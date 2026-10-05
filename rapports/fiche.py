"""
Rangement des pathologies du catalogue selon la disposition d'une fiche papier
(voir med_generale.py et gynecologie.py).

Une fiche est une liste de pages, chaque page une liste de lignes
(libellé imprimé, alias du catalogue, options). Chaque ligne est rapprochée
des pathologies du catalogue par nom normalisé (sans accents, casse, espaces
ni ponctuation) ou par l'un de ses alias : plusieurs entrées du catalogue
peuvent alimenter la même ligne (doublons de saisie, variantes), et une ligne
de la fiche reste affichée même sans pathologie correspondante. Les
pathologies hors fiche sont ajoutées après la dernière ligne de la catégorie,
dans l'ordre reçu (trier par pk pour l'ordre de création).
"""
import re
import unicodedata


def cle_nom(nom):
    """Nom normalisé pour le rapprochement fiche ↔ catalogue
    (« Cas dePaludisme simple » == « Cas de paludisme simple »)."""
    nom = (nom or '').lower().replace('œ', 'oe').replace('æ', 'ae')
    nom = unicodedata.normalize('NFKD', nom)
    nom = ''.join(c for c in nom if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', nom)


def ranger_selon_fiche(pages_fiche, pathos, construire_ligne):
    """Pages de lignes prêtes à rendre. `construire_ligne(label, pks, opts)`
    fabrique une ligne à partir des pk des pathologies qui l'alimentent ;
    les lignes hors fiche reçoivent opts={'hors_fiche': True}.

    Une ligne de la dernière page marquée opts={'en_dernier': True} (ligne
    « Autres … » de fin de tableau) reste en bas : les lignes hors fiche
    s'insèrent avant elle."""
    par_cle = {}
    for p in pathos:
        par_cle.setdefault(cle_nom(p.nom), []).append(p)
    utilisees = set()
    pages = []
    for page in pages_fiche:
        lignes = []
        position_fin = None
        for label, alias, opts in page:
            pks = []
            for cle in dict.fromkeys(cle_nom(n) for n in [label, *alias]):
                if cle not in utilisees:
                    utilisees.add(cle)
                    pks += [p.pk for p in par_cle.get(cle, [])]
            if opts.get('en_dernier') and position_fin is None:
                position_fin = len(lignes)
            lignes.append(construire_ligne(label, pks, opts))
        pages.append(lignes)
    hors_fiche = [
        construire_ligne(groupe[0].nom, [p.pk for p in groupe], {'hors_fiche': True})
        for cle, groupe in par_cle.items() if cle not in utilisees
    ]
    if position_fin is None:
        position_fin = len(pages[-1])
    pages[-1][position_fin:position_fin] = hors_fiche
    return pages
