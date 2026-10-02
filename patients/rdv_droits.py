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

`change_rendezvous` reste l'accès complet : qui l'avait garde tout, rien ne
change pour les comptes existants. Pour restreindre un compte à une étape, il
faut donc lui retirer `change_rendezvous` et lui donner la permission de
l'étape.

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


def _a(user, permission):
    return user.has_perm(PERMISSION_COMPLETE) or user.has_perm(permission)


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
