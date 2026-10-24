"""
Écritures comptables automatiques (lot 3 du module Comptabilité).

Personne ne saisit d'écriture au guichet : chaque opération de facturation et
de caisse produit la sienne, en brouillon, puis le comptable la valide au
« passage des écritures ». Seules les opérations diverses (salaires, loyers,
régularisations…) se saisissent à la main.

| Événement                     | Journal       | Débit                         | Crédit                        |
|-------------------------------|---------------|-------------------------------|-------------------------------|
| Facture émise / payée         | VTE           | Patient (+ tiers payant), remises | Produit selon la nature de chaque ligne (prix plein) |
| Paiement                      | caisse / MM / BQ | Trésorerie du mode         | Patient                       |
| Avoir (annulation)            | VTE           | inverse de la facture         |                               |
| Remboursement                 | caisse / MM / BQ | Patient                    | Trésorerie                    |
| Sortie de caisse payée        | caisse        | Compte de charge du motif     | Caisse                        |
| Écart de clôture de session   | caisse        | Manquant / Caisse             | Caisse / Excédent             |

Aucun numéro de compte n'est écrit ici : tout passe par les correspondances
(`Correspondance`), modifiables à l'écran. Chaque écriture porte la clé de
son origine (« paiement:12 ») : relancer la génération ne double jamais rien.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Compte, Correspondance, Ecriture, Exercice, Journal, LigneEcriture

ZERO = Decimal('0')

# Journal de trésorerie selon le mode de paiement. Les espèces vont au journal
# de la caisse ; les modes qui ne sont pas de l'argent reçu (prise en charge
# d'une assurance, bon) passent en opérations diverses.
JOURNAL_DU_MODE = {'mobile_money': 'MM', 'cheque': 'BQ', 'virement': 'BQ',
                   'assurance': 'OD', 'bon': 'OD'}


class ErreurCompta(Exception):
    """Refus d'une opération comptable, avec un message pour l'utilisateur."""


# ─── Référentiel ───────────────────────────────────────────────────────────────

def compte(cle):
    corr = Correspondance.objects.select_related('compte').filter(cle=cle).first()
    if corr is None:
        raise ErreurCompta(f"Aucun compte n'est associé à « {cle} » "
                           "(Comptabilité → Configuration → Correspondances).")
    return corr.compte


def compte_de_caisse(caisse):
    """Sous-compte 571 de la caisse, créé à sa première écriture."""
    if caisse is None:
        return compte('caisse')
    cle = f'caisse:{caisse.code}'
    corr = Correspondance.objects.select_related('compte').filter(cle=cle).first()
    if corr:
        return corr.compte
    racine = compte('caisse').numero
    rang = 1
    while Compte.objects.filter(numero=f'{racine}{rang}').exists():
        rang += 1
    nouveau = Compte.objects.create(numero=f'{racine}{rang}', intitule=f'Caisse {caisse.nom}')
    Correspondance.objects.create(cle=cle, libelle=f'Caisse {caisse.nom}', compte=nouveau)
    return nouveau


def journal(code):
    j = Journal.objects.filter(code=code).first()
    if j is None:
        raise ErreurCompta(f"Le journal {code} n'existe pas.")
    return j


def journal_de_caisse(caisse):
    if caisse is None:
        return journal('CAI')
    existant = Journal.objects.filter(caisse=caisse).first()
    if existant:
        return existant
    code = f'CA-{caisse.code}'[:12]
    return Journal.objects.create(code=code, libelle=f'Caisse {caisse.nom}', type='caisse', caisse=caisse)


def exercice_pour(jour):
    """Exercice qui contient ce jour, créé (année civile) s'il n'existe pas."""
    exercice = Exercice.objects.filter(date_debut__lte=jour, date_fin__gte=jour).first()
    if exercice is None:
        exercice = Exercice.objects.create(libelle=str(jour.year), date_debut=date(jour.year, 1, 1),
                                           date_fin=date(jour.year, 12, 31))
    if exercice.statut != 'ouvert':
        raise ErreurCompta(f"L'exercice {exercice} est clôturé : aucune écriture au {jour:%d/%m/%Y}.")
    return exercice


def _jour(dt):
    return timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()


# ─── Création ──────────────────────────────────────────────────────────────────

def creer_ecriture(journal_, jour, libelle, lignes, piece='', origine=None, centre=None, par=None,
                   contre_passation_de=None):
    """Écriture en brouillon. `lignes` : [(compte, libellé, débit, crédit, tiers)].

    Les lignes à zéro sont écartées ; l'ensemble doit être équilibré.
    """
    lignes = [l for l in lignes if (l[2] or ZERO) or (l[3] or ZERO)]
    debit = sum((l[2] or ZERO for l in lignes), ZERO)
    credit = sum((l[3] or ZERO for l in lignes), ZERO)
    if len(lignes) < 2:
        raise ErreurCompta("Une écriture compte au moins deux lignes.")
    if debit != credit:
        raise ErreurCompta(f"Écriture déséquilibrée : débit {debit} ≠ crédit {credit}.")
    with transaction.atomic():
        ecriture = Ecriture.objects.create(
            journal=journal_, exercice=exercice_pour(jour), date=jour, libelle=libelle[:255],
            piece=piece[:60], origine=origine, centre=centre, cree_par=par,
            contre_passation_de=contre_passation_de)
        LigneEcriture.objects.bulk_create([
            LigneEcriture(ecriture=ecriture, compte=c, libelle=(lib or libelle)[:255],
                          debit=d or ZERO, credit=cr or ZERO, tiers=(t or '')[:150])
            for c, lib, d, cr, t in lignes])
    return ecriture


def _deja(origine):
    return Ecriture.all_objects.filter(origine=origine).exists()


# ─── Facture et avoir ──────────────────────────────────────────────────────────

def nature_de_ligne(ligne, facture):
    from facturation.models import CATEGORIE_VERS_TYPE
    if ligne.produit_id:
        return 'pharmacie'
    article = ligne.article
    code = article.categorie.code if article and article.categorie_id else None
    nature = CATEGORIE_VERS_TYPE.get(code)
    if nature:
        return nature
    if facture.type_facture not in ('mixte', 'autre'):
        return facture.type_facture
    return 'autre'


def _nom_patient(facture):
    p = facture.patient
    return f'{p.nom} {p.prenoms} ({p.code_patient})'.strip()


def lignes_de_vente(facture):
    """Lignes de l'écriture de vente : produits au prix plein, remises à part,
    créance sur le patient (et l'assurance pour sa part)."""
    tiers = _nom_patient(facture)
    produits, remises = {}, ZERO
    for ligne in facture.lignes.select_related('article__categorie'):
        brut = (ligne.quantite * ligne.prix_unitaire).quantize(Decimal('0.01'))
        nature = nature_de_ligne(ligne, facture)
        produits[nature] = produits.get(nature, ZERO) + brut
        remises += brut - ligne.montant_ligne
    if not produits and facture.montant_total:
        # Facture posée d'un bloc, sans lignes détaillées : son type dit la nature.
        nature = facture.type_facture if facture.type_facture not in ('mixte', 'autre') else 'autre'
        produits[nature] = facture.montant_total
    total = sum(produits.values(), ZERO) - remises
    part_assurance = min(facture.montant_assurance or ZERO, total)
    lignes = [(compte('patient'), 'Créance patient', total - part_assurance, ZERO, tiers)]
    if part_assurance:
        lignes.append((compte('tiers_payant'), 'Part assurance', part_assurance, ZERO, tiers))
    if remises:
        motif = facture.motif_remise.libelle if facture.motif_remise_id else 'remise'
        lignes.append((compte('remise'), f'Remise — {motif}', remises, ZERO, tiers))
    for nature, montant in produits.items():
        lignes.append((compte(f'nature:{nature}'), None, ZERO, montant, tiers))
    return lignes


def ecriture_facture(facture):
    origine = f'facture:{facture.pk}'
    if _deja(origine):
        return None
    lignes = lignes_de_vente(facture)
    if not any(d or c for _, _, d, c, _ in lignes):
        return None                      # facture à 0 F : rien à comptabiliser
    return creer_ecriture(journal('VTE'), _jour(facture.date_emission),
                          f'Facture {facture.numero} — {_nom_patient(facture)}',
                          lignes, piece=facture.numero, origine=origine, centre=facture.centre)


def ecriture_avoir(avoir):
    origine = f'avoir:{avoir.pk}'
    if _deja(origine):
        return None
    facture = avoir.facture
    ecriture_facture(facture)            # la vente d'abord, si elle manque
    inverse = [(c, lib, cr, d, t) for c, lib, d, cr, t in lignes_de_vente(facture)]
    if not any(d or c for _, _, d, c, _ in inverse):
        return None
    return creer_ecriture(journal('VTE'), _jour(avoir.date_creation),
                          f'Avoir {avoir.numero} sur facture {facture.numero}', inverse,
                          piece=avoir.numero, origine=origine, centre=avoir.centre)


def _tresorerie(mode, caisse):
    """(compte, journal) de l'argent reçu ou rendu selon le mode."""
    if mode == 'especes':
        return compte_de_caisse(caisse), journal_de_caisse(caisse)
    return compte(f'mode:{mode}'), journal(JOURNAL_DU_MODE.get(mode, 'OD'))


def ecriture_remboursement(avoir):
    origine = f'remboursement:{avoir.pk}'
    if not avoir.montant_rembourse or _deja(origine):
        return None
    caisse = avoir.session.journee.caisse if avoir.session_id else None
    tresorerie, journal_ = _tresorerie(avoir.mode_remboursement or 'especes', caisse)
    tiers = _nom_patient(avoir.facture)
    return creer_ecriture(journal_, _jour(avoir.date_creation),
                          f'Remboursement avoir {avoir.numero}',
                          [(compte('patient'), None, avoir.montant_rembourse, ZERO, tiers),
                           (tresorerie, None, ZERO, avoir.montant_rembourse, tiers)],
                          piece=avoir.numero, origine=origine, centre=avoir.centre)


# ─── Paiement, sortie, écart ───────────────────────────────────────────────────

def ecriture_paiement(paiement):
    origine = f'paiement:{paiement.pk}'
    if _deja(origine) or not paiement.montant:
        return None
    facture = paiement.facture
    tresorerie, journal_ = _tresorerie(paiement.mode_paiement, paiement.caisse)
    tiers = _nom_patient(facture)
    return creer_ecriture(journal_, _jour(paiement.date_paiement),
                          f'Encaissement {paiement.numero} — facture {facture.numero}',
                          [(tresorerie, None, paiement.montant, ZERO, tiers),
                           (compte('patient'), None, ZERO, paiement.montant, tiers)],
                          piece=paiement.numero, origine=origine, centre=paiement.centre)


def ecriture_sortie(sortie):
    origine = f'sortie:{sortie.pk}'
    if sortie.statut != 'payee' or _deja(origine):
        return None
    caisse = sortie.session.journee.caisse
    charge = sortie.motif.compte or compte('sortie_defaut')
    libelle = f'Sortie {sortie.numero} — {sortie.libelle}'
    return creer_ecriture(journal_de_caisse(caisse), _jour(sortie.date_paiement), libelle,
                          [(charge, None, sortie.montant, ZERO, sortie.beneficiaire),
                           (compte_de_caisse(caisse), None, ZERO, sortie.montant, sortie.beneficiaire)],
                          piece=sortie.numero, origine=origine, centre=sortie.centre)


def ecriture_ecart(session):
    origine = f'ecart:{session.pk}'
    if not session.ecart or session.statut == 'ouverte' or _deja(origine):
        return None
    caisse = session.journee.caisse
    montant = abs(session.ecart)
    tiers = session.nom_caissiere
    if session.ecart < 0:
        lignes = [(compte('ecart_manquant'), None, montant, ZERO, tiers),
                  (compte_de_caisse(caisse), None, ZERO, montant, tiers)]
        libelle = f'Manquant de caisse — session {session.numero}'
    else:
        lignes = [(compte_de_caisse(caisse), None, montant, ZERO, tiers),
                  (compte('ecart_excedent'), None, ZERO, montant, tiers)]
        libelle = f'Excédent de caisse — session {session.numero}'
    return creer_ecriture(journal_de_caisse(caisse), _jour(session.date_cloture), libelle, lignes,
                          piece=session.numero, origine=origine, centre=session.centre)


# ─── Génération d'une période ──────────────────────────────────────────────────

def generer(debut, fin):
    """Crée en brouillon toutes les écritures manquantes de la période.

    Rend {'crees': n, 'erreurs': [messages]}. Une pièce qui pose problème
    (compte manquant, exercice clôturé…) est signalée et n'empêche pas les
    autres d'être passées.
    """
    from facturation.models import Facture, Paiement
    from .models import Avoir, SessionCaissiere, SortieCaisse

    taches = []
    factures = (Facture.all_objects.filter(date_emission__date__range=[debut, fin])
                .exclude(statut='brouillon').select_related('patient', 'motif_remise')
                .prefetch_related('avoirs'))
    for f in factures:
        # Annulée sans avoir : un brouillon annulé, ou une annulation d'avant
        # les avoirs — ce n'était pas (ou plus) une vente.
        if f.statut == 'annulee' and not f.avoirs.exists():
            continue
        taches.append((f'Facture {f.numero}', ecriture_facture, f))
    for p in (Paiement.all_objects.filter(date_paiement__date__range=[debut, fin])
              .select_related('facture__patient', 'caisse')):
        taches.append((f'Paiement {p.numero}', ecriture_paiement, p))
    for a in (Avoir.all_objects.filter(date_creation__date__range=[debut, fin])
              .select_related('facture__patient', 'session__journee__caisse')):
        taches.append((f'Avoir {a.numero}', ecriture_avoir, a))
        taches.append((f'Remboursement {a.numero}', ecriture_remboursement, a))
    for s in (SortieCaisse.all_objects.filter(statut='payee', date_paiement__date__range=[debut, fin])
              .select_related('session__journee__caisse', 'motif__compte')):
        taches.append((f'Sortie {s.numero}', ecriture_sortie, s))
    for s in (SessionCaissiere.all_objects.filter(date_cloture__date__range=[debut, fin])
              .exclude(statut='ouverte').select_related('journee__caisse', 'caissiere')):
        taches.append((f'Session {s.numero}', ecriture_ecart, s))

    crees, erreurs = 0, []
    for nom, fonction, objet in taches:
        try:
            with transaction.atomic():
                if fonction(objet) is not None:
                    crees += 1
        except ErreurCompta as e:
            erreurs.append(f'{nom} : {e}')
    return {'crees': crees, 'erreurs': erreurs}


# ─── Passage des écritures ─────────────────────────────────────────────────────

def valider(ecritures, par):
    """Valide des écritures en brouillon : contrôle, puis numéro définitif.

    Le numéro suit, par journal et par exercice, le plus haut déjà attribué :
    la numérotation reste continue et sans trou, puisqu'une écriture validée
    ne se supprime jamais.
    """
    valides = 0
    for ecriture in sorted(ecritures, key=lambda e: (e.date, e.pk)):
        if ecriture.statut != 'brouillon':
            continue
        debit, credit = ecriture.totaux()
        if debit != credit or not debit:
            raise ErreurCompta(f"Écriture « {ecriture.libelle} » déséquilibrée : validation refusée.")
        if ecriture.exercice.statut != 'ouvert':
            raise ErreurCompta(f"L'exercice {ecriture.exercice} est clôturé.")
        with transaction.atomic():
            dernier = (Ecriture.all_objects.select_for_update()
                       .filter(journal=ecriture.journal, exercice=ecriture.exercice)
                       .aggregate(m=Max('numero'))['m'] or 0)
            ecriture.numero = dernier + 1
            ecriture.statut = 'validee'
            ecriture.validee_par = par
            ecriture.date_validation = timezone.now()
            ecriture.save()
        valides += 1
    return valides


def contre_passer(ecriture, par, jour=None):
    """Écriture inverse, en brouillon, d'une écriture validée."""
    if ecriture.statut != 'validee':
        raise ErreurCompta("Seule une écriture validée se contre-passe ; un brouillon se supprime.")
    if hasattr(ecriture, 'contre_passee_par'):
        raise ErreurCompta("Cette écriture a déjà été contre-passée.")
    lignes = [(l.compte, l.libelle, l.credit, l.debit, l.tiers) for l in ecriture.lignes.all()]
    return creer_ecriture(ecriture.journal, jour or timezone.localdate(),
                          f'Contre-passation de {ecriture.reference} — {ecriture.libelle}', lignes,
                          piece=ecriture.piece, centre=ecriture.centre, par=par,
                          contre_passation_de=ecriture)


def supprimer_brouillon(ecriture):
    if ecriture.statut != 'brouillon':
        raise ErreurCompta("Une écriture validée ne se supprime pas : contre-passez-la.")
    ecriture.delete()
