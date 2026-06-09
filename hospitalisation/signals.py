from django.db.models.signals import post_save


def _on_facture_paid(facture):
    """Déclenche _sync_statut_soin_dossier quand une facture passe à 'payee'."""
    hosp = getattr(facture, 'hospitalisation', None)
    if not hosp:
        # Remonter via une ProcedureSoin liée au dossier de cette facture
        from soins.models import ProcedureSoin
        proc = (
            ProcedureSoin.objects
            .filter(facture=facture, soin__hospitalisation__isnull=False)
            .select_related('soin__hospitalisation')
            .first()
        )
        if proc and proc.soin:
            hosp = proc.soin.hospitalisation

    if hosp:
        from .views import _sync_statut_soin_dossier
        _sync_statut_soin_dossier(hosp)


def _facture_post_save(sender, instance, **kwargs):
    if instance.statut == 'payee':
        _on_facture_paid(instance)


def register():
    from facturation.models import Facture
    post_save.connect(
        _facture_post_save,
        sender=Facture,
        dispatch_uid='hosp_sync_soin_on_payment',
    )
