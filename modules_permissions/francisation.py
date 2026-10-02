"""Noms de permissions en français.

Django crée pour chaque modèle quatre permissions — add, change, delete,
view — et leur donne un nom anglais figé dans le code : « Can add Patient ».
Ce nom n'est pas traduit, même avec LANGUAGE_CODE = 'fr-fr', et c'est lui que
l'on lit dans /admin/ en attribuant les droits d'un groupe ou d'un utilisateur.

Certains modèles déclaraient déjà leurs permissions à la main, en français,
avec `default_permissions = ()`. Faire de même pour tous les modèles voulait
dire toucher chaque Meta et produire une migration par application. On
renomme plutôt en base, après chaque `migrate` : les permissions créées par
un nouveau modèle sont francisées dès leur création, et seules celles qui
portent encore le nom anglais de Django sont touchées — un nom écrit à la
main n'est jamais réécrit.

Le codename ne change pas : `perms.patients.add_patient` et
`has_perm('patients.add_patient')` continuent de fonctionner.
"""

import re

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS
from django.utils import translation

# « Peut créer : rendez-vous » plutôt que « Peut créer un rendez-vous » :
# Django ignore le genre du modèle (un patient, une chambre), et le pluriel
# qu'il déduit faute de verbose_name_plural est souvent faux (« rendez-vouss »).
# La forme avec deux-points reste juste dans tous les cas.
GABARITS = {
    'add': 'Peut créer : {}',
    'change': 'Peut modifier : {}',
    'delete': 'Peut supprimer : {}',
    'view': 'Peut consulter : {}',
}

NOM_ANGLAIS = re.compile(r'^Can (add|change|delete|view) (.+)$')

# Permission.name : max_length=255.
LONGUEUR_MAX = 255


def _minuscule_initiale(texte):
    """« Besoins d'achat » → « besoins d'achat », mais « VIH » reste « VIH »."""
    if len(texte) > 1 and texte[1].isupper():
        return texte
    return texte[:1].lower() + texte[1:]


def nom_francais(action, modele, nom_anglais_objet):
    """Le nom français d'une permission par défaut.

    `modele` peut être None : le type de contenu d'un modèle supprimé du code
    reste en base, on se rabat alors sur le nom lu dans le libellé anglais.
    """
    if modele is not None:
        objet = str(modele._meta.verbose_name)
    else:
        objet = nom_anglais_objet
    return GABARITS[action].format(_minuscule_initiale(objet))[:LONGUEUR_MAX]


def franciser_permissions(using=DEFAULT_DB_ALIAS):
    """Renomme les permissions qui portent encore le nom anglais de Django.

    Retourne le nombre de permissions renommées.
    """
    from django.contrib.auth.models import Permission

    renommees = 0
    # verbose_name_plural est souvent paresseux (gettext_lazy) : sans langue
    # active, Django rendrait « Users » au lieu de « Utilisateurs ».
    with translation.override(settings.LANGUAGE_CODE):
        permissions = (
            Permission.objects.using(using)
            .filter(name__startswith='Can ')
            .select_related('content_type')
        )
        for permission in permissions:
            correspondance = NOM_ANGLAIS.match(permission.name)
            if not correspondance:
                continue
            action, objet = correspondance.groups()
            nouveau = nom_francais(action, permission.content_type.model_class(), objet)
            if nouveau != permission.name:
                permission.name = nouveau
                permission.save(update_fields=['name'])
                renommees += 1
    return renommees


def franciser_apres_migration(sender, using=DEFAULT_DB_ALIAS, **kwargs):
    """Receveur de post_migrate.

    Branché sans `sender` : Django crée les permissions application par
    application, et celles d'une application listée après la nôtre dans
    INSTALLED_APPS n'existent pas encore quand notre propre signal part.
    La requête ne ramène rien une fois tout francisé : le coût est nul.
    """
    franciser_permissions(using=using)
