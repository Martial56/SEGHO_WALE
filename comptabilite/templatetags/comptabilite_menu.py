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



@register.simple_tag
def menu_tresorerie():
    """Comptes de trésorerie actifs, une entrée de rapprochement chacun."""
    from comptabilite.models import CompteTresorerie
    return list(CompteTresorerie.objects.filter(actif=True).order_by('libelle'))


# Écrans du module Caisse côté comptabilite (session, sorties, journées) ;
# toutes les routes de facturation en relèvent aussi, sauf la configuration
# des caisses, qui reste dans le module Comptabilité.
ECRANS_DE_CAISSE = {'ma_caisse', 'ouvrir', 'session', 'cloturer', 'valider', 'imprimer', 'sortie_creer',
                    'sortie_decider', 'sortie_annuler', 'journees', 'journee', 'journee_cloturer',
                    'journee_rouvrir'}


@register.simple_tag(takes_context=True)
def module_de_la_page(context):
    """« caisse » ou « comptabilite » : le module dont la barre s'affiche."""
    match = getattr(context.get('request'), 'resolver_match', None)
    if match is None:
        return 'comptabilite'
    nom = match.url_name or ''
    if match.namespace == 'facturation':
        return 'comptabilite' if nom.startswith('caisse') else 'caisse'
    if match.namespace == 'comptabilite' and nom in ECRANS_DE_CAISSE:
        return 'caisse'
    return 'comptabilite'
