def stock_alertes(request):
    if not request.user.is_authenticated:
        return {}
    try:
        from .models import DemandePharmacie
        nb_demandes = DemandePharmacie.objects.filter(statut='en_attente').count()
    except Exception:
        nb_demandes = 0
    try:
        from achats.models import ReceptionAchat
        nb_receptions = ReceptionAchat.objects.filter(integre_en_stock=False).count()
    except Exception:
        nb_receptions = 0
    return {
        'stock_demandes_en_attente':    nb_demandes,
        'stock_receptions_a_integrer':  nb_receptions,
    }
