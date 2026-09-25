"""Pont entre les modèles Django et la passerelle blockchain (voir
blockchain/gateway). Toute panne réseau est journalisée, jamais levée : une
indisponibilité de la blockchain ne doit jamais empêcher un soin ou une
facturation (voir signals.py, seul appelant de ancrer_evenement)."""

import logging

from django.conf import settings
from django.utils import timezone

from . import hashing
from .models import AncrageBlockchain

logger = logging.getLogger(__name__)

# `requests` n'est importé que si BLOCKCHAIN_ENABLED est actif (voir chaque
# fonction ci-dessous) : tant que la fonctionnalité est désactivée, le reste
# de l'application ne doit pas dépendre de cette dépendance supplémentaire
# pour démarrer.


def ancrer_evenement(type_entite, id_entite, empreinte_hash, *, code_patient='', code_centre='', metadonnees=None):
    """Ancre un événement d'intégrité sur la blockchain, si BLOCKCHAIN_ENABLED.

    Idempotent : `id_evenement` est dérivé de manière déterministe de
    (type_entite, id_entite) ; un événement déjà ancré n'est jamais renvoyé
    une seconde fois (le chaincode le refuserait de toute façon — voir
    IntegriteContract.EnregistrerEvenement — mais on évite ici l'appel réseau
    inutile).
    """
    if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
        return None
    import requests

    id_evenement = f'{type_entite}:{id_entite}'
    if AncrageBlockchain.objects.filter(id_evenement=id_evenement).exists():
        return None

    ancrage = AncrageBlockchain.objects.create(
        id_evenement=id_evenement,
        type_entite=type_entite,
        id_entite=id_entite,
        code_patient=code_patient,
        code_centre=code_centre,
        empreinte_hash=empreinte_hash,
        statut='en_attente',
    )

    payload = {
        'idEvenement': id_evenement,
        'typeEntite': type_entite,
        'idEntite': id_entite,
        'codePatient': code_patient,
        'codeCentre': code_centre,
        'empreinteHash': empreinte_hash,
        'horodatage': timezone.now().isoformat(),
        'metadonnees': metadonnees or {},
    }

    try:
        response = requests.post(f'{settings.BLOCKCHAIN_GATEWAY_URL}/evenements', json=payload, timeout=5)
        response.raise_for_status()
        resultat = response.json()
    except requests.RequestException as exc:
        logger.warning('Ancrage blockchain échoué pour %s: %s', id_evenement, exc)
        ancrage.statut = 'erreur'
        ancrage.erreur_message = str(exc)
        ancrage.save(update_fields=['statut', 'erreur_message'])
        return ancrage

    ancrage.tx_id = resultat.get('txIdCreation', '')
    ancrage.statut = 'confirme'
    ancrage.date_confirmation = timezone.now()
    ancrage.save(update_fields=['tx_id', 'statut', 'date_confirmation'])
    return ancrage


def verifier_integrite(ancrage):
    """Recalcule l'empreinte depuis l'état courant de la base (jamais depuis
    le hash déjà stocké sur `ancrage`, qui daterait de l'ancrage) et la
    compare à celle inscrite sur la chaîne — c'est la vérification qui
    détecte une altération de la base Django postérieure à l'ancrage."""
    if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
        return None
    import requests

    empreinte_actuelle = hashing.recalculer_empreinte(ancrage.type_entite, ancrage.id_entite)
    if empreinte_actuelle is None:
        return {'conforme': False, 'erreur': "entité introuvable (supprimée depuis l'ancrage ?)"}

    try:
        response = requests.post(
            f'{settings.BLOCKCHAIN_GATEWAY_URL}/evenements/{ancrage.id_evenement}/verifier',
            json={'empreinteRecalculee': empreinte_actuelle},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Vérification d'intégrité échouée pour %s: %s", ancrage.id_evenement, exc)
        return {'conforme': False, 'erreur': str(exc)}
