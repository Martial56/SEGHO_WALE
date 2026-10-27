"""
Financements (lot 5) : suivi des conventions, budget et fonds dédiés.

Le réalisé d'une convention se lit dans les écritures, par l'axe
« financement » (`LigneEcriture.convention`) : une dépense compte pour une
convention dès qu'une ligne de charge lui est imputée (sortie de caisse,
opération diverse). Brouillons compris : le suivi d'un projet doit voir une
dépense le jour où elle est faite, pas le jour où le comptable la valide.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from .models import Convention, Ecriture, LigneEcriture

ZERO = Decimal('0')


def _somme(qs, champ):
    return qs.aggregate(s=Sum(champ))['s'] or ZERO


def _lignes_convention(convention, debut=None, fin=None):
    qs = LigneEcriture.objects.filter(convention=convention)
    if debut:
        qs = qs.filter(ecriture__date__gte=debut)
    if fin:
        qs = qs.filter(ecriture__date__lte=fin)
    return qs


def _charges(convention, debut=None, fin=None):
    """Lignes de charge (classe 6) imputées à la convention, hors constitution
    des fonds dédiés : cette écriture déplace la ressource, elle ne dépense rien."""
    from .models import Correspondance
    qs = _lignes_convention(convention, debut, fin).filter(compte__numero__startswith='6')
    engagement = Correspondance.objects.filter(cle='engagement_fonds_dedies').values('compte_id').first()
    if engagement:
        qs = qs.exclude(compte_id=engagement['compte_id'])
    return qs


def depenses(convention, debut=None, fin=None):
    """Charges imputées à la convention, nettes des contre-passations."""
    qs = _charges(convention, debut, fin)
    return _somme(qs, 'debit') - _somme(qs, 'credit')


def suivi(convention, fin=None):
    """Accordé, reçu, dépensé et ce qu'il reste, budget ligne à ligne."""
    versements = convention.versements.all()
    dons = convention.dons.all()
    if fin:
        versements = versements.filter(date__lte=fin)
        dons = dons.filter(date__lte=fin)
    recu = _somme(versements, 'montant')
    dons_affectes = _somme(dons, 'montant')
    depense = depenses(convention, fin=fin)
    accorde = convention.montant_accorde

    lignes, rattache = [], ZERO
    charges = _charges(convention, fin=fin)
    for lb in convention.lignes_budget.select_related('compte'):
        qs = charges.filter(compte__numero__startswith=lb.compte.numero)
        realise = _somme(qs, 'debit') - _somme(qs, 'credit')
        rattache += realise
        lignes.append({'ligne': lb, 'prevu': lb.montant_prevu, 'realise': realise,
                       'reste': lb.montant_prevu - realise,
                       'taux': (realise * 100 / lb.montant_prevu) if lb.montant_prevu else None})
    prevu = sum((l['prevu'] for l in lignes), ZERO)
    return {
        'convention': convention, 'accorde': accorde, 'recu': recu, 'dons': dons_affectes,
        'ressources': recu + dons_affectes, 'depense': depense,
        'reste_a_recevoir': accorde - recu, 'reste_a_depenser': accorde - depense,
        'disponible': recu + dons_affectes - depense,
        'taux': (depense * 100 / accorde) if accorde else None,
        'lignes_budget': lignes, 'budget_prevu': prevu,
        'hors_budget': depense - rattache,
    }


# ─── Fonds dédiés ──────────────────────────────────────────────────────────────

def calcul_fonds_dedies(exercice):
    """Pour chaque convention : ressources affectées de l'exercice, dépenses
    imputées, et la part non utilisée qui devient fonds dédié."""
    resultats = []
    for convention in Convention.objects.select_related('bailleur').order_by('code'):
        lignes = _lignes_convention(convention, exercice.date_debut, exercice.date_fin)
        produits = lignes.filter(compte__numero__startswith='7')
        ressources = _somme(produits, 'credit') - _somme(produits, 'debit')
        depense = depenses(convention, exercice.date_debut, exercice.date_fin)
        if not ressources and not depense:
            continue
        resultats.append({'convention': convention, 'ressources': ressources, 'depenses': depense,
                          'fonds_dedies': max(ressources - depense, ZERO)})
    return resultats


def ecritures_fonds_dedies(exercice, par):
    """Écritures de fonds dédiés en brouillon : constitution à la clôture de
    l'exercice, reprise au premier jour du suivant.

    Rend (constitution, reprise) ; None quand il n'y a rien à constater ou que
    l'écriture existe déjà.
    """
    from . import ecritures as moteur
    a_reporter = [r for r in calcul_fonds_dedies(exercice) if r['fonds_dedies'] > 0]
    if not a_reporter:
        return None, None
    engagement = moteur.compte('engagement_fonds_dedies')
    fonds = moteur.compte('fonds_dedies')
    report = moteur.compte('report_fonds_dedies')
    od = moteur.journal('OD')

    constitution = reprise = None
    origine = f'fonds_dedies:{exercice.pk}'
    if not Ecriture.all_objects.filter(origine=origine).exists():
        lignes = []
        for r in a_reporter:
            c = r['convention']
            lignes.append((engagement, f'{c.code} — ressources non utilisées', r['fonds_dedies'], ZERO,
                           str(c.bailleur), c))
            lignes.append((fonds, f'{c.code} — fonds dédiés', ZERO, r['fonds_dedies'], str(c.bailleur), c))
        constitution = moteur.creer_ecriture(od, exercice.date_fin, f'Fonds dédiés — exercice {exercice}',
                                             lignes, origine=origine, par=par)
    origine = f'reprise_fonds_dedies:{exercice.pk}'
    if not Ecriture.all_objects.filter(origine=origine).exists():
        lendemain = exercice.date_fin + timedelta(days=1)
        lignes = []
        for r in a_reporter:
            c = r['convention']
            lignes.append((fonds, f'{c.code} — reprise des fonds dédiés', r['fonds_dedies'], ZERO,
                           str(c.bailleur), c))
            lignes.append((report, f'{c.code} — ressources reportées', ZERO, r['fonds_dedies'],
                           str(c.bailleur), c))
        reprise = moteur.creer_ecriture(od, lendemain, f'Reprise des fonds dédiés de {exercice}',
                                        lignes, origine=origine, par=par)
    return constitution, reprise


# ─── Budget annuel ─────────────────────────────────────────────────────────────

def budget_realise(exercice, fin):
    """Budget annuel et réalisé du début de l'exercice à `fin`, compte par compte."""
    from .models import LigneBudget
    lignes = []
    for lb in LigneBudget.objects.filter(exercice=exercice).select_related('compte'):
        qs = LigneEcriture.objects.filter(
            ecriture__in=Ecriture.objects.filter(date__range=[exercice.date_debut, fin]).values('pk'),
            compte__numero__startswith=lb.compte.numero)
        d, c = _somme(qs, 'debit'), _somme(qs, 'credit')
        realise = d - c if lb.compte.classe == '6' else c - d
        lignes.append({'ligne': lb, 'prevu': lb.montant, 'realise': realise, 'ecart': realise - lb.montant,
                       'taux': (realise * 100 / lb.montant) if lb.montant else None})
    return lignes
