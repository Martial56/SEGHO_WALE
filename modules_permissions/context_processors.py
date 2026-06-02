from .models import get_user_modules


def user_modules(request):
    """
    Injecte `user_modules` dans chaque template pour filtrer la sidebar
    et d'autres éléments de navigation.
    """
    if not request.user.is_authenticated:
        return {'user_modules': [], 'user_module_codes': set()}

    modules = get_user_modules(request.user)
    codes = set(modules.values_list('code', flat=True))
    return {
        'user_modules': modules,
        'user_module_codes': codes,
    }
