"""Appliquer à une configuration la composition reçue de l'écran de réglage.

L'écran renvoie toute la fiche d'un coup, en JSON, plutôt qu'une mosaïque de
champs indexés : la structure est imbriquée et réordonnable, et l'ordre d'une
ligne est sa place dans la liste. Un formset aurait demandé de transporter des
numéros d'ordre que le navigateur venait de recalculer, et de les croire.

Tout ce qui entre ici vient du navigateur, donc rien n'est cru sur parole : les
libellés sont bornés, les choix vérifiés contre ceux du modèle, et les
prestations relues en base. Une prestation inconnue arrête l'enregistrement au
lieu d'être ignorée — si l'écran envoie un identifiant qui n'existe plus, c'est
qu'il travaille sur un catalogue périmé, et une ligne silencieusement vidée se
remarquerait des mois plus tard.
"""
import json

from .models import (BlocFicheSoins, ColonneFicheSoins, LigneFicheSoins)


class CompositionInvalide(Exception):
    """Ce que l'écran a envoyé ne décrit pas une fiche. Le message est montré
    tel quel à l'utilisateur, donc il est écrit pour lui."""


#: Les mêmes bornes que les champs du modèle. Les répéter ici permet de rendre
#: un message lisible au lieu d'une erreur de base de données.
LONGUEUR_TITRE_BLOC = 120
LONGUEUR_TITRE_COLONNE = 60
LONGUEUR_LIBELLE = 200

SOURCES = {code for code, _ in LigneFicheSoins.SOURCE}
ORIGINES = {code for code, _ in LigneFicheSoins.ORIGINE}


def _texte(valeur, quoi, longueur_max):
    if not isinstance(valeur, str) or not valeur.strip():
        raise CompositionInvalide(f"{quoi} ne peut pas être vide.")
    valeur = valeur.strip()
    if len(valeur) > longueur_max:
        raise CompositionInvalide(
            f"{quoi} dépasse {longueur_max} caractères.")
    return valeur


def _articles(identifiants, libelle):
    """Les prestations d'une ligne, relues en base."""
    from services.models import Articleservice

    if not isinstance(identifiants, list):
        raise CompositionInvalide(
            f"Les prestations de « {libelle} » sont illisibles.")
    if not identifiants:
        return []
    try:
        identifiants = {int(i) for i in identifiants}
    except (TypeError, ValueError):
        raise CompositionInvalide(
            f"Les prestations de « {libelle} » sont illisibles.")

    articles = list(Articleservice.objects.filter(pk__in=identifiants))
    if len(articles) != len(identifiants):
        raise CompositionInvalide(
            f"Une prestation de « {libelle} » n'existe plus au catalogue. "
            "Rechargez la page avant d'enregistrer.")
    return articles


def _ligne_valide(brute):
    if not isinstance(brute, dict):
        raise CompositionInvalide("Une ligne est illisible.")

    libelle = _texte(brute.get('libelle'), "Le libellé d'une ligne",
                     LONGUEUR_LIBELLE)
    source = brute.get('source')
    if source not in SOURCES:
        raise CompositionInvalide(
            f"« {libelle} » n'indique pas ce qu'elle compte.")
    origines = brute.get('origines')
    if origines not in ORIGINES:
        raise CompositionInvalide(
            f"« {libelle} » n'indique pas où chercher.")

    # Une ligne qui ne compte pas de prestations n'en garde aucune : les
    # laisser attachées donnerait à croire, dans l'écran, qu'elles entrent dans
    # le chiffre alors que la règle de la ligne les ignore.
    articles = (_articles(brute.get('articles', []), libelle)
                if source == 'articles' else [])
    return {'libelle': libelle, 'source': source, 'origines': origines,
            'articles': articles}


def _bloc_valide(brut):
    if not isinstance(brut, dict):
        raise CompositionInvalide("Un bloc est illisible.")
    titre = _texte(brut.get('titre'), "Le titre d'un bloc",
                   LONGUEUR_TITRE_BLOC)
    colonne = _texte(brut.get('colonne') or 'Nombre',
                     f"Le titre de colonne de « {titre} »",
                     LONGUEUR_TITRE_COLONNE)
    lignes = brut.get('lignes')
    if not isinstance(lignes, list):
        raise CompositionInvalide(f"Les lignes de « {titre} » sont illisibles.")
    return {'titre': titre, 'colonne': colonne,
            'lignes': [_ligne_valide(l) for l in lignes]}


def lire(charge_utile):
    """Valide la composition reçue et la rend sous forme de dictionnaires.

    Séparé de l'écriture à dessein : on refuse une composition bancale **avant**
    d'avoir effacé quoi que ce soit.
    """
    try:
        donnees = json.loads(charge_utile or '')
    except (TypeError, ValueError):
        raise CompositionInvalide("La composition envoyée est illisible.")

    if not isinstance(donnees, dict):
        raise CompositionInvalide("La composition envoyée est illisible.")
    blocs = donnees.get('blocs')
    if not isinstance(blocs, list) or not blocs:
        raise CompositionInvalide("La fiche doit garder au moins un bloc.")
    return [_bloc_valide(b) for b in blocs]


def appliquer(configuration, charge_utile):
    """Remplace la composition de `configuration` par celle reçue.

    On efface et on récrit plutôt que de rapprocher ligne à ligne : l'ordre est
    la position dans la liste, rien d'autre ne pointe sur ces lignes, et un
    rapprochement n'apporterait qu'un risque de laisser traîner une ligne que
    l'écran croit supprimée.
    """
    blocs = lire(charge_utile)

    configuration.blocs.all().delete()
    for rang_bloc, bloc in enumerate(blocs):
        enregistre = BlocFicheSoins.objects.create(
            configuration=configuration, titre=bloc['titre'], ordre=rang_bloc)
        ColonneFicheSoins.objects.create(
            bloc=enregistre, titre=bloc['colonne'], type_valeur='nombre',
            ordre=0)
        for rang, ligne in enumerate(bloc['lignes']):
            enregistree = LigneFicheSoins.objects.create(
                bloc=enregistre, libelle=ligne['libelle'], ordre=rang,
                source=ligne['source'], origines=ligne['origines'])
            if ligne['articles']:
                enregistree.articles.set(ligne['articles'])
    # `date_modification` est en `auto_now` : la configuration doit être
    # sauvée pour que « modifiée le… » suive les changements de ses blocs.
    configuration.save(update_fields=['date_modification'])
    return configuration


def composition(configuration):
    """La composition d'une configuration, telle que l'écran l'attend."""
    if configuration is None:
        return {'blocs': []}
    blocs = []
    for bloc in configuration.blocs.prefetch_related('colonnes',
                                                     'lignes__articles'):
        colonne = bloc.colonnes.first()
        blocs.append({
            'titre': bloc.titre,
            'colonne': colonne.titre if colonne else 'Nombre',
            'lignes': [{
                'libelle': ligne.libelle,
                'source': ligne.source,
                'origines': ligne.origines,
                'articles': [a.pk for a in ligne.articles.all()],
            } for ligne in bloc.lignes.all()],
        })
    return {'blocs': blocs}
