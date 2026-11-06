"""Lettrage des comptes de tiers, comme dans Sage 100.

Lettrer, c'est marquer d'une même lettre (A, B… Z, AA…) les lignes d'un
compte de tiers qui se soldent : une facture et ses règlements, une dette
fournisseur et son paiement. Ce qui reste sans lettre est ce qui reste dû —
c'est ce que montrent le grand livre et la balance des tiers.

Règles :

- seules les lignes d'écritures **validées**, sur un compte de classe 4, se
  lettrent : un brouillon peut encore disparaître ;
- les lignes lettrées ensemble ont le même compte général et le même compte
  tiers, et leurs débits égalent leurs crédits ;
- les lettres se suivent par compte général et compte tiers ;
- le lettrage automatique rapproche les lignes d'un même document : une
  facture patient, ses encaissements, avoirs, remboursements et refus
  d'assureur ; une facture fournisseur et ses règlements. Il ne lettre un
  document que s'il est soldé.
"""
from decimal import Decimal
from itertools import product
from string import ascii_uppercase

from django.db import transaction
from django.utils import timezone

from .models import LigneEcriture

ZERO = Decimal('0')


class ErreurLettrage(Exception):
    pass


def _lettres():
    """A, B… Z, AA, AB… ZZ, AAA… : la suite des lettres de Sage."""
    for longueur in range(1, 5):
        for lettres in product(ascii_uppercase, repeat=longueur):
            yield ''.join(lettres)


def _rang(lettre):
    return (len(lettre), lettre)


def prochaine_lettre(compte_id, compte_tiers_id):
    prises = set(LigneEcriture.objects.filter(compte_id=compte_id, compte_tiers_id=compte_tiers_id)
                 .exclude(lettre='').values_list('lettre', flat=True))
    derniere = max(prises, key=_rang) if prises else ''
    for lettre in _lettres():
        if _rang(lettre) > _rang(derniere):
            return lettre
    raise ErreurLettrage("Plus aucune lettre disponible sur ce compte.")


def lettrables():
    """Lignes qu'on peut lettrer : validées, sur un compte de tiers."""
    return LigneEcriture.objects.filter(ecriture__statut='validee', compte__numero__startswith='4')


def lettrer(lignes):
    """Lettre ensemble `lignes` (des LigneEcriture) ; rend la lettre."""
    lignes = list(lignes)
    if len(lignes) < 2:
        raise ErreurLettrage("Choisissez au moins deux lignes à lettrer.")
    ids = {l.pk for l in lignes}
    if lettrables().filter(pk__in=ids).count() != len(ids):
        raise ErreurLettrage("Seules les lignes d'écritures validées sur un compte de tiers (classe 4) se lettrent.")
    if len({(l.compte_id, l.compte_tiers_id) for l in lignes}) > 1:
        raise ErreurLettrage("Les lignes lettrées ensemble sont sur le même compte et le même compte tiers.")
    if any(l.lettre for l in lignes):
        raise ErreurLettrage("Une des lignes est déjà lettrée : délettrez-la d'abord.")
    debit = sum((l.debit for l in lignes), ZERO)
    credit = sum((l.credit for l in lignes), ZERO)
    if debit != credit:
        raise ErreurLettrage(f"Les lignes ne se soldent pas : débit {debit:,.0f} ≠ crédit {credit:,.0f}."
                             .replace(',', ' '))
    with transaction.atomic():
        lettre = prochaine_lettre(lignes[0].compte_id, lignes[0].compte_tiers_id)
        LigneEcriture.objects.filter(pk__in=ids).update(lettre=lettre, lettree_le=timezone.localdate())
    return lettre


def delettrer(compte_id, compte_tiers_id, lettre):
    """Retire une lettre ; rend le nombre de lignes délettrées."""
    if not lettre:
        return 0
    return (LigneEcriture.objects.filter(compte_id=compte_id, compte_tiers_id=compte_tiers_id, lettre=lettre)
            .update(lettre='', lettree_le=None))


# ─── Lettrage automatique ──────────────────────────────────────────────────────

def _documents(ecritures):
    """{écriture_id: clé du document} : « facture:12 » pour une facture
    patient et tout ce qui la solde, « ffo:3 » pour une facture fournisseur
    et ses règlements. Une contre-passation suit l'écriture qu'elle annule."""
    from facturation.models import Paiement
    from .models import Avoir, ReglementFournisseur, RejetAssurance

    par_nature = {}
    for e in ecritures:
        nature, _, pk = (e.origine or '').partition(':')
        if pk.isdigit():
            par_nature.setdefault(nature, set()).add(int(pk))
    factures = {}
    for nature, modele in (('paiement', Paiement), ('avoir', Avoir), ('remboursement', Avoir),
                           ('rejet', RejetAssurance)):
        ids = par_nature.get(nature)
        if ids:
            factures[nature] = dict(modele.all_objects.filter(pk__in=ids).values_list('pk', 'facture_id'))
    reglements = dict(ReglementFournisseur.all_objects.filter(pk__in=par_nature.get('reglement_fournisseur', ()))
                      .values_list('pk', 'facture_id'))

    def cle(e):
        nature, _, pk = (e.origine or '').partition(':')
        if not pk.isdigit():
            return None
        pk = int(pk)
        if nature == 'facture':
            return f'facture:{pk}'
        if nature in factures and pk in factures[nature]:
            return f'facture:{factures[nature][pk]}'
        if nature == 'facture_fournisseur':
            return f'ffo:{pk}'
        if nature == 'reglement_fournisseur' and pk in reglements:
            return f'ffo:{reglements[pk]}'
        return None

    cles = {e.pk: cle(e) for e in ecritures}
    for e in ecritures:
        if e.contre_passation_de_id:
            cles[e.pk] = cles.get(e.contre_passation_de_id) or f'ecriture:{e.contre_passation_de_id}'
    # Une écriture contre-passée sans document se solde avec sa contre-passation.
    for e in ecritures:
        if cles[e.pk] is None and any(x.contre_passation_de_id == e.pk for x in ecritures):
            cles[e.pk] = f'ecriture:{e.pk}'
    return cles


def lettrage_automatique(compte=None, compte_tiers=None):
    """Lettre chaque document soldé ; rend le nombre de lettres posées."""
    from .models import Ecriture
    qs = lettrables().filter(lettre='')
    if compte is not None:
        qs = qs.filter(compte=compte)
    if compte_tiers is not None:
        qs = qs.filter(compte_tiers=compte_tiers)
    lignes = list(qs.only('pk', 'compte_id', 'compte_tiers_id', 'debit', 'credit', 'ecriture_id', 'lettre'))
    ecritures = list(Ecriture.all_objects.filter(
        pk__in={l.ecriture_id for l in lignes} | set(
            Ecriture.all_objects.filter(contre_passation_de__in={l.ecriture_id for l in lignes})
            .values_list('pk', flat=True)))
        .only('pk', 'origine', 'contre_passation_de_id'))
    # La contre-passation et son original : il faut aussi connaître l'original.
    originaux = {e.contre_passation_de_id for e in ecritures if e.contre_passation_de_id} - {e.pk for e in ecritures}
    ecritures += list(Ecriture.all_objects.filter(pk__in=originaux).only('pk', 'origine', 'contre_passation_de_id'))
    documents = _documents(ecritures)
    groupes = {}
    for l in lignes:
        doc = documents.get(l.ecriture_id)
        if doc:
            groupes.setdefault((l.compte_id, l.compte_tiers_id, doc), []).append(l)
    posees = 0
    for groupe in groupes.values():
        debit = sum((l.debit for l in groupe), ZERO)
        if len(groupe) >= 2 and debit and debit == sum((l.credit for l in groupe), ZERO):
            lettrer(groupe)
            posees += 1
    return posees
