from datetime import date, timedelta
from employer.models import Conge


def conge_context(request):
    """Alimente la cloche de notifications globale avec les alertes RH congés
    (demandes en attente, congés approuvés débutant bientôt) — n'expose des
    données que lorsqu'on est dans le module Congés et pour les gestionnaires RH."""
    empty = {
        'cg_demandes_attente': Conge.objects.none(), 'cg_demandes_attente_count': 0,
        'cg_debut_proche': Conge.objects.none(), 'cg_debut_proche_count': 0,
        'cg_rh_notifs_total': 0,
    }
    if not request.user.is_authenticated:
        return empty
    try:
        from core.utils import current_module
        if current_module(request) != 'conges':
            return empty

        from conges.views import can_manage_rh
        if not can_manage_rh(request.user):
            return empty

        today = date.today()
        cg_demandes_attente = (
            Conge.objects.filter(statut__in=['demande', 'valide_service'])
            .select_related('employe').order_by('date_demande')[:20]
        )
        cg_demandes_attente_count = Conge.objects.filter(
            statut__in=['demande', 'valide_service']
        ).count()
        cg_debut_proche = (
            Conge.objects.filter(
                statut='approuve',
                date_debut__gt=today,
                date_debut__lte=today + timedelta(days=7),
            ).select_related('employe').order_by('date_debut')[:20]
        )
        cg_debut_proche_count = Conge.objects.filter(
            statut='approuve',
            date_debut__gt=today,
            date_debut__lte=today + timedelta(days=7),
        ).count()

        return {
            'cg_demandes_attente':       cg_demandes_attente,
            'cg_demandes_attente_count': cg_demandes_attente_count,
            'cg_debut_proche':           cg_debut_proche,
            'cg_debut_proche_count':     cg_debut_proche_count,
            'cg_rh_notifs_total':        cg_demandes_attente_count + cg_debut_proche_count,
        }
    except Exception:
        return empty
