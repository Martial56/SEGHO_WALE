def permanence_medecins_ctx(request):
    """Expose si l'utilisateur peut gérer la permanence des médecins (nav) —
    ne fait la vérification que dans le module Présence."""
    empty = {'can_manage_medecins_permanence': False}
    if not request.user.is_authenticated:
        return empty
    try:
        if not request.path.startswith('/presence/'):
            return empty
        from medecins.views import can_manage_medecins
        return {'can_manage_medecins_permanence': can_manage_medecins(request.user)}
    except Exception:
        return empty
