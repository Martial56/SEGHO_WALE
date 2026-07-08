from .models import Soin


def soins_alertes(request):
    """Alimente la cloche de notifications globale avec les soins en attente
    de paiement — n'expose des données que dans le module Soins."""
    empty = {'soins_en_attente': Soin.objects.none(), 'soins_en_attente_count': 0}
    if not request.user.is_authenticated:
        return empty

    from core.utils import current_module
    if current_module(request) != 'soins':
        return empty

    qs = Soin.objects.filter(statut='en_attente_de_paiement').select_related('patient').order_by('-date_heure')
    return {
        'soins_en_attente': qs[:20],
        'soins_en_attente_count': qs.count(),
    }
