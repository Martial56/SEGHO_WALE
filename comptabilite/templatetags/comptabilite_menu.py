"""Le sous-menu « États » de la barre du module se construit depuis le
registre des états (comptabilite.etats.ETATS) : un état ajouté au registre
apparaît dans le menu, avec les mêmes droits que son écran."""
from django import template

from comptabilite.etats import ETATS, GROUPES, peut_voir

register = template.Library()


@register.simple_tag
def menu_etats(user):
    """[(titre du groupe, [(code, état)])] des états que l'utilisateur peut voir."""
    groupes = []
    for cle, titre in GROUPES:
        etats = [(code, e) for code, e in ETATS.items()
                 if e['groupe'] == cle and peut_voir(user, e)]
        if etats:
            groupes.append((titre, etats))
    return groupes
