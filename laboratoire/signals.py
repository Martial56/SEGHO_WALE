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
        ancien = (DemandeExamen.objects
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
    deja_envoye = EchangeHPRIM.objects.filter(
        demande=instance, sens="envoi",
        statut__in=("transmis", "en_attente"),
    ).exists()
    if deja_envoye:
        return

    demande_id = instance.pk

    def _faire_envoi():
        # Import tardif pour éviter tout import circulaire au chargement.
        from .hprim.services import envoyer_demande
        try:
            demande = DemandeExamen.objects.get(pk=demande_id)
        except DemandeExamen.DoesNotExist:
            return

        # Filet de sécurité : refuser l'envoi d'une demande sans aucune ligne
        # d'examen. La vérification a lieu APRÈS le commit, donc les lignes
        # créées dans la même transaction que la demande sont déjà présentes.
        if not demande.lignes.exists():
            EchangeHPRIM.objects.create(
                sens="envoi", contexte="ORM",
                nom_fichier="(non généré)", demande=demande,
                statut="erreur",
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
