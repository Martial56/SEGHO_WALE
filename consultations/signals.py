from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='consultations.Consultation')
def sync_rdv_statut(sender, instance, created, **kwargs):
    if not instance.rendez_vous_id:
        return
    try:
        rdv = instance.rendez_vous
    except Exception:
        return

    TERMINAL = ('termine', 'annule', 'absent')

    if created:
        # N'avancer vers 'en_consultation' que si le RDV est déjà en attente.
        # Créer une consultation pendant l'évaluation clinique (statut 'confirme')
        # ne doit pas sauter l'étape 'en_attente'.
        if rdv.statut == 'en_attente':
            rdv.statut = 'en_consultation'
            rdv.save(update_fields=['statut'])
    else:
        if instance.statut == 'termine' and rdv.statut not in TERMINAL:
            rdv.statut = 'termine'
            rdv.save(update_fields=['statut'])
        elif instance.statut == 'annule' and rdv.statut not in TERMINAL:
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])
