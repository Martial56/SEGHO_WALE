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


# ──────────────────────────────────────────────────────────────
# Facture → statut « Facturée » de l'ordonnance
# ──────────────────────────────────────────────────────────────

@receiver(post_save, sender='facturation.Facture')
def statut_facturee(sender, instance, **kwargs):
    """Une ordonnance passe « Facturée » dès qu'une facture non annulée la
    porte — la règle même qu'applique la caisse pour refuser de la facturer
    deux fois — et redevient « Émise » si sa facture est annulée. Seuls ces
    deux statuts bougent : une ordonnance déjà servie ou expirée le reste."""
    if not instance.ordonnance_id:
        return
    from facturation.models import Facture
    from .models import Ordonnance
    facturee = (Facture.all_objects.filter(ordonnance_id=instance.ordonnance_id)
                .exclude(statut='annulee').exists())
    if facturee:
        Ordonnance.objects.filter(pk=instance.ordonnance_id, statut='emise').update(statut='facturee')
    else:
        Ordonnance.objects.filter(pk=instance.ordonnance_id, statut='facturee').update(statut='emise')
