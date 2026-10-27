"""
Tiers payants (lot 6) : ce que doivent les assurances et mutuelles.

Une facture d'un patient assuré se partage en deux : la part patient, payée à
la caisse, et la part assurance (`Facture.montant_assurance`), due par
l'assureur. Le patient qui a réglé sa part repart avec ses produits et son
soin démarre (voir `Facture.reglee_par_le_patient`) ; la facture n'est
« payée » que lorsque l'assureur a réglé la sienne.

Le parcours :
1. les factures s'accumulent en créances sur l'assureur ;
2. on les regroupe dans un **bordereau** (une période, un assureur) qu'on lui
   envoie ;
3. son **règlement** est réparti sur les factures — celles du bordereau, ou
   les plus anciennes — sous forme de paiements « Assurance » qui soldent leur
   part.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

ZERO = Decimal('0')


class ErreurAssurance(Exception):
    """Refus d'une opération sur les tiers payants, avec un message clair."""


def factures_assurees(assurance=None):
    """Factures (hors brouillons et annulées) portant une part assurance."""
    from facturation.models import Facture
    qs = (Facture.objects.filter(assurance__isnull=False, montant_assurance__gt=0)
          .exclude(statut__in=['brouillon', 'annulee'])
          .select_related('patient', 'assurance', 'bordereau_assurance').order_by('date_emission', 'pk'))
    if assurance is not None:
        qs = qs.filter(assurance=assurance)
    return qs


def creances(assurance=None):
    """Factures dont l'assureur doit encore quelque chose : [(facture, reste)]."""
    resultat = []
    for f in factures_assurees(assurance):
        reste = f.reste_assurance
        if reste > 0:
            resultat.append((f, reste))
    return resultat


def synthese_par_assureur():
    """Par assureur : nombre de factures, dû, dont pas encore sur un bordereau."""
    from patients.models import Assurance
    lignes = {}
    for f, reste in creances():
        l = lignes.setdefault(f.assurance_id, {'assurance': f.assurance, 'nb': 0, 'du': ZERO,
                                               'hors_bordereau': ZERO, 'nb_hors_bordereau': 0})
        l['nb'] += 1
        l['du'] += reste
        if not f.bordereau_assurance_id:
            l['hors_bordereau'] += reste
            l['nb_hors_bordereau'] += 1
    for a in Assurance.objects.filter(actif=True):
        lignes.setdefault(a.pk, {'assurance': a, 'nb': 0, 'du': ZERO, 'hors_bordereau': ZERO,
                                 'nb_hors_bordereau': 0})
    return sorted(lignes.values(), key=lambda l: (-l['du'], l['assurance'].nom))


# ─── Bordereaux ────────────────────────────────────────────────────────────────

def a_bordereauter(assurance, debut, fin):
    """Factures de l'assureur sur la période, non encore envoyées, avec un reste dû."""
    return [f for f in factures_assurees(assurance)
            .filter(bordereau_assurance__isnull=True, date_emission__date__range=[debut, fin])
            if f.reste_assurance > 0]


def preparer_bordereau(assurance, debut, fin, par):
    from .models import BordereauAssurance
    factures = a_bordereauter(assurance, debut, fin)
    if not factures:
        raise ErreurAssurance(f"Aucune facture de {assurance} à envoyer sur cette période.")
    with transaction.atomic():
        bordereau = BordereauAssurance.objects.create(assurance=assurance, date_debut=debut, date_fin=fin,
                                                      cree_par=par)
        for f in factures:
            f.bordereau_assurance = bordereau
            f.save(update_fields=['bordereau_assurance'])
    return bordereau


def contenu_bordereau(bordereau):
    lignes = []
    for f in bordereau.factures.select_related('patient').order_by('date_emission'):
        lignes.append({'facture': f, 'part': f.part_assurance, 'reste': f.reste_assurance})
    return {'lignes': lignes, 'total': sum((l['part'] for l in lignes), ZERO),
            'reste': sum((l['reste'] for l in lignes), ZERO)}


def marquer_envoye(bordereau, jour=None):
    if bordereau.statut != 'prepare':
        raise ErreurAssurance("Ce bordereau a déjà été envoyé.")
    bordereau.statut = 'envoye'
    bordereau.date_envoi = jour or timezone.localdate()
    bordereau.save(update_fields=['statut', 'date_envoi'])


def retirer_du_bordereau(bordereau, facture):
    """Une facture envoyée par erreur sort du bordereau, tant qu'il n'est pas envoyé."""
    if bordereau.statut != 'prepare':
        raise ErreurAssurance("Un bordereau envoyé ne se modifie plus.")
    if facture.bordereau_assurance_id != bordereau.pk:
        raise ErreurAssurance("Cette facture n'est pas sur ce bordereau.")
    facture.bordereau_assurance = None
    facture.save(update_fields=['bordereau_assurance'])


# ─── Règlements ────────────────────────────────────────────────────────────────

def repartition(assurance, montant, bordereau=None):
    """Comment un règlement se répartit : [(facture, montant affecté)].

    Sur les factures du bordereau s'il est donné, sinon sur toutes les créances
    de l'assureur, des plus anciennes aux plus récentes.
    """
    if bordereau is not None:
        candidates = [(f, f.reste_assurance) for f in bordereau.factures.order_by('date_emission', 'pk')]
    else:
        candidates = creances(assurance)
    restant, affectations = montant, []
    for facture, reste in candidates:
        if restant <= 0:
            break
        part = min(reste, restant)
        if part > 0:
            affectations.append((facture, part))
            restant -= part
    return affectations, restant


def enregistrer_reglement(assurance, montant, jour, mode, par, reference='', bordereau=None, observation=''):
    from facturation.models import Paiement
    from .models import ReglementAssurance

    if montant <= 0:
        raise ErreurAssurance("Le montant du règlement doit être positif.")
    if bordereau is not None and bordereau.assurance_id != assurance.pk:
        raise ErreurAssurance("Ce bordereau est celui d'un autre assureur.")
    affectations, excedent = repartition(assurance, montant, bordereau)
    if excedent > 0:
        du = montant - excedent
        raise ErreurAssurance(
            f"Le règlement dépasse ce que doit {assurance} "
            f"({du:,.0f} F{' sur ce bordereau' if bordereau else ''}). "
            "Vérifiez le montant, ou enregistrez-le sans bordereau.".replace(',', ' '))
    with transaction.atomic():
        reglement = ReglementAssurance.objects.create(
            assurance=assurance, bordereau=bordereau, date=jour, montant=montant, mode=mode,
            reference=reference, observation=observation, cree_par=par)
        for facture, part in affectations:
            Paiement.objects.create(
                facture=facture, montant=part, mode_paiement='assurance', reglement_assurance=reglement,
                reference=reference or reglement.numero, notes=f'Règlement {reglement.numero}',
                recu_par=par, centre=facture.centre)
            facture.montant_paye = (facture.montant_paye or ZERO) + part
            if facture.montant_paye + (facture.montant_perte or ZERO) >= facture.montant_total:
                facture.statut = 'payee'
            facture.save(update_fields=['montant_paye', 'statut'])
        for b in {f.bordereau_assurance for f, _ in affectations if f.bordereau_assurance_id}:
            reste = contenu_bordereau(b)['reste']
            b.statut = 'regle' if reste <= 0 else 'regle_partiel'
            b.save(update_fields=['statut'])
    return reglement, affectations


# ─── Balance âgée ──────────────────────────────────────────────────────────────

TRANCHES = [(30, '0-30 j'), (60, '31-60 j'), (90, '61-90 j'), (None, '+90 j')]


def balance_agee(fin):
    """Par assureur : ce qui reste dû, réparti par ancienneté de la facture."""
    lignes = {}
    for f, reste in creances():
        emise = timezone.localtime(f.date_emission).date()
        if emise > fin:
            continue
        age = (fin - emise).days
        rang = next(i for i, (limite, _) in enumerate(TRANCHES) if limite is None or age <= limite)
        l = lignes.setdefault(f.assurance_id, {'assurance': f.assurance, 'tranches': [ZERO] * len(TRANCHES)})
        l['tranches'][rang] += reste
    return sorted(lignes.values(), key=lambda l: l['assurance'].nom)


# ─── Refus de l'assureur (lot 7) ───────────────────────────────────────────────

def rejeter(facture, montant, decision, motif, jour, par):
    """L'assureur refuse tout ou partie de sa part sur une facture.

    - 'patient' : la somme passe à la charge du patient — la part assurance
      diminue d'autant, la part patient augmente ;
    - 'perte' : la somme est abandonnée — la facture est soldée sans
      encaissement, et la perte est comptabilisée.
    """
    from .models import RejetAssurance
    if decision not in dict(RejetAssurance.DECISION):
        raise ErreurAssurance("Décision inconnue.")
    if not motif.strip():
        raise ErreurAssurance("Indiquez le motif du refus de l'assureur.")
    reste = facture.reste_assurance
    if montant <= 0 or montant > reste:
        raise ErreurAssurance(f"Le montant refusé doit être compris entre 1 et {reste:,.0f} F "
                              "(ce que l'assureur doit encore sur cette facture).".replace(',', ' '))
    with transaction.atomic():
        rejet = RejetAssurance.objects.create(facture=facture, assurance=facture.assurance, date=jour,
                                              montant=montant, decision=decision, motif=motif.strip(),
                                              cree_par=par, centre=facture.centre)
        if decision == 'patient':
            facture.montant_assurance -= montant
        else:
            facture.montant_perte = (facture.montant_perte or ZERO) + montant
        solde = facture.montant_total - (facture.montant_paye or ZERO) - (facture.montant_perte or ZERO)
        facture.statut = 'payee' if solde <= 0 else 'emise'
        facture.save(update_fields=['montant_assurance', 'montant_perte', 'statut'])
        if facture.bordereau_assurance_id:
            b = facture.bordereau_assurance
            if b.statut != 'prepare':
                b.statut = 'regle' if contenu_bordereau(b)['reste'] <= 0 else 'regle_partiel'
                b.save(update_fields=['statut'])
    return rejet
