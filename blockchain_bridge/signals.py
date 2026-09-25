"""Ancrage automatique sur la blockchain à des transitions significatives des
modèles existants — pas à chaque sauvegarde brouillon. Voir
blockchain/README.md pour la portée volontairement limitée de cette
intégration (IntegriteContract seulement)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from . import hashing
from .services import ancrer_evenement


def _code_centre(instance_avec_centre):
    centre = getattr(instance_avec_centre, 'centre', None)
    return centre.code if centre else ''


@receiver(post_save, sender='patients.Patient')
def ancrer_patient(sender, instance, created, **kwargs):
    if not created:
        return
    ancrer_evenement(
        'patient', instance.code_patient,
        hashing.empreinte_patient(instance),
        code_patient=instance.code_patient,
        code_centre=_code_centre(instance),
    )


@receiver(post_save, sender='consultations.Consultation')
def ancrer_consultation(sender, instance, created, **kwargs):
    if instance.statut != 'termine':
        return
    ancrer_evenement(
        'consultation', instance.numero,
        hashing.empreinte_consultation(instance),
        code_patient=instance.patient.code_patient,
        code_centre=_code_centre(instance.patient),
    )


@receiver(post_save, sender='consultations.Ordonnance')
def ancrer_ordonnance(sender, instance, created, **kwargs):
    if instance.consultation_id:
        return  # couverte par l'ancrage de la consultation (voir ancrer_consultation)
    patient = instance.patient_effectif
    if patient is None:
        return
    ancrer_evenement(
        'ordonnance', instance.numero,
        hashing.empreinte_ordonnance(instance),
        code_patient=patient.code_patient,
        code_centre=_code_centre(patient),
    )


@receiver(post_save, sender='facturation.Facture')
def ancrer_facture(sender, instance, created, **kwargs):
    if instance.statut != 'emise':
        return
    ancrer_evenement(
        'facture', instance.numero,
        hashing.empreinte_facture(instance),
        code_patient=instance.patient.code_patient,
        code_centre=_code_centre(instance),
    )


@receiver(post_save, sender='facturation.Paiement')
def ancrer_paiement(sender, instance, created, **kwargs):
    if not created:
        return
    ancrer_evenement(
        'paiement', instance.numero,
        hashing.empreinte_paiement(instance),
        code_patient=instance.facture.patient.code_patient,
        code_centre=_code_centre(instance),
    )


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
    ancrer_evenement(
        'echange_hprim', str(instance.pk),
        hashing.empreinte_echange_hprim(instance),
        code_patient=code_patient,
        code_centre=_code_centre(instance),
        metadonnees={'sens': instance.sens, 'contexte': instance.contexte, 'nom_fichier': instance.nom_fichier},
    )


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
    ancrer_evenement(
        'analyse_laboratoire', analyse.numero,
        hashing.empreinte_analyse_laboratoire(analyse),
        code_patient=analyse.patient.code_patient,
        code_centre=_code_centre(analyse.patient),
    )
