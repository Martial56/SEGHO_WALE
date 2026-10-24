def session_caisse(request):
    """Session de caisse en cours, pour le bandeau de la barre du haut.

    `doit_ouvrir_caisse` signale une caissière qui n'a pas encore ouvert sa
    caisse aujourd'hui (ou dont la session de la veille reste ouverte).
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    from .caisse import peut_encaisser, session_ouverte
    if not peut_encaisser(user):
        return {}
    session = session_ouverte(user)
    return {
        'session_caisse': session,
        'doit_ouvrir_caisse': (session is None or not session.est_du_jour) and not user.is_superuser,
    }
