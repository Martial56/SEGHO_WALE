from django.db.models import F


def user_profile(request):
    if not request.user.is_authenticated:
        return {'user_profile': None, 'accent_css': None}
    try:
        from core.models import UserProfile
        from core.utils import build_accent_css, is_valid_hex_color
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        accent_css = build_accent_css(profile.accent_color) if is_valid_hex_color(profile.accent_color) else None
        return {'user_profile': profile, 'accent_css': accent_css}
    except Exception:
        return {'user_profile': None, 'accent_css': None}


def header_stats(request):
    empty = {'header_stats': {'medicaments_alerte': 0, 'factures_impayees': 0, 'analyses_pending': 0}}
    if not request.user.is_authenticated:
        return empty
    from core.utils import current_module
    module = current_module(request)
    try:
        return {
            'header_stats': {
                'medicaments_alerte': _medicaments_alerte_count() if module == 'pharmacie' else 0,
                'factures_impayees': _factures_impayees_count() if module == 'facturation' else 0,
                'analyses_pending': _analyses_pending_count() if module == 'laboratoire' else 0,
            }
        }
    except Exception:
        return empty


def _medicaments_alerte_count():
    from pharmacie.models import Medicament
    return Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count()


def _factures_impayees_count():
    from facturation.models import Facture
    return Facture.objects.filter(statut__in=['emise', 'partielle']).count()


def _analyses_pending_count():
    from laboratoire.models import AnalyseLaboratoire
    return AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count()
