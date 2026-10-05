"""Droits par étape du rendez-vous.

Une seule permission, `change_rendezvous`, ouvrait jadis toutes les étapes de
la fiche : impossible de laisser l'accueil confirmer sans le laisser aussi
mener la consultation. Chaque étape a désormais sa permission :

* Brouillon → Confirmé .......... `confirmer_rendezvous`   (accueil)
* Confirmé → En attente ......... `mettre_en_attente_rendezvous` (évaluation,
  choix du médecin — infirmier)
* En attente → En consultation
  → Terminé ..................... `consulter_rendezvous`   (médecin)
* Annuler ....................... `annuler_rendezvous`

`change_rendezvous` reste l'accès complet, mais seulement pour un compte qui
n'a **aucune** permission d'étape : les comptes existants gardent tout. Dès
qu'un compte reçoit une permission d'étape (par l'un de ses groupes ou en
direct), seules ses permissions d'étape comptent. Sans cela, un infirmier
qui tenait aussi `change_rendezvous` par un autre groupe voyait le bouton
« En consultation » malgré sa seule permission « mettre en attente ».

Les mêmes fonctions servent aux deux fiches (patients et gynécologie) et
gardent à la fois l'affichage des boutons et le POST : un bouton masqué ne
suffit pas, la vue refuse aussi l'écriture.
"""

PERMISSION_COMPLETE = 'patients.change_rendezvous'

CONFIRMER = 'patients.confirmer_rendezvous'
METTRE_EN_ATTENTE = 'patients.mettre_en_attente_rendezvous'
CONSULTER = 'patients.consulter_rendezvous'
ANNULER = 'patients.annuler_rendezvous'

#: Statut courant → permission qui autorise à enregistrer la fiche à ce stade
#: (champs, évaluation, registres). Un statut absent (annulé, absent) n'est
#: modifiable qu'avec l'accès complet.
PERMISSION_DE_L_ETAPE = {
    'planifie': CONFIRMER,
    'confirme': METTRE_EN_ATTENTE,
    'en_attente': CONSULTER,
    'en_consultation': CONSULTER,
    'termine': CONSULTER,
}

#: Valeur de `_action` → permission exigée pour ce changement d'état.
PERMISSION_DE_L_ACTION = {
    'confirmer': CONFIRMER,
    'en_attente': METTRE_EN_ATTENTE,
    'en_consultation': CONSULTER,
    'terminer': CONSULTER,
    'annuler': ANNULER,
    'annuler_confirme': ANNULER,
}


PERMISSIONS_D_ETAPE = (CONFIRMER, METTRE_EN_ATTENTE, CONSULTER, ANNULER)


def _acces_complet(user):
    """`change_rendezvous` ouvre tout, sauf à qui a des permissions d'étape."""
    return (user.has_perm(PERMISSION_COMPLETE)
            and not any(user.has_perm(p) for p in PERMISSIONS_D_ETAPE))


def _a(user, permission):
    return user.has_perm(permission) or _acces_complet(user)


def peut_modifier(user, rdv):
    """L'utilisateur peut-il enregistrer la fiche au statut actuel du RDV ?"""
    if rdv.statut == 'annule':
        return False
    permission = PERMISSION_DE_L_ETAPE.get(rdv.statut)
    if permission is None:
        return user.has_perm(PERMISSION_COMPLETE)
    return _a(user, permission)


def peut_faire(user, action):
    """L'utilisateur peut-il lancer ce changement d'état (`_action`) ?"""
    return _a(user, PERMISSION_DE_L_ACTION[action])


def est_un_changement_d_etat(action):
    return action in PERMISSION_DE_L_ACTION


def droits(user, rdv):
    """Booléens pour les templates : quels boutons afficher."""
    return {
        'modifier': peut_modifier(user, rdv),
        'confirmer': _a(user, CONFIRMER),
        'en_attente': _a(user, METTRE_EN_ATTENTE),
        'consulter': _a(user, CONSULTER),
        'annuler': _a(user, ANNULER) and rdv.statut != 'annule',
    }
