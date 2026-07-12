def pharmacie_alertes(request):
    if not request.user.is_authenticated:
        return {}
    if not request.path.startswith('/pharmacie/'):
        return {}
    try:
        from stock.models import DemandePharmacie
        # Extraire le code pharmacie depuis l'URL
        parts = request.path.split('/')
        pharmacie_code = parts[2] if len(parts) > 2 else ''
        nb = DemandePharmacie.objects.filter(
            pharmacie=pharmacie_code, statut='en_livraison'
        ).count() if pharmacie_code else 0
    except Exception:
        nb = 0
    return {'ph_livraisons_en_attente': nb}
