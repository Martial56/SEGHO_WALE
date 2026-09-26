"""Chercher des utilisateurs par permission plutôt que par nom de groupe.

`user.has_perm('app.code')` répond pour **un** utilisateur. Pour la question
inverse — « qui détient cette permission ? », posée quand il faut prévenir les
personnes concernées — Django n'offre rien : il faut remonter à la fois les
permissions accordées au groupe et celles accordées à la personne.

Le code écrivait `groups__name__in={'RH', 'Directeur', ...}`. Renommer un groupe
dans /admin/ coupait la notification sans un mot, et les noms attendus
n'existaient dans aucune base : personne n'était jamais prévenu.
"""
from django.contrib.auth.models import Permission, User
from django.db.models import Q


def utilisateurs_avec(code_permission):
    """Les utilisateurs actifs qui détiennent `app_label.codename`.

    Par le groupe ou en direct, les superutilisateurs compris — ils ont toutes
    les permissions, et `has_perm` le dit aussi.

    Le code est **toujours** qualifié par son app : deux applications peuvent
    porter le même codename (`can_creer_facture` existe sur `soins.Soin` et sur
    `hospitalisation.Hospitalisation`), et une recherche non qualifiée lèverait
    `MultipleObjectsReturned`.
    """
    app_label, codename = code_permission.split('.')
    permission = Permission.objects.filter(
        content_type__app_label=app_label, codename=codename).first()
    if permission is None:
        # Permission absente : seuls les superutilisateurs passent, ce que dit
        # aussi `has_perm`. Le cas arrive entre une migration et la suivante.
        return User.objects.filter(is_active=True, is_superuser=True)
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True)
        | Q(groups__permissions=permission)
        | Q(user_permissions=permission)
    ).distinct()
