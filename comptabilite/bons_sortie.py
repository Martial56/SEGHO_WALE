"""
Bons de sortie de la petite caisse (et de toute caisse hors guichet).

Chez WALÉ, les dépenses en espèces sortent de la petite caisse, et c'est
l'assistant comptable qui saisit les bons. Le circuit suit la demande du
comptable :

1. **Saisie** du bon (brouillon, modifiable) : motif, objet, bénéficiaire,
   montant, justificatif.
2. **Validation** par l'assistant lui-même : le bon ne bouge plus. Il est
   refusé s'il dépasse ce que contient la caisse.
3. **Équilibrage** : l'écriture est proposée d'après le bon — au débit le
   compte du motif, le libellé et le montant ; au crédit le compte de la
   caisse — rien n'est ressaisi. On peut changer de compte ou répartir la
   dépense, mais le total reste celui du bon et la caisse est créditée du
   montant du bon. L'écriture va dans le journal de la caisse (CAISPC), en
   brouillon, et se valide au passage des écritures.

Les sorties faites par les caissières sur leur pochette (`SortieCaisse`,
comptabilite/caisse.py) restent à part : elles gardent le billetage de la
session juste.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import ecritures as moteur
from .models import BonSortie, CompteTresorerie, Ecriture

ZERO = Decimal('0')


class ErreurBon(Exception):
    """Refus d'une opération sur un bon de sortie, avec un message clair."""


def _francs(m):
    return f"{m:,.0f}".replace(',', ' ')


def caisses():
    """Caisses hors guichet où l'on saisit des bons (petite caisse…)."""
    return CompteTresorerie.objects.filter(type='caisse', actif=True).select_related('compte').order_by('libelle')


def bons_en_attente(caisse, sauf=None):
    """Montant des bons validés pas encore équilibrés : l'argent est sorti,
    l'écriture pas encore passée."""
    bons = BonSortie.all_objects.filter(caisse=caisse, statut='valide')
    if sauf is not None:
        bons = bons.exclude(pk=sauf.pk)
    origines = set(Ecriture.all_objects.filter(origine__startswith='bon_sortie:')
                   .values_list('origine', flat=True))
    return sum((b.montant for b in bons if b.origine not in origines), ZERO)


def disponible(caisse, jour=None, sauf=None):
    """Ce que contient la caisse : solde de son compte, moins les bons validés
    dont l'écriture n'est pas encore passée."""
    from .tresorerie import solde_comptable
    return solde_comptable(caisse.compte, jour) - bons_en_attente(caisse, sauf)


def _controler(caisse, motif, libelle, montant):
    if caisse is None or caisse.type != 'caisse':
        raise ErreurBon("Choisissez la caisse d'où sort l'argent.")
    if motif is None:
        raise ErreurBon("Choisissez le motif de la dépense.")
    if not (libelle or '').strip():
        raise ErreurBon("Précisez l'objet de la dépense.")
    if montant is None or montant <= 0:
        raise ErreurBon("Le montant du bon doit être positif.")


def enregistrer(par, caisse, date, motif, libelle, montant, beneficiaire='', justificatif=None,
                convention=None, bon=None):
    """Crée (ou modifie, tant qu'il est en brouillon) un bon de sortie."""
    _controler(caisse, motif, libelle, montant)
    if bon is not None and bon.statut != 'brouillon':
        raise ErreurBon("Seul un bon en brouillon se modifie.")
    bon = bon or BonSortie(cree_par=par)
    bon.caisse, bon.date, bon.motif = caisse, date, motif
    bon.libelle, bon.beneficiaire, bon.montant = libelle.strip(), (beneficiaire or '').strip(), montant
    bon.convention = convention
    if justificatif:
        bon.justificatif = justificatif
    bon.save()
    return bon


def valider(bon, par):
    """Le bon est arrêté : l'argent sort de la caisse. Vient l'équilibrage."""
    if bon.statut != 'brouillon':
        raise ErreurBon("Ce bon a déjà été validé ou annulé.")
    with transaction.atomic():
        bon = BonSortie.all_objects.select_for_update().get(pk=bon.pk)
        dispo = disponible(bon.caisse, bon.date, sauf=bon)
        if bon.montant > dispo:
            raise ErreurBon(f"La caisse {bon.caisse} ne contient que {_francs(max(dispo, ZERO))} F "
                            "selon les comptes : le bon ne peut pas dépasser ce montant.")
        bon.statut, bon.valide_par, bon.valide_le = 'valide', par, timezone.now()
        bon.save(update_fields=['statut', 'valide_par', 'valide_le'])
    return bon


def annuler(bon):
    """Un bon pas encore équilibré s'annule ; équilibré, son écriture doit
    d'abord disparaître (brouillon supprimé) ou être contre-passée."""
    if bon.statut == 'annule':
        raise ErreurBon("Ce bon est déjà annulé.")
    ecriture = bon.ecriture
    if ecriture is not None and ecriture.statut == 'validee' \
            and not hasattr(ecriture, 'contre_passee_par'):
        raise ErreurBon("L'écriture de ce bon est validée : contre-passez-la avant d'annuler le bon.")
    if ecriture is not None and ecriture.statut == 'brouillon':
        moteur.supprimer_brouillon(ecriture)
    bon.statut = 'annule'
    bon.save(update_fields=['statut'])
    return bon


def lignes_proposees(bon):
    """L'écriture d'équilibrage telle qu'elle découle du bon :
    [(compte, libellé, débit, crédit, tiers, convention)]."""
    charge = bon.motif.compte or moteur.compte('sortie_defaut')
    libelle = f'{bon.numero} — {bon.libelle}'
    return [(charge, libelle, bon.montant, ZERO, bon.beneficiaire, bon.convention),
            (bon.caisse.compte, libelle, ZERO, bon.montant, bon.beneficiaire, None)]


def journal_du_bon(bon):
    return moteur.journal_de_tresorerie(bon.caisse.compte)


def equilibrer(bon, lignes, par, valider_ecriture=False):
    """Passe l'écriture du bon. `lignes` : comme `creer_ecriture`. Le total
    doit être celui du bon, et la caisse créditée du montant du bon."""
    if bon.statut != 'valide':
        raise ErreurBon("Seul un bon validé s'équilibre.")
    if bon.ecriture is not None:
        raise ErreurBon("Ce bon est déjà équilibré.")
    caisse = bon.caisse.compte
    total = sum((l[2] or ZERO for l in lignes), ZERO)
    net_caisse = sum(((l[3] or ZERO) - (l[2] or ZERO) for l in lignes if l[0].pk == caisse.pk), ZERO)
    if net_caisse != bon.montant:
        raise ErreurBon(f"La caisse ({caisse.numero}) doit être créditée du montant du bon, "
                        f"{_francs(bon.montant)} F.")
    if total != bon.montant:
        raise ErreurBon(f"Le total de l'écriture ({_francs(total)} F) doit être celui du bon "
                        f"({_francs(bon.montant)} F).")
    with transaction.atomic():
        ecriture = moteur.creer_ecriture(journal_du_bon(bon), bon.date, f'Bon de sortie {bon.numero} — {bon.libelle}',
                                         lignes, piece=bon.numero, origine=bon.origine,
                                         centre=bon.centre, par=par)
        if valider_ecriture:
            moteur.valider([ecriture], par)
    bon._ecriture = ecriture
    return ecriture


def totaux(bons):
    return bons.aggregate(t=Sum('montant'))['t'] or ZERO
