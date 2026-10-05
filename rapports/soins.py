"""
Calculs pour la Fiche d'activité de SOINS (MO + Activités de soins infirmiers),
à partir des mêmes données que les rapports "Listing des mises en observation"
et "Listing des soins infirmiers" (voir rapports/registry.py).

Le tableau MO (âge × sexe) réutilise exactement le même calcul que le rapport
MO existant, et n'est pas configurable.

La partie « Activités de soins infirmiers », elle, ne vit plus dans ce fichier :
sa composition est en base (`rapports.models.ConfigurationFicheSoins`), semée
par migration avec les quinze lignes d'origine. Ce module ne fait plus que
compter ce que la configuration lui désigne.

Le gain n'est pas l'écran de réglage, c'est la disparition des noms en dur :
les lignes visaient les prestations **par leur nom**, si bien qu'un article
renommé faisait tomber la ligne à zéro sans un mot. Elles les visent désormais
par clé étrangère.
"""
import calendar
from datetime import date
from itertools import zip_longest

from .periode import nom_du_mois
from .registry import AGE_BRACKETS_MO, _age_bracket_mo, _facture_statut_hospitalisation


def _recap_mo(premier_jour, dernier_jour):
    from hospitalisation.models import Hospitalisation

    qs = Hospitalisation.objects.select_related('patient').filter(
        date_admission__date__gte=premier_jour, date_admission__date__lte=dernier_jour,
    )
    nb = {b: {'F': 0, 'M': 0} for b in AGE_BRACKETS_MO}
    heures = {b: {'F': 0.0, 'M': 0.0} for b in AGE_BRACKETS_MO}

    for h in qs:
        if _facture_statut_hospitalisation(h) != 'Payé':
            continue
        patient = h.patient
        ref = h.date_admission.date() if h.date_admission else None
        bracket = _age_bracket_mo(patient.date_naissance, ref)
        sexe = patient.sexe
        if not bracket or sexe not in ('F', 'M'):
            continue
        nb[bracket][sexe] += 1
        if h.duree_observation is not None:
            heures[bracket][sexe] += h.duree_observation / 3600

    colonnes = []
    total = {'nb_f': 0, 'nb_m': 0, 'h_f': 0.0, 'h_m': 0.0}
    for b in AGE_BRACKETS_MO:
        nb_f, nb_m = nb[b]['F'], nb[b]['M']
        h_f, h_m = round(heures[b]['F'], 1), round(heures[b]['M'], 1)
        total['nb_f'] += nb_f
        total['nb_m'] += nb_m
        total['h_f'] += h_f
        total['h_m'] += h_m
        colonnes.append({'label': b, 'nb_f': nb_f, 'nb_m': nb_m, 'h_f': h_f, 'h_m': h_m})
    total['h_f'] = round(total['h_f'], 1)
    total['h_m'] = round(total['h_m'], 1)
    return colonnes, total


#: Origines d'un acte de soin posé pendant une mise en observation. Les deux
#: comptent : l'application offre deux chemins pour poser un soin sur une MO —
#: le bouton « Ajouter un soin » (`soin`) et l'onglet des visites infirmières
#: (`visite_infirmiere`) — et n'écarter que l'un des deux revenait à ne rien
#: compter, le premier n'ayant jamais servi une seule fois.
SOURCES_SOIN_EN_MO = ('soin', 'visite_infirmiere')


def _compte_mo_avec_soin_facture(premier_jour, dernier_jour):
    """PERFUSION : pas d'article dédié au catalogue, donc comptée comme le
    nombre de mises en observation (Hospitalisation) admises dans le mois ayant
    reçu au moins un soin dont la facture est payée.

    Les deux conditions tiennent dans un seul `filter` à dessein : sur une
    relation multiple, Django les applique alors à la **même** ligne liée. En
    deux appels, une MO passerait avec un soin non facturé d'un côté et une
    toute autre ligne payée de l'autre.
    """
    from hospitalisation.models import Hospitalisation
    return Hospitalisation.objects.filter(
        date_admission__date__gte=premier_jour, date_admission__date__lte=dernier_jour,
        services_a_facturer__source__in=SOURCES_SOIN_EN_MO,
        services_a_facturer__facture__statut='payee',
    ).distinct().count()


def _compte_mo_simple(premier_jour, dernier_jour):
    """« Mise en Observation simple » : une MO pendant laquelle aucun soin n'a
    été posé — c'est exactement le complément de la ligne PERFUSION.

    La ligne visait l'article « MISE EN OBSERVATION (VENTE) », qui n'a jamais
    servi ; les mises en observation réelles portent « MISE EN OBSERVATION ».
    Elle affichait donc zéro quoi qu'il arrive. On ne compte plus un article
    mais les MO elles-mêmes, dont on écarte celles qui ont reçu un soin, par
    l'un ou l'autre des deux chemins de saisie.

    `exclude` sur une relation multiple écarte la MO dès qu'**une** de ses
    lignes porte une de ces origines, ce qui est bien la question posée : a-t-on
    posé un soin, oui ou non.

    « Payé » se juge comme dans le tableau MO du haut de la fiche, pour que les
    deux parties comptent les mêmes mises en observation.
    """
    from hospitalisation.models import Hospitalisation
    qs = (Hospitalisation.objects
          .filter(date_admission__date__gte=premier_jour,
                  date_admission__date__lte=dernier_jour)
          .exclude(services_a_facturer__source__in=SOURCES_SOIN_EN_MO))
    return sum(1 for h in qs if _facture_statut_hospitalisation(h) == 'Payé')


def _compte_articles(premier_jour, dernier_jour, articles, origines):
    """Combien de fois ces prestations ont été faites et payées dans le mois.

    `origines` dit où regarder. Les deux chemins existent vraiment et ne se
    recoupent pas : une prestation posée depuis le module Soins devient une
    `ProcedureSoin`, la même posée pendant une mise en observation devient une
    `ServiceAFacturer`. Ne regarder que le premier — ce que faisait la fiche —
    laissait la seconde facturée, payée, et comptée nulle part.

    Aucune prestation cochée donne zéro, pas un blanc : c'est bien un compte,
    et il vaut zéro. Le blanc, c'est `source='manuelle'`.
    """
    if not articles:
        return 0

    total = 0
    if origines in ('procedure', 'les_deux'):
        from soins.models import ProcedureSoin
        total += ProcedureSoin.objects.filter(
            facture__statut='payee',
            soin_type__in=articles,
            date__date__gte=premier_jour, date__date__lte=dernier_jour,
        ).count()
    if origines in ('mo', 'les_deux'):
        from hospitalisation.models import ServiceAFacturer
        # Une ligne sans date ne tombe dans aucun mois : elle ne peut pas être
        # comptée ici sans choisir arbitrairement à quel mois la rattacher.
        total += ServiceAFacturer.objects.filter(
            facture__statut='payee',
            service__in=articles,
            date__gte=premier_jour, date__lte=dernier_jour,
        ).count()
    return total


def _compte_ligne(ligne, articles, premier_jour, dernier_jour):
    """Le nombre d'une ligne, ou None pour une case à remplir à la main."""
    if ligne.source == 'manuelle':
        return None
    if ligne.source == 'mo_avec_soin':
        return _compte_mo_avec_soin_facture(premier_jour, dernier_jour)
    if ligne.source == 'mo_sans_soin':
        return _compte_mo_simple(premier_jour, dernier_jour)
    return _compte_articles(premier_jour, dernier_jour, articles,
                            ligne.origines)


#: Ce qu'on écrit sous le libellé des deux lignes qui ne comptent pas des
#: prestations : leur règle ne se lit pas dans une liste d'articles.
DETAIL_DES_SOURCES = {
    'mo_avec_soin': 'MO ayant reçu au moins un soin (apporté ou visite infirmière) payé',
    'mo_sans_soin': 'MO payée sans aucun soin',
}


def _detail_ligne(ligne, articles):
    """Le petit texte entre parenthèses sous le libellé.

    Il ne paraît que lorsqu'il apprend quelque chose : une ligne qui regroupe
    plusieurs prestations dit lesquelles. Répéter « Transfusion » sous
    « TRANSFUSION » n'apprendrait rien, d'où le silence sur les lignes à une
    seule prestation.
    """
    if ligne.source in DETAIL_DES_SOURCES:
        return DETAIL_DES_SOURCES[ligne.source]
    if len(articles) < 2:
        return None
    return ', '.join(a.nom.title() for a in articles)


def _rendre_bloc(bloc, premier_jour, dernier_jour):
    """Un bloc prêt à afficher : son titre, ses colonnes, ses lignes calculées.

    Chaque ligne porte autant de valeurs que le bloc a de colonnes. Il n'existe
    aujourd'hui qu'un type de colonne, « Nombre », donc une seule valeur — le
    compte de la ligne. C'est exactement la fiche d'origine ; la liste est là
    pour que croiser par sexe ou par âge, plus tard, n'oblige pas à tout
    reprendre.
    """
    colonnes = list(bloc.colonnes.all())
    lignes = []
    for ligne in bloc.lignes.all():
        articles = list(ligne.articles.all())
        nombre = _compte_ligne(ligne, articles, premier_jour, dernier_jour)
        lignes.append({
            'libelle': ligne.libelle,
            'detail': _detail_ligne(ligne, articles),
            'valeurs': [nombre for _ in colonnes] or [nombre],
        })
    return {
        'titre': bloc.titre,
        'colonnes': [{'titre': c.titre, 'type_valeur': c.type_valeur}
                     for c in colonnes] or [{'titre': 'Nombre',
                                             'type_valeur': 'nombre'}],
        'lignes': lignes,
    }


def _entetes(paire):
    """Les en-têtes d'un tableau, à plat : libellé puis colonnes, par bloc."""
    entetes = []
    for bloc in paire:
        entetes.append({'texte': bloc['titre'], 'est_libelle': True})
        entetes.extend({'texte': c['titre'], 'est_libelle': False}
                       for c in bloc['colonnes'])
    return entetes


def _rangees(paire):
    """Les rangées d'un tableau, à plat elles aussi.

    Le gabarit ne sait rien faire d'autre que dérouler des cellules : c'est ici
    qu'on décide de tout, y compris des trous. Les deux blocs d'origine n'ont
    pas le même nombre de lignes — huit à gauche, sept à droite — et le dernier
    rang de droite est une case vide, pas un zéro.

    Trois cellules différentes, et il faut bien les trois : une case **absente**
    ne s'écrit pas comme une case **à remplir à la main**, qui ne s'écrit pas
    comme un compte.
    """
    rangees = []
    for lignes in zip_longest(*[b['lignes'] for b in paire]):
        rangee = []
        for bloc, ligne in zip(paire, lignes):
            if ligne is None:
                rangee.append({'est_libelle': True, 'libelle': '', 'detail': None})
                rangee.extend({'est_libelle': False, 'presente': False}
                              for _ in bloc['colonnes'])
                continue
            rangee.append({'est_libelle': True, 'libelle': ligne['libelle'],
                           'detail': ligne['detail']})
            rangee.extend({'est_libelle': False, 'presente': True, 'valeur': v}
                          for v in ligne['valeurs'])
        rangees.append(rangee)
    return rangees


def _tableaux(blocs):
    """Les blocs mis **deux par rangée**, comme sur la feuille d'origine.

    « Soins » et « Autres soins à préciser » s'impriment côte à côte : c'est ce
    qui fait tenir la fiche sur une page. Un bloc ajouté en troisième position
    ouvre un second tableau en dessous, et s'y retrouve seul tant qu'un
    quatrième ne vient pas lui tenir compagnie.
    """
    return [{'entetes': _entetes(paire), 'rangees': _rangees(paire)}
            for paire in (blocs[i:i + 2] for i in range(0, len(blocs), 2))]


def calculer_rapport_soins(annee, mois, configuration=None):
    """La fiche d'un mois, selon une configuration.

    Sans configuration donnée, c'est le format officiel qui sert — celui que la
    migration de semis a posé, et que tout le monde voit tant qu'il n'a rien
    réglé. Un mois passé se rouvre tel qu'il était en repassant la
    configuration de l'époque.
    """
    from .models import ConfigurationFicheSoins

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])

    mo_colonnes, mo_total = _recap_mo(premier_jour, dernier_jour)

    if configuration is None:
        configuration = ConfigurationFicheSoins.officielle()

    blocs = []
    if configuration is not None:
        # `prefetch_related` plutôt que quinze allers-retours : les lignes et
        # leurs prestations sont lues en deux requêtes au lieu de trente.
        for bloc in configuration.blocs.prefetch_related(
                'colonnes', 'lignes__articles'):
            blocs.append(_rendre_bloc(bloc, premier_jour, dernier_jour))

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': nom_du_mois(annee, mois),
        'premier_jour': premier_jour,
        'dernier_jour': dernier_jour,
        'mo_colonnes': mo_colonnes,
        'mo_total': mo_total,
        'configuration': configuration,
        'blocs': blocs,
        'tableaux': _tableaux(blocs),
    }
