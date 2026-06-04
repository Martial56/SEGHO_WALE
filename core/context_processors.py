from django.db.models import F


def user_profile(request):
    if not request.user.is_authenticated:
        return {'user_profile': None}
    try:
        from core.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return {'user_profile': profile}
    except Exception:
        return {'user_profile': None}


def header_stats(request):
    if not request.user.is_authenticated:
        return {'header_stats': {'medicaments_alerte': 0, 'factures_impayees': 0, 'analyses_pending': 0}}
    try:
        from pharmacie.models import Medicament
        from facturation.models import Facture
        from laboratoire.models import AnalyseLaboratoire
        return {
            'header_stats': {
                'medicaments_alerte': Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count(),
                'factures_impayees': Facture.objects.filter(statut__in=['emise', 'partielle']).count(),
                'analyses_pending': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
            }
        }
    except Exception:
        return {'header_stats': {'medicaments_alerte': 0, 'factures_impayees': 0, 'analyses_pending': 0}}
