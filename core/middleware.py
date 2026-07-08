import threading

_locals = threading.local()


class CurrentUserMiddleware:
    """Store the current request user in thread-local so signals can read it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _locals.current_user = getattr(request, 'user', None)
        try:
            response = self.get_response(request)
        finally:
            _locals.current_user = None
        return response


def get_current_user():
    """Return the user for the current request, or None outside request context."""
    return getattr(_locals, 'current_user', None)


class SessionTimeoutMiddleware:
    """Déconnecte automatiquement un utilisateur après sa durée d'inactivité
    personnelle (UserProfile.session_timeout_minutes). 0 = désactivé."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            from django.contrib import messages
            from django.contrib.auth import logout
            from django.shortcuts import redirect
            from django.utils import timezone
            from core.models import UserProfile

            try:
                timeout_minutes = user.profile.session_timeout_minutes
            except UserProfile.DoesNotExist:
                timeout_minutes = 30

            if timeout_minutes > 0:
                now_ts = timezone.now().timestamp()
                last_activity = request.session.get('last_activity')
                if last_activity is not None and (now_ts - last_activity) > timeout_minutes * 60:
                    logout(request)
                    messages.info(request, "Vous avez été déconnecté automatiquement pour inactivité.")
                    return redirect('login')
                request.session['last_activity'] = now_ts

        return self.get_response(request)
