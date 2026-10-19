"""Ancrage automatique sur la blockchain à des transitions significatives des
modèles existants — pas à chaque sauvegarde brouillon. Voir
blockchain/README.md pour la portée volontairement limitée de cette
intégration (IntegriteContract seulement).

Tout ancrage est différé après la validation de la transaction en base
(transaction.on_commit) : un événement inscrit sur la chaîne est définitif,
il ne doit jamais porter sur une donnée dont l'enregistrement serait ensuite
annulé. L'empreinte est calculée à ce moment-là, sur l'état validé.

Versionnement : un signal peut se déclencher à chaque sauvegarde ; seul un
état dont l'empreinte diffère de la dernière version ancrée donne lieu à une
nouvelle version (voir services.ancrer_evenement). Une sauvegarde qui ne
modifie aucun champ couvert par l'empreinte n'envoie donc rien au registre."""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import hashing
from .services import ancrer_evenement

logger = logging.getLogger(__name__)


def _code_centre(instance_avec_centre):
    centre = getattr(instance_avec_centre, 'centre', None)
    return centre.code if centre else ''


def _programmer_ancrage(description, fonction):
    """Exécute `fonction` après la validation de la transaction courante.

    Une erreur pendant l'ancrage (calcul d'empreinte, réseau…) est
    journalisée, jamais propagée : la blockchain ne doit jamais empêcher un
    soin ou une facturation."""
    if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
        return

    def _executer():
        try:
            fonction()
        except Exception:
            logger.exception('Échec inattendu de l\'ancrage blockchain (%s)', description)

    transaction.on_commit(_executer)


@receiver(post_save, sender='patients.Patient')
def ancrer_patient(sender, instance, created, **kwargs):
    # À la création, puis à chaque modification des champs couverts par
    # l'empreinte (nouvelle version).
    _programmer_ancrage(f'patient {instance.pk}', lambda: ancrer_evenement(
        'patient', instance.code_patient,
        hashing.empreinte_patient(instance),
        code_patient=instance.code_patient,
        code_centre=_code_centre(instance),
    ))


@receiver(post_save, sender='consultations.Consultation')
def ancrer_consultation(sender, instance, created, **kwargs):
    if instance.statut != 'termine':
        return
    _programmer_ancrage(f'consultation {instance.pk}', lambda: ancrer_evenement(
        'consultation', instance.numero,
        hashing.empreinte_consultation(instance),
        code_patient=instance.patient.code_patient,
        code_centre=_code_centre(instance.patient),
        metadonnees={'type_document': 'consultation'},
    ))


@receiver(post_save, sender='consultations.Ordonnance')
def ancrer_ordonnance(sender, instance, created, **kwargs):
    if instance.consultation_id:
        return  # couverte par l'ancrage de la consultation (voir ancrer_consultation)
    patient = instance.patient_effectif
    if patient is None:
        return
    _programmer_ancrage(f'ordonnance {instance.pk}', lambda: ancrer_evenement(
        'ordonnance', instance.numero,
        hashing.empreinte_ordonnance(instance),
        code_patient=patient.code_patient,
        code_centre=_code_centre(patient),
        metadonnees={'type_document': 'ordonnance'},
    ))


@receiver(post_save, sender='facturation.Facture')
def ancrer_facture(sender, instance, created, **kwargs):
    if instance.statut != 'emise':
        return
    _programmer_ancrage(f'facture {instance.pk}', lambda: ancrer_evenement(
        'facture', instance.numero,
        hashing.empreinte_facture(instance),
        code_patient=instance.patient.code_patient,
        code_centre=_code_centre(instance),
        metadonnees={'type_document': 'facture'},
    ))


@receiver(post_save, sender='facturation.Paiement')
def ancrer_paiement(sender, instance, created, **kwargs):
    # À la création, puis à chaque modification (nouvelle version).
    _programmer_ancrage(f'paiement {instance.pk}', lambda: ancrer_evenement(
        'paiement', instance.numero,
        hashing.empreinte_paiement(instance),
        code_patient=instance.facture.patient.code_patient,
        code_centre=_code_centre(instance),
        metadonnees={'type_document': 'paiement'},
    ))


def _metadonnees_hprim(echange):
    """Métadonnées techniques d'un échange HPRIM, limitées à la liste blanche.
    Le nom de fichier n'est pas transmis : il peut contenir un numéro de
    demande."""
    metadonnees = {'type_document': f'hprim-{echange.sens}'}
    if echange.contexte:
        metadonnees['type_message_hprim'] = echange.contexte
    return metadonnees


@receiver(post_save, sender='laboratoire.EchangeHPRIM')
def ancrer_echange_hprim(sender, instance, created, **kwargs):
    """Ancre chaque message HPRIM réellement échangé avec le laboratoire
    externe — l'envoi d'une demande (ORM) une fois transmise par FTP, et la
    réception d'un résultat ou d'une erreur (ORU/ERR) une fois intégrée. Les
    tentatives internes en échec (FTP indisponible, etc.) ne sont pas ancrées :
    rien n'a alors réellement franchi la frontière inter-systèmes."""
    if instance.sens == 'envoi' and instance.statut != 'transmis':
        return
    if instance.sens == 'reception' and instance.statut != 'traite':
        return

    code_patient = instance.demande.patient.code_patient if instance.demande_id else ''
    _programmer_ancrage(f'échange HPRIM {instance.pk}', lambda: ancrer_evenement(
        'echange_hprim', str(instance.pk),
        hashing.empreinte_echange_hprim(instance),
        code_patient=code_patient,
        code_centre=_code_centre(instance),
        metadonnees=_metadonnees_hprim(instance),
    ))


def ancrer_analyse_laboratoire_validee(analyse):
    """Ancre un résultat de laboratoire validé, une fois ses lignes de
    résultat attachées. Appelée explicitement depuis
    laboratoire.hprim.integration.integrer_oru — pas via un signal post_save
    générique : au moment où AnalyseLaboratoire.statut passe à 'valide' lors
    d'un import HPRIM, ses ResultatAnalyse ne sont pas encore créées (elles le
    sont juste après, dans la même fonction), un ancrage sur ce seul signal
    hasherait donc un jeu de résultats incomplet."""
    if analyse.statut != 'valide':
        return
    _programmer_ancrage(f'analyse {analyse.pk}', lambda: ancrer_evenement(
        'analyse_laboratoire', analyse.numero,
        hashing.empreinte_analyse_laboratoire(analyse),
        code_patient=analyse.patient.code_patient,
        code_centre=_code_centre(analyse.patient),
        metadonnees={'type_document': 'analyse_laboratoire'},
    ))
