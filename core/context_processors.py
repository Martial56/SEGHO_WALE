from django.db.models import F


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
