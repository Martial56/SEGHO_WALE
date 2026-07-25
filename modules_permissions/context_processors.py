from .models import get_user_modules, get_hidden_navitem_codes


def user_modules(request):
    """
    Injecte `user_modules` dans chaque template pour filtrer la sidebar
    et d'autres éléments de navigation, ainsi que `hidden_navitem_codes`
    pour filtrer les menus/sous-menus des barres de navigation internes.
    """
    if not request.user.is_authenticated:
        return {'user_modules': [], 'user_module_codes': set(), 'hidden_navitem_codes': set()}

    modules = get_user_modules(request.user)
    codes = set(modules.values_list('code', flat=True))
    return {
        'user_modules': modules,
        'user_module_codes': codes,
        'hidden_navitem_codes': get_hidden_navitem_codes(request.user),
    }
