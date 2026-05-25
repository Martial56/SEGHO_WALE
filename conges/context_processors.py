from employer.models import NotificationConge, Conge


def conge_context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        cg_notifs_count = NotificationConge.objects.filter(
            destinataire=request.user, lue=False
        ).count()
        from conges.views import can_manage_rh
        cg_pending_count = (
            Conge.objects.filter(statut='demande').count()
            if can_manage_rh(request.user) else 0
        )
        return {
            'cg_notifs_count':  cg_notifs_count,
            'cg_pending_count': cg_pending_count,
        }
    except Exception:
        return {}
