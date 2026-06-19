import threading

_locals = threading.local()


class CurrentUserMiddleware:
    """Store the current request user in thread-local so signals can read it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _locals.current_user = getattr(request, 'user', None)
        response = self.get_response(request)
        return response


def get_current_user():
    """Return the user for the current request, or None outside request context."""
    return getattr(_locals, 'current_user', None)
