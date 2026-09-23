import threading
from contextlib import contextmanager

_locals = threading.local()


class CurrentUserMiddleware:
    """Store the current request user (and son centre actif) in thread-local
    so les signaux et les managers cloisonnés (voir centres.models.ModeleCentre)
    peuvent les lire."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        _locals.current_user = user
        _locals.current_centre = None
        _locals.current_ip = _get_client_ip(request)
        request.centre = None
        try:
            if user is not None and getattr(user, 'is_authenticated', False):
                centre = _resoudre_centre_actif(user)
                _locals.current_centre = centre
                request.centre = centre
            response = self.get_response(request)
        finally:
            _locals.current_user = None
            _locals.current_centre = None
            _locals.current_ip = None
        return response


def _get_client_ip(request):
    """Adresse IP du client, en tenant compte d'un éventuel proxy inverse
    (en-tête X-Forwarded-For posé par celui-ci — le premier maillon de la
    chaîne est l'adresse réelle du client)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _resoudre_centre_actif(user):
    """Détermine le centre actif d'un utilisateur authentifié : celui déjà
    sélectionné (profile.centre_actif), ou — à défaut — le seul centre auquel
    il a accès (auto-sélection persistée)."""
    from django.core.exceptions import ObjectDoesNotExist
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        return None

    centre = profile.centre_actif
    if centre is None:
        centres_autorises = list(profile.centres.all()[:2])
        if len(centres_autorises) == 1:
            centre = centres_autorises[0]
            profile.centre_actif = centre
            profile.save(update_fields=['centre_actif'])
    return centre


def get_current_user():
    """Return the user for the current request, or None outside request context."""
    return getattr(_locals, 'current_user', None)


def get_current_ip():
    """Return l'adresse IP de la requête en cours, ou None hors requête."""
    return getattr(_locals, 'current_ip', None)


def get_current_centre():
    """Return le centre actif de la requête en cours, ou None hors requête."""
    return getattr(_locals, 'current_centre', None)


def set_current_centre(centre):
    _locals.current_centre = centre


def clear_current_centre():
    _locals.current_centre = None


@contextmanager
def centre_actif(centre):
    """Gestionnaire de contexte pour le code hors requête (management commands,
    cron, scripts) : rend `centre` actif pour la durée du bloc, puis restaure
    le centre précédent (imbrication sûre)."""
    precedent = get_current_centre()
    set_current_centre(centre)
    try:
        yield centre
    finally:
        set_current_centre(precedent)


class SessionTimeoutMiddleware:
    """Verrouille automatiquement la session d'un utilisateur après sa durée
    d'inactivité personnelle (UserProfile.session_timeout_minutes). 0 = désactivé.

    Contrairement à une déconnexion, le verrouillage NE détruit PAS la session :
    l'utilisateur reste authentifié, il doit juste ressaisir son mot de passe
    (voir core.views.lock_session / unlock_session) pour continuer — ce qui
    permet de revenir exactement à la page/au formulaire en cours sans rien
    perdre, tant que l'onglet n'a pas été rechargé ou fermé.
    """

    # Chemins qui doivent rester accessibles même verrouillé (sinon impossible
    # de se déverrouiller, ou de se déconnecter depuis l'écran de verrouillage).
    UNLOCK_EXEMPT_PATHS = {'/verrouiller/', '/deverrouiller/', '/logout/'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and request.path not in self.UNLOCK_EXEMPT_PATHS:
            from django.utils import timezone
            from core.models import UserProfile

            if request.session.get('locked'):
                return self._locked_response(request)

            try:
                timeout_minutes = user.profile.session_timeout_minutes
            except UserProfile.DoesNotExist:
                timeout_minutes = 30

            if timeout_minutes > 0:
                now_ts = timezone.now().timestamp()
                last_activity = request.session.get('last_activity')
                if last_activity is not None and (now_ts - last_activity) > timeout_minutes * 60:
                    request.session['locked'] = True
                    return self._locked_response(request)
                request.session['last_activity'] = now_ts

        return self.get_response(request)

    def _locked_response(self, request):
        from django.http import JsonResponse
        from django.shortcuts import render

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'locked': True}, status=423)
        return render(request, 'registration/locked.html', {'next': request.get_full_path()}, status=423)


class ActivityLogMiddleware:
    """Trace au journal chaque page effectivement consultée (ou reçu/document
    imprimé) par un utilisateur connecté — même quand l'action ne modifie
    aucune donnée (les signaux post_save/post_delete ne voient que les
    écritures en base). Complète, ne remplace pas, le suivi création/
    modification/suppression de core.audit.

    Doit être déclarée APRÈS CurrentUserMiddleware dans MIDDLEWARE : elle
    s'appuie sur core.middleware.get_current_ip() pour l'adresse IP.
    """

    # Préfixes jamais tracés : fichiers, API interne, le journal lui-même
    # (éviter le bruit et la boucle en consultant le journal), rechargement
    # navigateur en développement.
    CHEMINS_EXCLUS = (
        '/static/', '/media/', '/api/', '/journal/', '/__reload__/',
        '/admin/jsi18n/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._log_si_pertinent(request, response)
        except Exception:
            pass
        return response

    def _log_si_pertinent(self, request, response):
        if request.method != 'GET':
            return
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return
        if response.status_code != 200:
            return
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return
        content_type = response.get('Content-Type', '')
        if 'application/json' in content_type:
            return
        path = request.path
        if any(path.startswith(p) for p in self.CHEMINS_EXCLUS):
            return

        from core.views import log_event
        module = _module_depuis_request(request)
        log_event(user, user, f"Page consultée : {path}", type='consultation', module=module)


def _module_depuis_request(request):
    """Nom de l'app Django concernée par cette requête — via le namespace de
    l'URL si elle en a un, sinon le premier segment du chemin (convention de
    ce projet : chaque module préfixe ses routes par son propre nom)."""
    resolver_match = getattr(request, 'resolver_match', None)
    app_name = getattr(resolver_match, 'app_name', '') if resolver_match else ''
    if app_name:
        return app_name
    segments = [s for s in request.path.split('/') if s]
    return segments[0] if segments else 'core'
