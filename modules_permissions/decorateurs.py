"""Verrou d'accès à un module.

Les modules (modules_permissions.Module) décidaient jusqu'ici de ce qui
s'affiche — cartes du tableau de bord, barres de navigation — sans jamais
verrouiller une URL. Une personne qui n'avait pas le module Gynécologie ne
voyait pas sa carte, mais entrait dans ses pages en tapant l'adresse.

`module_requis` referme cet écart pour les vues qu'on décide de protéger. Il
s'appuie sur `get_user_modules`, donc sur les mêmes données que l'affichage :
attribuer le module dans /admin/ suffit, il n'y a pas de seconde liste à tenir.

    @login_required(login_url='login')
    @module_requis('gynecologie')
    def gynecologie_list(request): ...

À ne pas confondre avec les permissions Django, qui répondent à une autre
question : le module dit « cette personne travaille-t-elle ici ? », la
permission dit « a-t-elle le droit de faire ceci ? ». Les deux se cumulent.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import get_user_modules


def utilisateur_a_module(user, code):
    """Cet utilisateur a-t-il accès au module ? Les superusers, toujours."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return get_user_modules(user).filter(code=code).exists()


def module_requis(code):
    """Refuse la vue à qui n'a pas le module — 403, donc notre page d'erreur."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not utilisateur_a_module(request.user, code):
                raise PermissionDenied
            return vue(request, *args, **kwargs)
        return enveloppe
    return decorateur
