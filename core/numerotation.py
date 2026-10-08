"""Numéroter sans trou de mémoire : le rang suivant se déduit du plus haut posé.

Chaque entité principale porte un code lisible — « PAT202600423 »,
« LAB2026000017 » — fait d'un préfixe et d'un rang. Ce rang était obtenu en
comptant les lignes existantes, ce qui suppose qu'aucune ne disparaisse jamais.

Supprimer trois patients ramenait le compteur trois crans en arrière, et le code
calculé était déjà porté par un patient resté en base : l'enregistrement tombait
sur la contrainte d'unicité. Pire, il tombait encore à chaque tentative
suivante — le comptage ne pouvait plus rattraper son retard, et la création de
patients restait cassée jusqu'à une intervention. Le plus haut code attribué,
lui, ne recule pas quand on efface.

La boucle finale est la ceinture par-dessus les bretelles : deux guichets qui
enregistrent dans la même seconde lisent le même « dernier » et calculeraient le
même code. Elle ne remplace pas la contrainte d'unicité, qui reste le dernier
rempart, mais elle lui évite d'avoir à servir.
"""

from django.db.models.functions import Length


def prochain_code(manager, champ, prefixe, largeur):
    """Code suivant de la forme `prefixe` + rang cadré sur `largeur` chiffres.

    `manager` doit être celui qui voit **toutes** les lignes (`all_objects` sur
    les modèles cloisonnés par centre) : un gestionnaire filtré sur le centre
    actif rendrait un rang déjà pris dans l'autre centre.
    """
    deja_posees = manager.filter(**{f'{champ}__startswith': prefixe})

    # Tri par longueur avant le tri alphabétique : à largeur constante les deux
    # coïncident, mais une reprise de données ayant produit des rangs plus
    # courts mettrait « …9 » après « …10 » sur le seul ordre alphabétique.
    dernier = (deja_posees
               .order_by(Length(champ).desc(), f'-{champ}')
               .values_list(champ, flat=True)
               .first())

    rang = 1
    if dernier:
        try:
            rang = int(dernier[len(prefixe):]) + 1
        except ValueError:
            # Un code hors format : on repart du nombre de codes déjà posés, la
            # boucle ci-dessous se chargeant des collisions que cela provoque.
            rang = deja_posees.count() + 1

    code = f'{prefixe}{rang:0{largeur}d}'
    while manager.filter(**{champ: code}).exists():
        rang += 1
        code = f'{prefixe}{rang:0{largeur}d}'
    return code
