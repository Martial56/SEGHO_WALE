"""Tenir à jour la table des clés phonétiques.

La présélection des doublons compare des mots exacts. Une variante d'écriture
accompagnée d'un téléphone différent lui échappe donc, alors que le score la
reconnaîtrait : N'GESSAN N'DRISCA PRISCA et N'GUESSAN PRSICA, nées la même
année, ne partagent aucun mot entier et ne se croisaient jamais.

`doublons.cle_phonetique` sait rapprocher ces deux graphies depuis toujours,
mais elle n'intervenait qu'au moment de noter la ressemblance — trop tard,
puisque la paire n'était jamais présentée.

Ce module écrit donc ces clés en base, où la présélection peut les chercher.

Le module ne doit pas être renommé : la migration de données qui remplit la
table pour l'existant l'appelle par son nom. Même remarque que pour
`patients.dates_approximatives`. Si la fonction phonétique évolue, les clés
déjà écrites restent cohérentes tant qu'on relance `recalculer_doublons
--cles`, qui les régénère toutes.
"""

from django.utils.dateparse import parse_date

from .doublons import cle_phonetique, mots

#: Un mot plus court ne porte pas assez de matière pour être réduit : « AYA »
#: tient, « KA » rapprocherait n'importe quoi.
LONGUEUR_MINIMALE = 3

#: Les champs dont dépend une clé. Modifier une adresse ne change rien ici, et
#: ne doit donc déclencher aucun recalcul.
CHAMPS_SURVEILLES = ('nom', 'prenoms', 'date_naissance')


def cles(nom, prenoms):
    """Les clés phonétiques d'une identité, sans doublon."""
    trouvees = {cle_phonetique(m) for m in mots(nom) + mots(prenoms)
                if len(m) >= LONGUEUR_MINIMALE}
    return {c for c in trouvees if len(c) >= LONGUEUR_MINIMALE}


def annee_de(valeur):
    """L'année d'une date, quelle que soit sa forme.

    `Patient(date_naissance='1990-06-01')` est légal : Django ne convertit la
    chaîne qu'au passage en base, et l'attribut de l'instance en reste une
    jusqu'au rechargement. Lire `.year` dessus échouerait.
    """
    if not valeur:
        return None
    if isinstance(valeur, str):
        try:
            valeur = parse_date(valeur)
        except ValueError:          # bien formée mais impossible (30 février)
            return None
    return getattr(valeur, 'year', None)


def rafraichir(patients):
    """Réécrit les clés d'un lot de fiches, en deux requêtes.

    Supprimer puis réécrire plutôt que comparer l'existant : une fiche porte
    deux ou trois clés, le calcul de la différence coûterait plus que
    l'écriture.
    """
    from .models import ClePhonetique

    patients = [p for p in patients if p.pk]
    if not patients:
        return 0

    ClePhonetique.all_objects.filter(patient__in=patients).delete()
    lignes = [
        ClePhonetique(patient=p, cle=c, centre_id=p.centre_id,
                      annee=annee_de(p.date_naissance))
        for p in patients
        for c in cles(p.nom, p.prenoms)
    ]
    if lignes:
        ClePhonetique.all_objects.bulk_create(lignes, batch_size=2000)
    return len(lignes)


def doit_rafraichir(champs_modifies):
    """Faut-il réécrire les clés après cet enregistrement ?

    `champs_modifies` : les noms de champs touchés, ou None quand on l'ignore
    (création, ou `save()` sans `update_fields`) — auquel cas on réécrit.
    """
    if champs_modifies is None:
        return True
    return any(champ in champs_modifies for champ in CHAMPS_SURVEILLES)
