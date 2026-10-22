"""Repérer les dates de naissance qui n'en sont pas.

L'import convertit un âge en date à partir du jour où il tourne : « 34 ans »
importé le 1er octobre 2026 ressort « né le 01/10/1992 ». Un fichier de
48 000 lignes dépose donc 48 000 fiches au même jour et au même mois, et la
recherche de doublons y lit de vraies dates identiques.

Ces dates-là ne se reconnaissent pas une par une — rien ne distingue, sur une
fiche isolée, le 01/10/1992 inventé du 01/10/1992 véritable. Elles se
reconnaissent en masse : un jour/mois que porte une part anormale de la base.

Le jour retenu n'est pas écrit en dur. Chaque base a le sien, celui de son
dernier import — 30/09 ici, 01/10 là, 01/01 ailleurs — et une base peut en
porter plusieurs, un par import. La fonction ci-dessous les retrouve seule.

Elle vit hors de la migration qui l'emploie pour être éprouvée sans jouer de
migration.
"""

#: Part de la base à partir de laquelle un jour/mois devient suspect. Les
#: jours d'anniversaire se répartissent sur l'année : aucun n'approche 1 %.
PART_MINIMALE = 0.02

#: Plancher en nombre de fiches. Sur un fichier de 200 patients, 2 % font
#: quatre personnes — et quatre vrais anniversaires le même jour n'ont rien
#: d'anormal. En deçà, on ne coche rien : mieux vaut manquer une date inventée
#: que d'effacer la date exacte de quelqu'un.
PLANCHER = 30


def jours_par_defaut(comptes, total, part=PART_MINIMALE, plancher=PLANCHER):
    """Les (jour, mois) qu'une part anormale de la base porte.

    `comptes` : {(jour, mois): nombre de fiches}. `total` : le nombre de fiches
    datées sur lesquelles ces comptes ont été relevés.
    """
    if not total:
        return set()
    return {jour_mois for jour_mois, nombre in comptes.items()
            if nombre >= plancher and nombre / total >= part}


def comptes_par_centre(lignes):
    """Regroupe `(centre_id, jour, mois)` en {centre_id: {(jour, mois): n}}.

    Par centre, et non sur l'ensemble : deux centres importés des jours
    différents ont chacun leur date inventée, et un comptage global noierait
    celle du plus petit sous les fiches du plus gros.
    """
    comptes = {}
    for centre_id, jour, mois in lignes:
        comptes.setdefault(centre_id, {})
        cle = (jour, mois)
        comptes[centre_id][cle] = comptes[centre_id].get(cle, 0) + 1
    return comptes
