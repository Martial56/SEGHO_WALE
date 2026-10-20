"""Pont entre les modèles Django et la passerelle blockchain (voir
blockchain/gateway). Toute panne réseau est journalisée, jamais levée : une
indisponibilité de la blockchain ne doit jamais empêcher un soin ou une
facturation (voir signals.py, seul appelant de ancrer_evenement).

Règle de confidentialité : les données envoyées à la chaîne sont immuables et
répliquées chez Org2. Le code patient y est donc toujours pseudonymisé
(HMAC-SHA256 avec une clé connue de SEGHO seul) et les métadonnées sont
limitées à une liste blanche de valeurs techniques."""

import hashlib
import hmac
import logging
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import hashing
from .models import AncrageBlockchain

logger = logging.getLogger(__name__)

# `requests` n'est importé que si BLOCKCHAIN_ENABLED est actif (voir chaque
# fonction ci-dessous) : tant que la fonctionnalité est désactivée, le reste
# de l'application ne doit pas dépendre de cette dépendance supplémentaire
# pour démarrer.

# Délai d'attente de la passerelle : une soumission attend la validation du
# bloc par le réseau, ce qui peut dépasser quelques secondes.
DELAI_PASSERELLE = 15

# Liste blanche des métadonnées : doit rester identique à celle de la
# passerelle (gateway/validation.go) et du chaincode (chaincode/validation.go).
CLES_METADONNEES_AUTORISEES = frozenset({
    'version_schema',
    'type_document',
    'code_examen',
    'type_message_hprim',
})
NOMBRE_MAX_METADONNEES = 10
LONGUEUR_MAX_VALEUR = 64
MOTIF_VALEUR_METADONNEE = re.compile(r'^[A-Za-z0-9._:\-]+$')

LONGUEUR_MAX_MESSAGE_ERREUR = 255


def pseudonymiser_code_patient(code_patient):
    """Retourne le pseudonyme HMAC-SHA256 (64 caractères hexadécimaux) du code
    patient, ou une chaîne vide si aucun code n'est fourni.

    La clé BLOCKCHAIN_CLE_PSEUDONYMISATION ne doit jamais changer (sinon un
    même patient aurait deux pseudonymes) ni être communiquée à Org2."""
    if not code_patient:
        return ''
    cle = getattr(settings, 'BLOCKCHAIN_CLE_PSEUDONYMISATION', '')
    if not cle:
        raise ImproperlyConfigured(
            'BLOCKCHAIN_CLE_PSEUDONYMISATION doit être défini lorsque BLOCKCHAIN_ENABLED est actif.'
        )
    return hmac.new(cle.encode('utf-8'), str(code_patient).encode('utf-8'), hashlib.sha256).hexdigest()


def identifiant_public(type_entite, id_entite):
    """Retourne l'identifiant public (32 caractères hexadécimaux) sous lequel
    une entité est ancrée sur la chaîne.

    Les identifiants internes (code patient, numéros séquentiels de
    consultation ou de facture) ne doivent pas figurer sur la chaîne : le
    premier est une donnée personnelle, les seconds révèlent le volume
    d'activité du centre. La correspondance avec l'identifiant interne est
    conservée uniquement dans la table locale AncrageBlockchain."""
    cle = getattr(settings, 'BLOCKCHAIN_CLE_PSEUDONYMISATION', '')
    if not cle:
        raise ImproperlyConfigured(
            'BLOCKCHAIN_CLE_PSEUDONYMISATION doit être défini lorsque BLOCKCHAIN_ENABLED est actif.'
        )
    message = f'entite:{type_entite}:{id_entite}'.encode('utf-8')
    return hmac.new(cle.encode('utf-8'), message, hashlib.sha256).hexdigest()[:32]


def normaliser_metadonnees(metadonnees):
    """Convertit les métadonnées en dictionnaire chaîne → chaîne conforme à la
    liste blanche. Lève ValueError pour toute clé ou valeur non conforme."""
    if not metadonnees:
        return {}
    if len(metadonnees) > NOMBRE_MAX_METADONNEES:
        raise ValueError(f'{NOMBRE_MAX_METADONNEES} métadonnées maximum')

    resultat = {}
    for cle, valeur in metadonnees.items():
        if cle not in CLES_METADONNEES_AUTORISEES:
            raise ValueError(f'clé de métadonnée non autorisée : {cle!r}')
        if valeur is None:
            continue
        if isinstance(valeur, bool):
            valeur = 'true' if valeur else 'false'
        elif isinstance(valeur, (list, tuple, set, dict)):
            raise ValueError(f'métadonnée {cle!r} : valeur simple attendue')
        valeur = str(valeur)
        if not 1 <= len(valeur) <= LONGUEUR_MAX_VALEUR or not MOTIF_VALEUR_METADONNEE.match(valeur):
            raise ValueError(f'métadonnée {cle!r} : valeur technique attendue (lettres, chiffres, . _ : -)')
        resultat[cle] = valeur
    return resultat


def ancrer_evenement(type_entite, id_entite, empreinte_hash, *, code_patient='', code_centre='', metadonnees=None):
    """Ancre l'état courant d'un enregistrement sur la blockchain, si
    BLOCKCHAIN_ENABLED.

    Versionnement : chaque état distinct d'un enregistrement est ancré sous
    une version propre (identifiant `type:identifiant_public:vN`).
    - aucun ancrage antérieur : la version 1 est créée ;
    - dernière version confirmée avec la même empreinte : rien n'est envoyé
      (état déjà ancré) ;
    - dernière version confirmée avec une empreinte différente : l'enregistrement
      a été modifié, une nouvelle version est créée ;
    - dernière version en erreur ou en attente : elle est retentée.

    Sur la chaîne, l'entité est désignée par son identifiant public (voir
    identifiant_public), jamais par son identifiant interne.
    """
    if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
        return None
    import requests

    id_entite = str(id_entite)
    try:
        id_public = identifiant_public(type_entite, id_entite)
    except ImproperlyConfigured as exc:
        logger.error('Ancrage blockchain impossible pour %s %s : %s', type_entite, id_entite, exc)
        return None

    derniere = derniere_version(type_entite, id_entite)
    if derniere is None:
        ancrage = _creer_version(type_entite, id_entite, id_public, 1, empreinte_hash, code_patient, code_centre)
    elif derniere.statut == 'confirme':
        if derniere.empreinte_hash == empreinte_hash:
            return None
        ancrage = _creer_version(type_entite, id_entite, id_public, derniere.version + 1,
                                 empreinte_hash, code_patient, code_centre)
    else:
        ancrage = derniere
        ancrage.code_patient = code_patient
        ancrage.code_centre = code_centre
        ancrage.empreinte_hash = empreinte_hash
        ancrage.statut = 'en_attente'
        ancrage.save(update_fields=['code_patient', 'code_centre', 'empreinte_hash', 'statut'])

    if ancrage is None:
        return None
    return _soumettre(requests, ancrage, id_public, code_patient, code_centre, metadonnees)


def derniere_version(type_entite, id_entite, statut=None):
    """Retourne la version la plus récente de l'ancrage d'une entité."""
    ancrages = AncrageBlockchain.objects.filter(type_entite=type_entite, id_entite=str(id_entite))
    if statut:
        ancrages = ancrages.filter(statut=statut)
    return ancrages.order_by('-version').first()


def verifier_integrite(ancrage):
    """Recalcule l'empreinte depuis l'état courant de la base (jamais depuis
    le hash déjà stocké sur `ancrage`, qui daterait de l'ancrage) et la
    compare à celle inscrite sur la chaîne — c'est la vérification qui
    détecte une altération de la base Django postérieure à l'ancrage.

    La comparaison porte toujours sur la dernière version confirmée de
    l'entité : une modification faite par l'application a été ancrée comme
    une nouvelle version, seule une modification faite hors de l'application
    (par exemple directement en base) est signalée comme une altération."""
    if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
        return None
    import requests

    reference = derniere_version(ancrage.type_entite, ancrage.id_entite, statut='confirme')
    if reference is None:
        return {'conforme': False, 'erreur': 'aucune version confirmée sur le registre pour cette entité'}

    empreinte_actuelle = hashing.recalculer_empreinte(ancrage.type_entite, ancrage.id_entite)
    if empreinte_actuelle is None:
        return {'conforme': False, 'erreur': "entité introuvable (supprimée depuis l'ancrage ?)"}

    try:
        response = requests.post(
            f'{settings.BLOCKCHAIN_GATEWAY_URL}/evenements/{reference.id_evenement}/verifier',
            json={'empreinteRecalculee': empreinte_actuelle},
            timeout=DELAI_PASSERELLE,
        )
        response.raise_for_status()
        resultat = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Vérification d'intégrité échouée pour %s : %s", reference.id_evenement, exc)
        return {'conforme': False, 'erreur': str(exc)}

    resultat['version_verifiee'] = reference.version
    if reference.pk != ancrage.pk:
        resultat['remarque'] = (
            f'la version {ancrage.version} a été remplacée par la version {reference.version} : '
            f'la vérification porte sur cette dernière'
        )
    return resultat


def _creer_version(type_entite, id_entite, id_public, version, empreinte_hash, code_patient, code_centre):
    """Crée la ligne locale d'une nouvelle version. Retourne None si une autre
    exécution concurrente l'a créée au même instant."""
    try:
        with transaction.atomic():
            return AncrageBlockchain.objects.create(
                id_evenement=f'{type_entite}:{id_public}:v{version}',
                type_entite=type_entite,
                id_entite=id_entite,
                version=version,
                code_patient=code_patient,
                code_centre=code_centre,
                empreinte_hash=empreinte_hash,
                statut='en_attente',
            )
    except IntegrityError:
        logger.info('Version %s de %s %s déjà créée par un autre traitement', version, type_entite, id_entite)
        return None


def _soumettre(requests, ancrage, id_public, code_patient, code_centre, metadonnees, reprise_autorisee=True):
    try:
        payload = {
            'idEvenement': ancrage.id_evenement,
            'typeEntite': ancrage.type_entite,
            'idEntite': id_public,
            'codePatient': pseudonymiser_code_patient(code_patient),
            'codeCentre': code_centre,
            'empreinteHash': ancrage.empreinte_hash,
            'horodatage': timezone.now().isoformat(),
            'metadonnees': normaliser_metadonnees(metadonnees),
        }
    except (ValueError, ImproperlyConfigured) as exc:
        logger.error('Ancrage blockchain refusé pour %s (données non conformes) : %s', ancrage.id_evenement, exc)
        return _marquer_erreur(ancrage, f'données non conformes : {exc}')

    try:
        response = requests.post(
            f'{settings.BLOCKCHAIN_GATEWAY_URL}/evenements', json=payload, timeout=DELAI_PASSERELLE,
        )
    except requests.RequestException as exc:
        logger.warning('Ancrage blockchain échoué pour %s : %s', ancrage.id_evenement, exc)
        return _marquer_erreur(ancrage, str(exc))

    if response.status_code == 201:
        return _marquer_confirme(ancrage, _lire_json(response))

    message = _message_erreur(response)

    # Une tentative précédente a été validée par le réseau, mais sa réponse a
    # été perdue : cette version existe déjà sur la chaîne.
    if 'déjà enregistré' in message:
        existant = _consulter_evenement(requests, ancrage.id_evenement)
        if existant and existant.get('empreinteHash') == ancrage.empreinte_hash:
            return _marquer_confirme(ancrage, existant)
        if existant and existant.get('empreinteHash') and reprise_autorisee:
            # La chaîne fait foi : la version inscrite porte l'état antérieur.
            # On l'enregistre telle quelle, puis l'état courant est ancré
            # comme version suivante.
            empreinte_courante = ancrage.empreinte_hash
            ancrage.empreinte_hash = existant['empreinteHash']
            ancrage.save(update_fields=['empreinte_hash'])
            _marquer_confirme(ancrage, existant)
            suivante = _creer_version(ancrage.type_entite, ancrage.id_entite, id_public, ancrage.version + 1,
                                      empreinte_courante, code_patient, code_centre)
            if suivante is None:
                return ancrage
            return _soumettre(requests, suivante, id_public, code_patient, code_centre, metadonnees,
                              reprise_autorisee=False)
        message = "un événement portant cet identifiant existe déjà sur la chaîne avec une autre empreinte"

    logger.warning('Ancrage blockchain refusé pour %s : HTTP %s %s', ancrage.id_evenement, response.status_code, message)
    return _marquer_erreur(ancrage, f'HTTP {response.status_code} : {message}')


# --- Utilitaires internes ---

def _marquer_confirme(ancrage, resultat):
    ancrage.tx_id = (resultat or {}).get('txIdCreation', '')
    ancrage.statut = 'confirme'
    ancrage.erreur_message = ''
    ancrage.date_confirmation = timezone.now()
    ancrage.save(update_fields=['tx_id', 'statut', 'erreur_message', 'date_confirmation'])
    return ancrage


def _marquer_erreur(ancrage, message):
    ancrage.statut = 'erreur'
    ancrage.erreur_message = str(message)[:LONGUEUR_MAX_MESSAGE_ERREUR]
    ancrage.save(update_fields=['statut', 'erreur_message'])
    return ancrage


def _lire_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


def _message_erreur(response):
    corps = _lire_json(response)
    if isinstance(corps, dict) and corps.get('erreur'):
        return str(corps['erreur'])
    return response.text[:LONGUEUR_MAX_MESSAGE_ERREUR]


def _consulter_evenement(requests, id_evenement):
    try:
        response = requests.get(
            f'{settings.BLOCKCHAIN_GATEWAY_URL}/evenements/{id_evenement}', timeout=DELAI_PASSERELLE,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    return _lire_json(response)
