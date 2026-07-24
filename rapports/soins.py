"""
Calculs pour la Fiche d'activité de SOINS (MO + Activités de soins infirmiers),
à partir des mêmes données que les rapports "Listing des mises en observation"
et "Listing des soins infirmiers" (voir rapports/registry.py).

Le tableau MO (âge × sexe) réutilise exactement le même calcul que le rapport
MO existant. Le tableau des soins infirmiers compte, par type de soin, les
procédures (soins.ProcedureSoin) dont la facture est payée — seuls les types
de soin qui ont un article correspondant dans le catalogue (services.
Articleservice) peuvent être comptés ; les autres sont laissés vides (case à
remplir à la main), comme pour le rapport maternité.
"""
import calendar
from datetime import date
from itertools import zip_longest

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


# ── Correspondance ligne de la fiche → article(s) du catalogue Soins ────────
# None = pas d'article correspondant en base : ligne laissée vide (à remplir
# à la main), comme les indicateurs sans champ du rapport maternité.
# PERFUSION est un cas particulier (voir _compte_mo_avec_soin_facture) : pas
# d'article "PERFUSION" au catalogue, mais compté quand même via les mises en
# observation ayant reçu au moins un soin apporté (services_a_facturer,
# source='soin') et facturé/payé.
SOINS = [
    ('PERFUSION', 'MO_AVEC_SOIN_FACTURE'),
    ('TRANSFUSION', ['TRANSFUSION']),
    ('PANSEMENT', ['PANSEMENT GRANDE PLAIE', 'PANSEMENT MOYENNE PLAIE', 'PANSEMENT PETITE PLAIE']),
    ("BAIN D'OREILLE", ["LAVAGE D'OREILLE"]),
    ('INJECTION EXTERNE', ['INJECTION EXTERNE']),
    ('INJECTION INTERNE', ['INJECTION INTERNE']),
    ('Mise en Observation simple', ['MISE EN OBSERVATION (VENTE)']),
    ('Suture', ['FIL + SUTURE']),
]

AUTRES_SOINS = [
    ('Petite chirurgie, circoncision masculine', ['CIRCONCISION']),
    ('Petite chirurgie, suture de plaie traumatique', ['SUTURE PLAIE TRAUMATIQUE']),
    ("Petite chirurgie, incision d'abcès", ["INCISION D'ABCÈS"]),
    ('Autres petites chirurgies', ['COUPURE DE FREIN DE LANGUE', 'DRAINAGE', 'PONCTION']),
    ('Oxygénation', ['OXYGENATION (DIX MINUTES)']),
    ('Nébulisateur', ['NEBULISATION']),
    ('Ongle incarné', ['ONGLE INCARNE']),
]


def _compte_mo_avec_soin_facture(premier_jour, dernier_jour):
    """PERFUSION : pas d'article dédié, donc compté comme le nombre de mises
    en observation (Hospitalisation) du mois ayant reçu au moins un soin
    apporté (services_a_facturer, source='soin') dont la facture est payée."""
    from hospitalisation.models import Hospitalisation
    return Hospitalisation.objects.filter(
        date_admission__date__gte=premier_jour, date_admission__date__lte=dernier_jour,
        services_a_facturer__source='soin',
        services_a_facturer__facture__statut='payee',
    ).distinct().count()


def _compte_soin(premier_jour, dernier_jour, noms_articles):
    if noms_articles == 'MO_AVEC_SOIN_FACTURE':
        return _compte_mo_avec_soin_facture(premier_jour, dernier_jour)
    if not noms_articles:
        return None
    from soins.models import ProcedureSoin
    return ProcedureSoin.objects.filter(
        facture__statut='payee',
        soin_type__nom__in=noms_articles,
        date__date__gte=premier_jour, date__date__lte=dernier_jour,
    ).count()


def _detail_ligne(noms_articles):
    """Petit texte affiché sous le libellé pour qu'on voie exactement quel(s)
    article(s) du catalogue sont regroupés dans ce chiffre (utile dès qu'une
    ligne agrège plusieurs articles, ex. PANSEMENT ou Autres petites chirurgies)."""
    if noms_articles == 'MO_AVEC_SOIN_FACTURE':
        return 'MO ayant reçu au moins un soin apporté facturé/payé'
    if not noms_articles:
        return None
    if len(noms_articles) == 1:
        return None
    return ', '.join(n.title() for n in noms_articles)


def calculer_rapport_soins(annee, mois):
    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])

    mo_colonnes, mo_total = _recap_mo(premier_jour, dernier_jour)

    soins = [
        {
            'label': label,
            'nombre': _compte_soin(premier_jour, dernier_jour, noms),
            'detail': _detail_ligne(noms),
        }
        for label, noms in SOINS
    ]
    autres_soins = [
        {
            'label': label,
            'nombre': _compte_soin(premier_jour, dernier_jour, noms),
            'detail': _detail_ligne(noms),
        }
        for label, noms in AUTRES_SOINS
    ]
    # Les deux colonnes de la fiche papier n'ont pas le même nombre de lignes
    # (8 soins vs 7 autres soins) : on les met côte à côte ici plutôt que
    # d'essayer de le faire dans le template (Django n'a pas de filtre zip).
    lignes_soins = list(zip_longest(soins, autres_soins))

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': calendar.month_name[mois].capitalize(),
        'premier_jour': premier_jour,
        'dernier_jour': dernier_jour,
        'mo_colonnes': mo_colonnes,
        'mo_total': mo_total,
        'lignes_soins': lignes_soins,
    }
