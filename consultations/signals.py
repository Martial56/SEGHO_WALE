from django.db.models.signals import post_save
from django.dispatch import receiver

# ──────────────────────────────────────────────────────────────
# Consultation → synchronisation statut RendezVous
# ──────────────────────────────────────────────────────────────

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
        # L'évaluation clinique (infirmier) crée aussi une consultation : elle
        # ne doit pas démarrer la consultation à la place du médecin.
        if rdv.statut == 'en_attente' and not getattr(instance, '_evaluation_seule', False):
            rdv.statut = 'en_consultation'
            rdv.save(update_fields=['statut'])
    else:
        if instance.statut == 'termine' and rdv.statut not in TERMINAL:
            rdv.statut = 'termine'
            rdv.save(update_fields=['statut'])
        elif instance.statut == 'annule' and rdv.statut not in TERMINAL:
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])
