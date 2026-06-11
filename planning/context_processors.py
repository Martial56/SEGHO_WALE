from datetime import date, timedelta
from .models import PlanningHebdomadaire


def planning_alertes_ctx(request):
    if not (hasattr(request, 'user') and request.user.is_authenticated):
        return {}
    if not request.path.startswith('/planning/'):
        return {}

    from .views import can_manage_planning
    if not can_manage_planning(request.user):
        return {}

    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    next_monday = current_monday + timedelta(weeks=1)

    alertes = []
    if not PlanningHebdomadaire.objects.filter(semaine_debut=current_monday, publie=True).exists():
        alertes.append({'label': f'Semaine en cours (du {current_monday.strftime("%d/%m/%Y")})'})
    if not PlanningHebdomadaire.objects.filter(semaine_debut=next_monday, publie=True).exists():
        alertes.append({'label': f'Semaine prochaine (du {next_monday.strftime("%d/%m/%Y")})'})

    return {
        'planning_alertes': alertes,
        'pl_can_manage': True,
    }
