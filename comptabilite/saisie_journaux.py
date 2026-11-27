"""
Saisie des journaux, comme l'écran du même nom dans Sage 100.

- `periodes` : une ligne par journal et par mois de l'exercice (ACH janv.,
  ACH févr.… BQ CC janv.…), avec son état — vide, mouvementé, brouillons à
  valider, clôturé — et ses totaux. C'est la porte d'entrée de la saisie.
- `journal_du_mois` : le journal d'un mois ouvert — ses écritures et leurs
  lignes, les totaux, et pour un journal de trésorerie (caisse, banque) le
  solde de son compte au début, après chaque écriture et à la fin. Chaque
  écriture générée dit d'où elle vient : une remise montre sa caisse source,
  sa destination, le compte de virements internes et l'écriture de l'autre
  côté ; un bon de sortie, une journée de caisse renvoient à leur fiche.

La saisie elle-même passe par `ecritures.creer_ecriture`, qui refuse une
écriture déséquilibrée ou un mois clôturé.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from .cloture_journaux import mois_de
from .models import Ecriture, Journal, PeriodeCloturee

ZERO = Decimal('0')

ETATS = {'vide': 'Aucune écriture', 'mouvemente': 'Mouvementé', 'brouillon': 'Brouillons à valider',
         'cloture': 'Clôturé'}

# Filtre du bas de la liste, comme Sage (sans « imprimés », que SEGHO ne suit
# pas) : chaque choix garde les périodes dont l'état est dans l'ensemble.
FILTRES = {
    'ouverts': ('Ouverts', {'mouvemente', 'brouillon'}),
    'non_ouverts': ('Non ouverts', {'vide'}),
    'brouillons': ('Avec brouillons à valider', {'brouillon'}),
    'non_clotures': ('Non clôturés', {'vide', 'mouvemente', 'brouillon'}),
    'clotures': ('Clôturés', {'cloture'}),
}


def fin_du_mois(mois):
    suivant = date(mois.year + mois.month // 12, mois.month % 12 + 1, 1)
    return suivant - timedelta(days=1)


def mois_voisin(mois, pas):
    """Le 1er du mois précédent (pas = -1) ou suivant (pas = 1)."""
    m = mois.month - 1 + pas
    return date(mois.year + m // 12, m % 12 + 1, 1)


def periodes(exercice, code=None, mouvementes=False, filtre=None):
    """[{journal, mois, ecritures, brouillons, debit, cloture, etat, futur}]
    rangées comme Sage : par code de journal, puis par mois."""
    mois = mois_de(exercice)
    compteurs = {}
    for row in (Ecriture.objects.filter(exercice=exercice)
                .values('journal_id', 'date__year', 'date__month')
                .annotate(n=Count('pk', distinct=True),
                          b=Count('pk', filter=Q(statut='brouillon'), distinct=True),
                          d=Sum('lignes__debit'))):
        compteurs[(row['journal_id'], date(row['date__year'], row['date__month'], 1))] = row
    clotures = {(p.journal_id, p.mois): p for p in PeriodeCloturee.objects.filter(mois__in=mois)}
    utilises = {j for j, _ in compteurs}
    journaux = Journal.objects.filter(Q(actif=True) | Q(pk__in=utilises)).order_by('code')
    if code:
        journaux = journaux.filter(code=code)
    aujourdhui = timezone.localdate()
    lignes = []
    for j in journaux:
        for m in mois:
            row = compteurs.get((j.pk, m), {})
            n, b = row.get('n', 0), row.get('b', 0)
            if mouvementes and not n:
                continue
            cloture = clotures.get((j.pk, m))
            etat = 'cloture' if cloture else 'brouillon' if b else 'mouvemente' if n else 'vide'
            if filtre in FILTRES and etat not in FILTRES[filtre][1]:
                continue
            lignes.append({'journal': j, 'mois': m, 'ecritures': n, 'brouillons': b,
                           'debit': row.get('d') or ZERO, 'cloture': cloture, 'etat': etat, 'etat_libelle': ETATS[etat],
                           'futur': m > aujourdhui})
    return lignes


# ─── Origine des écritures générées ────────────────────────────────────────────

def _origines(ecritures):
    """{écriture.pk: {libelle, url, soeur}} pour les écritures générées dont la
    source a une fiche à ouvrir."""
    from .models import BonSortie, JourneeCaisse, RemiseBanque, SortieCaisse
    par_type = {}
    for e in ecritures:
        if e.origine and ':' in e.origine:
            genre, pk = e.origine.split(':', 1)
            if pk.isdigit():
                par_type.setdefault(genre, {})[e.pk] = int(pk)
    infos = {}

    remises_ids = set(par_type.get('remise_sortie', {}).values()) | set(par_type.get('remise_entree', {}).values())
    if remises_ids:
        from . import ecritures as moteur
        try:
            transit = moteur.compte('virement_interne').numero
        except moteur.ErreurCompta:
            transit = '58'
        remises = RemiseBanque.all_objects.select_related('caisse', 'compte_tresorerie').in_bulk(remises_ids)
        soeurs = {e.origine: e for e in Ecriture.all_objects.select_related('journal').filter(
            origine__in=[f'remise_{c}:{pk}' for pk in remises_ids for c in ('sortie', 'entree')])}
        for genre, autre in (('remise_sortie', 'remise_entree'), ('remise_entree', 'remise_sortie')):
            for epk, rpk in par_type.get(genre, {}).items():
                r = remises.get(rpk)
                if r is None:
                    continue
                infos[epk] = {'libelle': f"Remise {r.numero} : {r.caisse.nom} → {r.compte_tresorerie.libelle}, "
                                         f"via le compte {transit}",
                              'url': reverse('comptabilite:remises'), 'soeur': soeurs.get(f'{autre}:{rpk}')}

    bons = BonSortie.all_objects.in_bulk(set(par_type.get('bon_sortie', {}).values()))
    for epk, bpk in par_type.get('bon_sortie', {}).items():
        if bpk in bons:
            infos[epk] = {'libelle': f"Bon de sortie {bons[bpk].numero}",
                          'url': reverse('comptabilite:bon_sortie', args=[bpk])}

    journees = JourneeCaisse.all_objects.select_related('caisse').in_bulk(set(par_type.get('journee', {}).values()))
    for epk, jpk in par_type.get('journee', {}).items():
        if jpk in journees:
            j = journees[jpk]
            infos[epk] = {'libelle': f"Journée de caisse {j.caisse} du {j.date_journee:%d/%m/%Y}",
                          'url': reverse('comptabilite:journee', args=[jpk])}

    sorties = SortieCaisse.all_objects.in_bulk(set(par_type.get('sortie', {}).values()))
    for epk, spk in par_type.get('sortie', {}).items():
        if spk in sorties:
            infos[epk] = {'libelle': f"Sortie de caisse {sorties[spk].numero}",
                          'url': reverse('comptabilite:session', args=[sorties[spk].session_id])}
    return infos


# ─── Le journal d'un mois ──────────────────────────────────────────────────────

def journal_du_mois(journal, mois):
    """Écritures du journal sur le mois, totaux, et pour un journal de
    trésorerie le solde de son compte écriture après écriture."""
    from .tresorerie import solde_comptable
    fin = fin_du_mois(mois)
    ecritures = list(Ecriture.objects.filter(journal=journal, date__range=[mois, fin])
                     .select_related('contre_passation_de')
                     .prefetch_related('lignes__compte', 'lignes__compte_tiers')
                     .order_by('date', 'numero', 'pk'))
    origines = _origines(ecritures)
    compte = journal.compte_tresorerie
    solde = solde_comptable(compte, mois - timedelta(days=1)) if compte else None
    solde_debut = solde
    debit = credit = debit_valide = credit_valide = ZERO
    for e in ecritures:
        lignes = list(e.lignes.all())
        e.debit = sum((l.debit for l in lignes), ZERO)
        e.credit = sum((l.credit for l in lignes), ZERO)
        e.origine_info = origines.get(e.pk)
        debit, credit = debit + e.debit, credit + e.credit
        if e.statut == 'validee':
            debit_valide, credit_valide = debit_valide + e.debit, credit_valide + e.credit
        if compte:
            solde += sum((l.debit - l.credit for l in lignes if l.compte_id == compte.pk), ZERO)
            e.solde = solde
    resultat = {
        'ecritures': ecritures, 'debit': debit, 'credit': credit,
        'debit_valide': debit_valide, 'credit_valide': credit_valide,
        'brouillons': sum(1 for e in ecritures if e.statut == 'brouillon'),
        'compte': compte, 'solde_debut': solde_debut, 'solde_fin': solde,
        'cloture': PeriodeCloturee.objects.filter(journal=journal, mois=mois).select_related('cloturee_par').first(),
    }
    if compte:
        # Le compte a pu bouger dans un autre journal (une OD sur la caisse…).
        resultat['solde_compte'] = solde_comptable(compte, fin)
        resultat['autres_journaux'] = resultat['solde_compte'] - solde
    soldes = soldes_des_comptes({l.compte_id for e in ecritures for l in e.lignes.all()}, fin)
    for e in ecritures:
        for l in e.lignes.all():          # lignes préchargées : l'attribut reste
            l.solde_compte = soldes.get(l.compte_id, ZERO)
    return resultat


def soldes_des_comptes(comptes_ids, fin):
    """{pk du compte: solde (débit − crédit)} au `fin`, tous journaux, comme la
    case « Solde compte » de Sage pour la ligne sélectionnée."""
    from .ecritures import exclure_exercices_clos
    from .models import LigneEcriture
    if not comptes_ids:
        return {}
    qs = exclure_exercices_clos(LigneEcriture.objects.filter(
        compte_id__in=comptes_ids, ecriture__date__lte=fin,
        ecriture__in=Ecriture.objects.all().values('pk')), fin)
    return {r['compte_id']: (r['d'] or ZERO) - (r['c'] or ZERO)
            for r in qs.values('compte_id').annotate(d=Sum('debit'), c=Sum('credit'))}
