from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

def user_has_permission(user, module_name):
    """
    Vérifie si l'utilisateur a accès à un module spécifique en fonction de son groupe.
    """
    if user.is_superuser:
        return True

    # Récupérer les groupes de l'utilisateur
    user_groups = user.groups.all()

    # Vérifier si l'un des groupes de l'utilisateur a accès au module
    for group in user_groups:
        if group.permissions.filter(codename=module_name).exists():
            return True

    return False

def check_module_access(user, module_name):
    """
    Lève une exception si l'utilisateur n'a pas accès au module.
    """
    if not user_has_permission(user, module_name):
        raise PermissionDenied("Vous n'avez pas la permission d'accéder à ce module.")