from datetime import date, timedelta
from .models import PlanningHebdomadaire, PlanningVu


def planning_alertes_ctx(request):
    """Alimente à la fois le menu local du module Planning et la cloche de
    notifications globale (voir templates/base.html) — n'expose des données
    que lorsqu'on est effectivement dans le module Planning."""
    empty = {
        'planning_alertes': [], 'pl_can_manage': False,
        'planning_non_publiees': [], 'planning_non_vues': PlanningHebdomadaire.objects.none(),
        'planning_non_vues_count': 0, 'planning_notifs_total': 0,
    }
    if not (hasattr(request, 'user') and request.user.is_authenticated):
        return empty

    from core.utils import current_module
    if current_module(request) != 'planning':
        return empty

    from .views import can_manage_planning
    can_manage = can_manage_planning(request.user)

    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    next_monday = current_monday + timedelta(weeks=1)

    planning_non_publiees = []
    if can_manage:
        if not PlanningHebdomadaire.objects.filter(semaine_debut=current_monday, publie=True).exists():
            planning_non_publiees.append({'label': f'Semaine en cours (du {current_monday.strftime("%d/%m/%Y")})'})
        if not PlanningHebdomadaire.objects.filter(semaine_debut=next_monday, publie=True).exists():
            planning_non_publiees.append({'label': f'Semaine prochaine (du {next_monday.strftime("%d/%m/%Y")})'})

    viewed_ids = PlanningVu.objects.filter(user=request.user).values_list('planning_id', flat=True)
    planning_non_vues_qs = PlanningHebdomadaire.objects.filter(publie=True).exclude(pk__in=viewed_ids)
    planning_non_vues = planning_non_vues_qs.order_by('-semaine_debut')[:10]
    planning_non_vues_count = planning_non_vues_qs.count()

    return {
        'planning_alertes':          planning_non_publiees,
        'pl_can_manage':             can_manage,
        'planning_non_publiees':     planning_non_publiees,
        'planning_non_vues':         planning_non_vues,
        'planning_non_vues_count':   planning_non_vues_count,
        'planning_notifs_total':     len(planning_non_publiees) + planning_non_vues_count,
    }
