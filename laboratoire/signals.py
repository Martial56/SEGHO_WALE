# -*- coding: utf-8 -*-
"""
Envoi automatique d'une demande d'examen au laboratoire (HPRIM/ORM) dès
qu'elle passe au statut « demandé ».

Mécanisme :
  - on mémorise le statut chargé depuis la base (pre_save) ;
  - sur post_save, si le statut vient de devenir "demande" et qu'aucun envoi
    réussi n'existe déjà, on déclenche l'envoi APRÈS le commit de la
    transaction (transaction.on_commit) pour ne pas transmettre une demande
    dont l'enregistrement échouerait ensuite.

L'envoi n'interrompt jamais la sauvegarde : toute erreur (FTP indisponible,
config absente) est journalisée dans EchangeHPRIM sans propager d'exception.
"""

from __future__ import annotations
import logging

from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import DemandeExamen, EchangeHPRIM

logger = logging.getLogger("laboratoire.hprim")

STATUT_DECLENCHEUR = "demande"   # « Demandé »


@receiver(pre_save, sender=DemandeExamen)
def _memoriser_statut_precedent(sender, instance, **kwargs):
    """Mémorise le statut actuellement en base avant la sauvegarde."""
    if instance.pk:
        ancien = (DemandeExamen.all_objects
                  .filter(pk=instance.pk)
                  .values_list("statut", flat=True)
                  .first())
        instance._ancien_statut = ancien
    else:
        instance._ancien_statut = None


@receiver(post_save, sender=DemandeExamen)
def _envoyer_si_demande(sender, instance, created, **kwargs):
    """Déclenche l'envoi HPRIM si la demande vient de passer à « demandé »."""
    ancien = getattr(instance, "_ancien_statut", None)

    # Transition vers le statut déclencheur :
    #  - création directe avec statut "demande", ou
    #  - passage d'un autre statut vers "demande".
    transition = (
        instance.statut == STATUT_DECLENCHEUR
        and (created or ancien != STATUT_DECLENCHEUR)
    )
    if not transition:
        return

    # Anti-doublon : ne pas réémettre si un envoi a déjà abouti.
    deja_envoye = EchangeHPRIM.all_objects.filter(
        demande=instance, sens="envoi",
        statut__in=("transmis", "en_attente"),
    ).exists()
    if deja_envoye:
        return

    demande_id = instance.pk

    def _faire_envoi():
        # Import tardif pour éviter tout import circulaire au chargement.
        from .hprim.services import envoyer_demande
        from .models import ConfigurationHPRIM
        try:
            demande = DemandeExamen.all_objects.get(pk=demande_id)
        except DemandeExamen.DoesNotExist:
            return

        # Centre sans configuration HPRIM active (ex. CMS WALE Toumbokro, qui
        # n'a pas de SYSLAM) : on sort silencieusement, sans log ni ligne
        # d'échange — ce n'est pas une erreur, c'est la normale pour ce centre.
        if ConfigurationHPRIM.active(demande.centre) is None:
            return

        # Filet de sécurité : refuser l'envoi d'une demande sans aucune ligne
        # d'examen. La vérification a lieu APRÈS le commit, donc les lignes
        # créées dans la même transaction que la demande sont déjà présentes.
        if not demande.lignes.exists():
            EchangeHPRIM.objects.create(
                sens="envoi", contexte="ORM",
                nom_fichier="(non généré)", demande=demande,
                statut="erreur", centre=demande.centre,
                message_log=("Envoi automatique annulé : la demande ne contient "
                             "aucune ligne d'examen. Ajoutez au moins un examen "
                             "puis relancez l'envoi (action « Envoyer au "
                             "laboratoire » dans l'admin)."),
            )
            logger.warning("Envoi HPRIM auto annulé pour %s : aucune ligne "
                           "d'examen.", demande.numero)
            return

        try:
            envoyer_demande(demande)
        except Exception as exc:  # noqa: BLE001
            # On ne propage pas : la demande reste enregistrée. La trace
            # détaillée vit dans EchangeHPRIM ; ici un log applicatif suffit.
            logger.warning("Envoi HPRIM auto échoué pour %s : %s",
                           getattr(demande, "numero", demande_id), exc)

    # Après commit pour ne pas transmettre une demande non persistée.
    transaction.on_commit(_faire_envoi)


# ──────────────────────────────────────────────────────────────────────────
# Statut « Facturée »
# ──────────────────────────────────────────────────────────────────────────

def synchroniser_statut_facturee(demandes):
    """Brouillon → Facturée quand la demande porte une facture non annulée ;
    Facturée → Brouillon si cette facture est annulée ou retirée. Les autres
    statuts (déjà partie au laboratoire) ne bougent pas.

    La condition porte sur le statut **en base**, pas sur celui de l'objet en
    mémoire, qui peut être périmé : une demande envoyée entre-temps ne doit
    pas repasser « Facturée ». update() ne redéclenche ni l'envoi HPRIM ni
    aucun autre signal."""
    for demande in demandes:
        facturee = bool(demande.facture_id) and (
            demande.facture is not None and demande.facture.statut != 'annulee')
        ancien, nouveau = ('brouillon', 'facturee') if facturee else ('facturee', 'brouillon')
        if DemandeExamen.all_objects.filter(pk=demande.pk, statut=ancien).update(statut=nouveau):
            demande.statut = nouveau


@receiver(post_save, sender=DemandeExamen)
def _statut_facturee_demande(sender, instance, **kwargs):
    """La caisse rattache la facture à la demande (demande.facture)."""
    synchroniser_statut_facturee([instance])


@receiver(post_save, sender='facturation.Facture')
def _statut_facturee_facture(sender, instance, **kwargs):
    """Annuler la facture remet ses demandes en brouillon."""
    synchroniser_statut_facturee(
        DemandeExamen.all_objects.filter(facture=instance).select_related('facture'))
