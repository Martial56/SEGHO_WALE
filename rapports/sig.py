"""
Rapport SIG : les données du rapport mensuel de médecine générale
(med_generale.py), présentées au format du SIG — une colonne par tranche
d'âge, sans distinction de sexe, puis TOTAL et CAS REFERES :

    0-11 mois | 1-4 ans | 5-9 ans | 10-14 ans | 15-19 ans | 20-24 ans |
    25-49 ans | 50 ans et plus | TOTAL | CAS REFERES

Les comptages sont ceux de la fiche de médecine générale, lus par
`collecter_med_generale` : même source (registre curatif du département
'medg'), mêmes règles, mêmes lignes dans le même ordre (FICHE_A / FICHE_B /
FICHE_C, pathologies hors fiche à la suite de leur catégorie). Seule change la
présentation : chaque case additionne F et M.

Les IST (section C) sont ventilées sur les tranches générales, et non plus sur
celles de la fiche papier (0-28 jours, puis 10 ans et plus) : un patient de
29 jours à 9 ans, sans colonne sur la fiche, a donc ici la sienne.

Cases grisées : une case n'est grisée que si elle l'est pour les deux sexes
sur la fiche (ex. « FE » avant 5 ans) ; une case grisée pour un seul sexe
(ex. écoulement urétral masculin, côté F) ne l'est plus, puisque F et M sont
réunis.
"""
from .fiche import ranger_selon_fiche
from .med_generale import (BRACKETS, FICHE_A, FICHE_B, FICHE_C, VBG_LIGNES,
                           VIH_LIGNES, collecter_med_generale)
from .periode import nom_du_mois


def _somme(grille, cle):
    """F + M d'une tranche."""
    return grille[cle]['F'] + grille[cle]['M']


def calculer_rapport_sig(annee, mois):
    donnees = collecter_med_generale(annee, mois)
    pathos = donnees['pathos']
    patho_grilles = donnees['patho_grilles']
    activites = donnees['activites']

    def _ligne(label, pks, opts):
        """Une case par tranche (F + M de toutes les pathologies `pks`), puis
        le total et les cas référés."""
        grises = opts.get('grises', frozenset())
        cellules = []
        for cle, _ in BRACKETS:
            val = sum(_somme(patho_grilles[pk]['grille'], cle) for pk in pks)
            grise = (cle, 'F') in grises and (cle, 'M') in grises
            cellules.append({'val': val, 'grise': grise})
        referes = sum(patho_grilles[pk]['referes']['F'] + patho_grilles[pk]['referes']['M']
                      for pk in pks)
        return {
            'label': label,
            'cellules': cellules,
            'total': sum(c['val'] for c in cellules),
            'referes': referes,
            'refere_noir': opts.get('refere_noir', False),
            'separateur': opts.get('separateur', False),
        }

    def _section(pages_fiche, pathos_cat):
        """Toutes les lignes d'une section, pages de la fiche mises bout à bout."""
        pages = ranger_selon_fiche(pages_fiche, pathos_cat, _ligne)
        return [ligne for page in pages for ligne in page]

    def _activite(label, cle):
        if cle is None:  # pas de champ dans le registre : à remplir à la main
            return {'label': label, 'cellules': None, 'total': None}
        cellules = [_somme(activites[cle], b) for b, _ in BRACKETS]
        return {'label': label, 'cellules': cellules, 'total': sum(cellules)}

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': nom_du_mois(annee, mois),
        'brackets': BRACKETS,
        'activites_lignes': [
            _activite('Nombre de Nouveaux clients', 'nouveaux_clients'),
            _activite('Nombre de consultant', 'consultants'),
            _activite('Nombre de consultations', 'consultations'),
            _activite('Nombre de cas référés', 'referes'),
            _activite('Nombre de cas contre référés', None),
            _activite('Assurés', 'assures'),
        ],
        'infectieuses': _section(FICHE_A, pathos['infectieuse']),
        'non_infectieuses': _section(FICHE_B, pathos['non_infectieuse']),
        'ist': _section([FICHE_C], pathos['ist']),
        'epidemiologie': _section([[]], pathos['epidemiologie']),
        'milda': donnees['milda'],
        'vih_lignes': VIH_LIGNES,
        'vbg_lignes': VBG_LIGNES,
    }
