from datetime import date, timedelta
from employer.models import NotificationConge, Conge


def conge_context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        today = date.today()
        cg_notifs_count = NotificationConge.objects.filter(
            destinataire=request.user, lue=False
        ).count()
        from conges.views import can_manage_rh
        is_rh = can_manage_rh(request.user)
        cg_pending_count = (
            Conge.objects.filter(statut__in=['demande', 'valide_service']).count()
            if is_rh else 0
        )
        cg_dans_7j = (
            Conge.objects.filter(
                statut='approuve',
                date_debut__gt=today,
                date_debut__lte=today + timedelta(days=7),
            ).count()
            if is_rh else 0
        )
        return {
            'cg_notifs_count':  cg_notifs_count,
            'cg_pending_count': cg_pending_count,
            'cg_dans_7j':       cg_dans_7j,
        }
    except Exception:
        return {}
