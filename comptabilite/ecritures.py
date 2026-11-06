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
| Facture fournisseur           | ACH           | Charge ou immobilisation      | Fournisseur (401)             |
| Règlement fournisseur         | BQ / MM / CAI | Fournisseur                   | Trésorerie                    |

Aucun numéro de compte n'est écrit ici : tout passe par les correspondances
(`Correspondance`), modifiables à l'écran. Chaque écriture porte la clé de
son origine (« paiement:12 ») : relancer la génération ne double jamais rien.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .models import Correspondance, CorrespondanceTiers, Ecriture, Exercice, Journal, LigneEcriture

ZERO = Decimal('0')

# Journaux de l'expert-comptable (codes Sage). L'argent qui entre ou sort
# d'un compte de trésorerie va dans le journal qui porte ce compte (« CAI AC »
# pour 57100001, « BQ SIB » pour 52110002…) ; un compte sans journal (Mobile
# Money, prise en charge d'une assurance, bon) va aux opérations diverses.
VENTES, ACHATS, OPERATIONS_DIVERSES, A_NOUVEAUX = 'VTE', 'ACH', 'OD', 'RAN'


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
    """Compte de la caisse, désigné dans les correspondances (clé
    « caisse:<code> »). Le plan comptable est celui de l'expert-comptable :
    aucun sous-compte n'est créé ici, il le crée lui-même."""
    if caisse is None:
        return compte('caisse')
    corr = Correspondance.objects.select_related('compte').filter(cle=f'caisse:{caisse.code}').first()
    if corr is None:
        raise ErreurCompta(f"La caisse « {caisse.nom} » n'a pas de compte : désignez son sous-compte 571 "
                           "dans Comptabilité → Configuration → Correspondances.")
    return corr.compte


class NomTiers(str):
    """Le nom lisible d'un tiers sur une ligne (« KOFFI Awa (PAT…) »), qui
    porte en plus son compte du plan tiers (`compte`) : la créance d'un
    patient est due au client « CLIENT CAISSE … » de sa caisse."""

    def __new__(cls, nom, compte_tiers=None):
        obj = super().__new__(cls, nom or '')
        obj.compte = compte_tiers
        return obj


def tiers_designe(cle):
    """Le compte tiers désigné pour `cle` (« caisse:CAISACC »,
    « assurance:NSIA »), ou None : faute de désignation, la ligne garde
    seulement le nom."""
    corr = CorrespondanceTiers.objects.select_related('tiers').filter(cle=cle).first()
    return corr.tiers if corr else None


def tiers_de_caisse(caisse):
    return tiers_designe(f'caisse:{caisse.code}') if caisse else None


def caisse_de_facture(facture):
    """La caisse du premier encaissement de la facture (celle qui l'a vendue,
    comme dans les documents des ventes), sinon None."""
    from facturation.models import Paiement
    p = (Paiement.all_objects.filter(facture=facture, caisse__isnull=False)
         .select_related('caisse').order_by('date_paiement', 'pk').first())
    return p.caisse if p else None


def _patient(facture, caisse=None):
    """Le patient de la facture, rattaché au client de sa caisse."""
    return NomTiers(_nom_patient(facture), tiers_de_caisse(caisse or caisse_de_facture(facture)))


def rattacher_facture(facture, compte_tiers):
    """Une facture comptabilisée avant tout encaissement ne connaissait pas
    sa caisse : sa créance (et celle de ses avoirs) prend le client de la
    caisse qui encaisse, pour se lettrer avec ses règlements. Seul le
    rattachement au tiers change ; comptes et montants restent."""
    if compte_tiers is None:
        return 0
    origines = [f'facture:{facture.pk}'] + [f'avoir:{pk}' for pk in facture.avoirs.values_list('pk', flat=True)]
    return (LigneEcriture.objects.filter(ecriture__origine__in=origines, compte=compte('patient'),
                                         compte_tiers__isnull=True, lettre='')
            .update(compte_tiers=compte_tiers))


def _assureur(assurance):
    return NomTiers(assurance.nom, tiers_designe(f'assurance:{assurance.code}'))


def compte_fournisseur(facture):
    """Compte de la dette : le collectif du fournisseur dans le plan tiers,
    sinon la correspondance « fournisseur »."""
    if facture.compte_tiers_id and facture.compte_tiers.compte_collectif_id:
        return facture.compte_tiers.compte_collectif
    return compte('fournisseur')


def _fournisseur(facture):
    return NomTiers(facture.fournisseur, facture.compte_tiers)


def journal(code):
    j = Journal.objects.filter(code=code).first()
    if j is None:
        raise ErreurCompta(f"Le journal {code} n'existe pas.")
    return j


def journal_de_tresorerie(compte_):
    """Le journal de l'expert qui porte ce compte de trésorerie, sinon OD."""
    j = Journal.objects.filter(compte_tresorerie=compte_, actif=True).first()
    return j or journal(OPERATIONS_DIVERSES)


def journal_de_caisse(caisse):
    return journal_de_tresorerie(compte_de_caisse(caisse))


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


def exclure_exercices_clos(qs, jour, champ='ecriture__exercice'):
    """Cumul arrêté à `jour` : les exercices clos avant lui sont résumés par
    les à-nouveaux de l'exercice suivant — leurs lignes ne comptent plus,
    sans quoi chaque solde de bilan serait compté deux fois."""
    clos = Exercice.objects.filter(statut='cloture', date_fin__lt=jour)
    return qs.exclude(**{f'{champ}__in': clos})


# ─── Création ──────────────────────────────────────────────────────────────────

def creer_ecriture(journal_, jour, libelle, lignes, piece='', origine=None, centre=None, par=None,
                   contre_passation_de=None):
    """Écriture en brouillon. `lignes` : [(compte, libellé, débit, crédit, tiers)],
    avec en option un sixième élément : la convention qui finance la ligne.

    Les lignes à zéro sont écartées ; l'ensemble doit être équilibré.
    """
    lignes = [l for l in lignes if (l[2] or ZERO) or (l[3] or ZERO)]
    debit = sum((l[2] or ZERO for l in lignes), ZERO)
    credit = sum((l[3] or ZERO for l in lignes), ZERO)
    if len(lignes) < 2:
        raise ErreurCompta("Une écriture compte au moins deux lignes.")
    if debit != credit:
        raise ErreurCompta(f"Écriture déséquilibrée : débit {debit} ≠ crédit {credit}.")
    for l in lignes:
        if l[0].totalisation:
            raise ErreurCompta(f"Le compte {l[0].numero} est un compte de totalisation : "
                               "il ne reçoit pas d'écriture, choisissez un sous-compte.")
        if getattr(l[4], 'compte', None) and l[0].classe != '4':
            raise ErreurCompta(f"Le compte tiers {l[4].compte.numero} ne va que sur un compte de tiers "
                               f"(classe 4), pas sur {l[0].numero}.")
    with transaction.atomic():
        ecriture = Ecriture.objects.create(
            journal=journal_, exercice=exercice_pour(jour), date=jour, libelle=libelle[:255],
            piece=piece[:60], origine=origine, centre=centre, cree_par=par,
            contre_passation_de=contre_passation_de)
        LigneEcriture.objects.bulk_create([
            LigneEcriture(ecriture=ecriture, compte=l[0], libelle=(l[1] or libelle)[:255],
                          debit=l[2] or ZERO, credit=l[3] or ZERO, tiers=(l[4] or '')[:150],
                          compte_tiers=getattr(l[4], 'compte', None),
                          convention=l[5] if len(l) > 5 else None)
            for l in lignes])
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
    tiers = _patient(facture)
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
    # Part de l'assureur : seulement si la facture désigne un assureur
    # (Facture.part_assurance) ; la créance porte alors son nom.
    # Une part refusée puis reportée sur le patient (lot 7) a quitté
    # `montant_assurance` ; la vente, elle, la reconnaît telle qu'elle était,
    # l'écriture du refus la faisant ensuite passer au patient.
    reportee = facture.rejets_assurance.filter(decision='patient').aggregate(s=Sum('montant'))['s'] or ZERO
    part_initiale = facture.part_assurance + reportee if facture.assurance_id else ZERO
    part_assurance = min(part_initiale, total)
    lignes = [(compte('patient'), 'Créance patient', total - part_assurance, ZERO, tiers)]
    if part_assurance:
        lignes.append((compte('tiers_payant'), f'Part assurance — {tiers}', part_assurance, ZERO,
                       _assureur(facture.assurance)))
    # Sur les comptes de charge et de produit, le nom seul.
    if remises:
        motif = facture.motif_remise.libelle if facture.motif_remise_id else 'remise'
        lignes.append((compte('remise'), f'Remise — {motif}', remises, ZERO, str(tiers)))
    for nature, montant in produits.items():
        lignes.append((compte(f'nature:{nature}'), None, ZERO, montant, str(tiers)))
    return lignes


def ecriture_facture(facture):
    origine = f'facture:{facture.pk}'
    if _deja(origine):
        return None
    lignes = lignes_de_vente(facture)
    if not any(d or c for _, _, d, c, _ in lignes):
        return None                      # facture à 0 F : rien à comptabiliser
    return creer_ecriture(journal(VENTES), _jour(facture.date_emission),
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
    return creer_ecriture(journal(VENTES), _jour(avoir.date_creation),
                          f'Avoir {avoir.numero} sur facture {facture.numero}', inverse,
                          piece=avoir.numero, origine=origine, centre=avoir.centre)


def _tresorerie(mode, caisse):
    """(compte, journal) de l'argent reçu ou rendu selon le mode."""
    tresorerie = compte_de_caisse(caisse) if mode == 'especes' else compte(f'mode:{mode}')
    return tresorerie, journal_de_tresorerie(tresorerie)


def ecriture_remboursement(avoir):
    origine = f'remboursement:{avoir.pk}'
    if not avoir.montant_rembourse or _deja(origine):
        return None
    caisse = avoir.session.journee.caisse if avoir.session_id else None
    tresorerie, journal_ = _tresorerie(avoir.mode_remboursement or 'especes', caisse)
    tiers = _patient(avoir.facture, caisse)
    return creer_ecriture(journal_, _jour(avoir.date_creation),
                          f'Remboursement avoir {avoir.numero}',
                          [(compte('patient'), None, avoir.montant_rembourse, ZERO, tiers),
                           (tresorerie, None, ZERO, avoir.montant_rembourse, str(tiers))],
                          piece=avoir.numero, origine=origine, centre=avoir.centre)


# ─── Paiement, sortie, écart ───────────────────────────────────────────────────

def ecriture_paiement(paiement):
    origine = f'paiement:{paiement.pk}'
    if _deja(origine) or not paiement.montant:
        return None
    if paiement.reglement_assurance_id:
        return None          # compté avec le règlement de l'assureur (ecriture_reglement)
    facture = paiement.facture
    if paiement.operateur_id:
        # Mobile Money : sur le compte de l'opérateur (Wave, Orange Money…).
        tresorerie = paiement.operateur.compte
        journal_ = journal_de_tresorerie(tresorerie)
    else:
        tresorerie, journal_ = _tresorerie(paiement.mode_paiement, paiement.caisse)
    tiers = _patient(facture, paiement.caisse)
    rattacher_facture(facture, tiers.compte)
    # Prise en charge (mode assurance, bon) : la « trésorerie » est la
    # créance sur l'assureur.
    debiteur = (_assureur(facture.assurance) if tresorerie.classe == '4' and facture.assurance_id
                else str(tiers))
    return creer_ecriture(journal_, _jour(paiement.date_paiement),
                          f'Encaissement {paiement.numero} — facture {facture.numero}',
                          [(tresorerie, None, paiement.montant, ZERO, debiteur),
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
                          [(charge, None, sortie.montant, ZERO, sortie.beneficiaire, sortie.convention),
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


# ─── Financements : versements des bailleurs, dons ─────────────────────────────

def _tresorerie_recue(mode):
    """(compte, journal) de l'argent reçu hors caisse de guichet."""
    tresorerie = compte('caisse') if mode == 'especes' else compte(f'mode:{mode}')
    return tresorerie, journal_de_tresorerie(tresorerie)


def ecriture_versement(versement):
    origine = f'versement:{versement.pk}'
    if _deja(origine):
        return None
    convention = versement.convention
    tresorerie, journal_ = _tresorerie_recue(versement.mode)
    tiers = str(convention.bailleur)
    return creer_ecriture(journal_, versement.date,
                          f'Versement {versement.numero} — {convention.code} {convention.intitule}',
                          [(tresorerie, None, versement.montant, ZERO, tiers),
                           (convention.compte_ressource, None, ZERO, versement.montant, tiers, convention)],
                          piece=versement.reference or versement.numero, origine=origine,
                          centre=versement.centre)


def ecriture_don(don):
    origine = f'don:{don.pk}'
    if _deja(origine) or not don.montant:
        return None
    tiers = don.nom_donateur
    produits = list(don.lignes.select_related('produit')) if don.nature == 'nature' else []
    if produits:
        # Produits entrés en stock : chacun à l'actif de son type (lot 8).
        par_compte = {}
        for l in produits:
            c = compte(f'stock:{l.produit.type}')
            par_compte[c] = par_compte.get(c, ZERO) + l.montant
        debits = [(c, None, m, ZERO, tiers) for c, m in par_compte.items()]
        journal_ = journal(OPERATIONS_DIVERSES)
    elif don.nature == 'nature':
        debits = [(don.compte_actif or compte('don_nature_actif'), None, don.montant, ZERO, tiers)]
        journal_ = journal(OPERATIONS_DIVERSES)
    else:
        debit, journal_ = _tresorerie_recue(don.nature)
        debits = [(debit, None, don.montant, ZERO, tiers)]
    credit = don.convention.compte_ressource if don.convention_id else compte('don')
    return creer_ecriture(journal_, don.date, f'Don {don.numero} — {tiers}',
                          debits + [(credit, None, ZERO, don.montant, tiers, don.convention)],
                          piece=don.reference or don.numero, origine=origine, centre=don.centre)


def ecriture_reglement(reglement):
    """Règlement d'un assureur : trésorerie au débit, créance sur l'assureur au crédit."""
    origine = f'reglement:{reglement.pk}'
    if _deja(origine):
        return None
    tresorerie, journal_ = _tresorerie_recue(reglement.mode)
    tiers = _assureur(reglement.assurance)
    return creer_ecriture(journal_, reglement.date, f'Règlement {reglement.numero} — {tiers}',
                          [(tresorerie, None, reglement.montant, ZERO, str(tiers)),
                           (compte('tiers_payant'), None, ZERO, reglement.montant, tiers)],
                          piece=reglement.reference or reglement.numero, origine=origine,
                          centre=reglement.centre)


def ecriture_rejet(rejet):
    """Refus de l'assureur : la créance sur lui passe au patient, ou en perte."""
    origine = f'rejet:{rejet.pk}'
    if _deja(origine):
        return None
    facture = rejet.facture
    ecriture_facture(facture)            # la vente d'abord, si elle manque
    debit = compte('patient') if rejet.decision == 'patient' else compte('perte_creance')
    tiers = _assureur(rejet.assurance)
    patient = _patient(facture) if debit.classe == '4' else _nom_patient(facture)
    return creer_ecriture(journal(OPERATIONS_DIVERSES), rejet.date,
                          f'Refus {rejet.numero} de {tiers} — facture {facture.numero} ({rejet.get_decision_display().lower()})',
                          [(debit, None, rejet.montant, ZERO, patient),
                           (compte('tiers_payant'), None, ZERO, rejet.montant, tiers)],
                          piece=rejet.numero, origine=origine, centre=rejet.centre)


# ─── Achats (lot 8) ────────────────────────────────────────────────────────────

def ecriture_facture_fournisseur(facture):
    """Charges (ou immobilisations) au débit, dette fournisseur au crédit."""
    origine = f'facture_fournisseur:{facture.pk}'
    if _deja(origine) or not facture.montant_total:
        return None
    tiers = _fournisseur(facture)
    convention = facture.convention
    lignes = [(l.compte, l.libelle, l.montant, ZERO, str(tiers), convention) for l in facture.lignes.all()]
    lignes.append((compte_fournisseur(facture), None, ZERO, facture.montant_total, tiers))
    return creer_ecriture(journal(ACHATS), facture.date,
                          f'Facture {facture.reference or facture.numero} — {tiers}', lignes,
                          piece=facture.reference or facture.numero, origine=origine, centre=facture.centre)


def ecriture_reglement_fournisseur(reglement):
    origine = f'reglement_fournisseur:{reglement.pk}'
    if _deja(origine):
        return None
    ct = reglement.compte_tresorerie
    if ct:
        tresorerie, journal_ = ct.compte, journal_de_tresorerie(ct.compte)
    else:
        tresorerie, journal_ = _tresorerie_recue(reglement.mode)
    tiers = _fournisseur(reglement.facture)
    return creer_ecriture(journal_, reglement.date,
                          f'Règlement {reglement.numero} — {tiers} (facture {reglement.facture.numero})',
                          [(compte_fournisseur(reglement.facture), None, reglement.montant, ZERO, tiers),
                           (tresorerie, None, ZERO, reglement.montant, str(tiers))],
                          piece=reglement.reference or reglement.numero, origine=origine,
                          centre=reglement.centre)


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
              .select_related('facture__patient', 'caisse', 'operateur__compte')):
        taches.append((f'Paiement {p.numero}', ecriture_paiement, p))
    for a in (Avoir.all_objects.filter(date_creation__date__range=[debut, fin])
              .select_related('facture__patient', 'session__journee__caisse')):
        taches.append((f'Avoir {a.numero}', ecriture_avoir, a))
        taches.append((f'Remboursement {a.numero}', ecriture_remboursement, a))
    for s in (SortieCaisse.all_objects.filter(statut='payee', date_paiement__date__range=[debut, fin])
              .select_related('session__journee__caisse', 'motif__compte')):
        taches.append((f'Sortie {s.numero}', ecriture_sortie, s))
    from .models import Don, ReglementAssurance, RejetAssurance, RemiseBanque, Versement
    for r in RejetAssurance.all_objects.filter(date__range=[debut, fin]).select_related('facture', 'assurance'):
        taches.append((f'Refus {r.numero}', ecriture_rejet, r))
    from .tresorerie import ecritures_remise
    for r in RemiseBanque.all_objects.filter(date__range=[debut, fin]).select_related('caisse', 'compte_tresorerie'):
        taches.append((f'Remise {r.numero}', ecritures_remise, r))
    for r in ReglementAssurance.all_objects.filter(date__range=[debut, fin]).select_related('assurance'):
        taches.append((f'Règlement {r.numero}', ecriture_reglement, r))
    for v in Versement.all_objects.filter(date__range=[debut, fin]).select_related('convention__bailleur'):
        taches.append((f'Versement {v.numero}', ecriture_versement, v))
    for d in Don.all_objects.filter(date__range=[debut, fin]).select_related('donateur', 'convention'):
        taches.append((f'Don {d.numero}', ecriture_don, d))
    from .models import FactureFournisseur, ReglementFournisseur
    for f in (FactureFournisseur.all_objects.filter(date__range=[debut, fin])
              .select_related('convention', 'compte_tiers__compte_collectif')
              .prefetch_related('lignes__compte')):
        taches.append((f'Facture fournisseur {f.numero}', ecriture_facture_fournisseur, f))
    for r in (ReglementFournisseur.all_objects.filter(date__range=[debut, fin])
              .select_related('facture__compte_tiers__compte_collectif', 'compte_tresorerie__compte')):
        taches.append((f'Règlement fournisseur {r.numero}', ecriture_reglement_fournisseur, r))
    for s in (SessionCaissiere.all_objects.filter(date_cloture__date__range=[debut, fin])
              .exclude(statut='ouverte').select_related('journee__caisse', 'caissiere')):
        taches.append((f'Session {s.numero}', ecriture_ecart, s))

    crees, erreurs = 0, []
    for nom, fonction, objet in taches:
        try:
            with transaction.atomic():
                cree = fonction(objet)
                # Une remise en banque produit deux écritures (une liste).
                crees += len(cree) if isinstance(cree, list) else int(cree is not None)
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
    lignes = [(l.compte, l.libelle, l.credit, l.debit, NomTiers(l.tiers, l.compte_tiers), l.convention)
              for l in ecriture.lignes.select_related('compte', 'compte_tiers')]
    return creer_ecriture(ecriture.journal, jour or timezone.localdate(),
                          f'Contre-passation de {ecriture.reference} — {ecriture.libelle}', lignes,
                          piece=ecriture.piece, centre=ecriture.centre, par=par,
                          contre_passation_de=ecriture)


def supprimer_brouillon(ecriture):
    if ecriture.statut != 'brouillon':
        raise ErreurCompta("Une écriture validée ne se supprime pas : contre-passez-la.")
    ecriture.delete()
