"""
Clôture de l'exercice (lot 8 du module Comptabilité).

Dans l'ordre :

1. **Inventaire** : le stock compté au 31/12 est porté aux comptes de stock
   (311, 331) par la variation (6031, 6033). Les achats étant passés en
   charge toute l'année (inventaire intermittent), c'est cette écriture qui
   fait de la consommation réelle la charge de l'exercice.
2. **Contrôles** : pièces toutes comptabilisées, brouillons tous validés,
   journées de caisse toutes closes, exercice précédent clos.
3. **Clôture** : le résultat (classes 6 à 8) est arrêté ; les soldes des
   comptes de bilan (classes 1 à 5) passent en **à-nouveaux** au premier jour
   de l'exercice suivant, le résultat sur 131 (excédent) ou 139 (déficit).
   L'exercice est alors figé : plus aucune écriture n'y entre.

Les comptes sont tenus par centre : l'inventaire se saisit pour chacun, et
chaque centre reçoit ses propres à-nouveaux.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import ecritures as moteur
from .models import Ecriture, Exercice, LigneEcriture

ZERO = Decimal('0')

# Types de produits suivis en stock à l'inventaire. L'équipement reçu ou
# acheté est une immobilisation : il ne se compte pas en stock.
TYPES_STOCK = [('medicament', 'Médicaments'), ('consommable', 'Consommables médicaux')]

# Le stock central (magasin) est tenu à Yamoussoukro : sa valeur est
# proposée dans l'inventaire de ce centre ; chaque pharmacie l'est dans le
# centre dont elle dépend. Les montants restent modifiables à l'écran.
CENTRE_DU_STOCK_CENTRAL = 'WALE'


def _origine_inventaire(exercice, centre):
    return f'inventaire:{exercice.pk}:{centre.pk if centre else 0}'


def _origine_an(exercice, centre_id):
    return f'an:{exercice.pk}:{centre_id or 0}'


# ─── Inventaire ────────────────────────────────────────────────────────────────

def valeur_stocks(centre):
    """Valeur au prix d'achat du stock présent, par type :
    {type: {'detail': [(lieu, valeur)], 'total': valeur}}."""
    from pharmacie.models import PHARMACIE_CENTRE_CODE, PHARMACIES_WALE, StockPharmacie
    from stock.models import Produit

    resultat = {t: {'detail': [], 'total': ZERO} for t, _ in TYPES_STOCK}

    def _ajouter(lieu, valeurs):
        for t, _ in TYPES_STOCK:
            v = valeurs.get(t, ZERO).quantize(Decimal('1'))
            if v:
                resultat[t]['detail'].append((lieu, v))
                resultat[t]['total'] += v

    if centre is None or centre.code == CENTRE_DU_STOCK_CENTRAL:
        valeurs = {}
        for p in Produit.objects.filter(stock_actuel__gt=0):
            valeurs[p.type] = valeurs.get(p.type, ZERO) + p.stock_actuel * p.prix_achat
        _ajouter('Stock central (magasin)', valeurs)
    noms = dict(PHARMACIES_WALE)
    for code, centre_code in PHARMACIE_CENTRE_CODE.items():
        if centre is not None and centre.code != centre_code:
            continue
        valeurs = {}
        for s in StockPharmacie.objects.filter(pharmacie=code, quantite__gt=0).select_related('produit'):
            valeurs[s.produit.type] = valeurs.get(s.produit.type, ZERO) + s.quantite * s.produit.prix_achat
        _ajouter(f'Pharmacie {noms.get(code, code)}', valeurs)
    return resultat


def solde_compte(compte, centre, jour):
    """Solde d'un compte pour un centre, toutes écritures confondues, au `jour`."""
    qs = LigneEcriture.objects.filter(compte=compte, ecriture__centre=centre, ecriture__date__lte=jour)
    t = moteur.exclure_exercices_clos(qs, jour).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (t['d'] or ZERO) - (t['c'] or ZERO)


def ecriture_inventaire(exercice, centre):
    return Ecriture.all_objects.filter(origine=_origine_inventaire(exercice, centre)).first()


def situation_inventaire(exercice, centre):
    """Par type : compte de stock, solde actuel, valeur proposée."""
    valeurs = valeur_stocks(centre)
    lignes = []
    for t, libelle in TYPES_STOCK:
        compte = moteur.compte(f'stock:{t}')
        lignes.append({'type': t, 'libelle': libelle, 'compte': compte,
                       'solde': solde_compte(compte, centre, exercice.date_fin),
                       'propose': valeurs[t]['total'], 'detail': valeurs[t]['detail']})
    return lignes


def comptabiliser_inventaire(exercice, centre, valeurs, par):
    """Porte les comptes de stock à la valeur inventoriée `valeurs` ({type: montant}).

    L'écriture, datée du dernier jour de l'exercice, passe la différence entre
    le solde du compte de stock et l'inventaire en variation de stock. Refaite
    tant qu'elle est en brouillon ; validée, elle se contre-passe d'abord.
    """
    if exercice.statut != 'ouvert':
        raise moteur.ErreurCompta(f"L'exercice {exercice} est clôturé.")
    existante = ecriture_inventaire(exercice, centre)
    if existante and existante.statut == 'validee':
        raise moteur.ErreurCompta("L'inventaire de cet exercice est déjà validé : contre-passez son écriture "
                                  "pour le refaire.")
    lignes = []
    with transaction.atomic():
        if existante:
            existante.delete()
        for t, libelle in TYPES_STOCK:
            if t not in valeurs:
                continue
            valeur = valeurs[t]
            if valeur is None or valeur < 0:
                raise moteur.ErreurCompta(f"Valeur d'inventaire invalide pour : {libelle.lower()}.")
            stock, variation = moteur.compte(f'stock:{t}'), moteur.compte(f'variation:{t}')
            ecart = valeur - solde_compte(stock, centre, exercice.date_fin)
            if ecart > 0:
                lignes += [(stock, f'Stock final — {libelle.lower()}', ecart, ZERO, ''),
                           (variation, f'Variation — {libelle.lower()}', ZERO, ecart, '')]
            elif ecart < 0:
                lignes += [(variation, f'Variation — {libelle.lower()}', -ecart, ZERO, ''),
                           (stock, f'Stock final — {libelle.lower()}', ZERO, -ecart, '')]
        if not lignes:
            return None
        return moteur.creer_ecriture(
            moteur.journal('OD'), exercice.date_fin, f"Inventaire de fin d'exercice {exercice}", lignes,
            piece=f'INV-{exercice}', origine=_origine_inventaire(exercice, centre), centre=centre, par=par)


# ─── Contrôles ─────────────────────────────────────────────────────────────────

def _centres_mouvementes(exercice):
    from centres.models import Centre
    ids = set(Ecriture.all_objects.filter(exercice=exercice).values_list('centre_id', flat=True).distinct())
    return [None if i is None else Centre.objects.get(pk=i) for i in sorted(ids, key=lambda i: i or 0)]


def controles(exercice):
    """Ce qui empêche la clôture (`bloquants`) et ce qui mérite un regard (`avertissements`).

    Les pièces de l'exercice encore sans écriture sont d'abord comptabilisées
    (en brouillon) : il ne reste qu'à les valider.
    """
    from .models import Convention, JourneeCaisse
    bloquants, avertissements = [], []
    if exercice.statut != 'ouvert':
        return {'bloquants': [f"L'exercice {exercice} est déjà clôturé."], 'avertissements': [], 'generees': 0}
    precedent = Exercice.objects.filter(date_fin__lt=exercice.date_debut, statut='ouvert').order_by('date_debut').first()
    if precedent:
        bloquants.append(f"L'exercice précédent ({precedent}) n'est pas clôturé : les exercices se clôturent dans l'ordre.")
    generation = moteur.generer(exercice.date_debut, exercice.date_fin)
    bloquants += [f"Pièce non comptabilisée — {e}" for e in generation['erreurs']]
    journees = JourneeCaisse.all_objects.filter(date_journee__range=[exercice.date_debut, exercice.date_fin],
                                                statut='ouverte').select_related('caisse')
    for j in journees:
        bloquants.append(f"Journée de caisse non clôturée : {j.caisse} du {j.date_journee:%d/%m/%Y}.")
    brouillons = Ecriture.all_objects.filter(exercice=exercice, statut='brouillon').count()
    if brouillons:
        bloquants.append(f"{brouillons} écriture(s) en brouillon à valider (Écritures → passage des écritures).")
    for centre in _centres_mouvementes(exercice):
        if ecriture_inventaire(exercice, centre) is None:
            avertissements.append(f"Aucun inventaire de stock comptabilisé pour {centre or 'les écritures sans centre'} "
                                  "(sans variation de stock, la charge est celle des achats).")
    if (Convention.all_objects.filter(date_debut__lte=exercice.date_fin, date_fin__gte=exercice.date_debut).exists()
            and not Ecriture.all_objects.filter(origine=f'fonds_dedies:{exercice.pk}').exists()):
        avertissements.append("Fonds dédiés non examinés (Financements → Fonds dédiés) : les ressources "
                              "affectées non utilisées seraient comptées dans l'excédent.")
    a_valider = set(LigneEcriture.objects.filter(ecriture__exercice=exercice, compte__a_valider=True)
                    .values_list('compte__numero', flat=True))
    if a_valider:
        avertissements.append("Comptes utilisés dont le numéro SYCEBNL reste à confirmer par l'expert-comptable : "
                              + ', '.join(sorted(a_valider)) + '.')
    return {'bloquants': bloquants, 'avertissements': avertissements, 'generees': generation['crees']}


# ─── Clôture ───────────────────────────────────────────────────────────────────

def resultat(exercice, centre_id=None, tous=True):
    """Excédent (positif) ou déficit des écritures validées de l'exercice."""
    qs = LigneEcriture.objects.filter(ecriture__exercice=exercice, ecriture__statut='validee',
                                      compte__numero__regex=r'^[678]')
    if not tous:
        qs = qs.filter(ecriture__centre_id=centre_id)
    t = qs.aggregate(d=Sum('debit'), c=Sum('credit'))
    return (t['c'] or ZERO) - (t['d'] or ZERO)


def _lignes_a_nouveaux(exercice, centre_id):
    """Soldes de bilan d'un centre : par compte, et par tiers sur les comptes de tiers (classe 4)."""
    soldes = (LigneEcriture.objects.filter(ecriture__exercice=exercice, ecriture__statut='validee',
                                           ecriture__centre_id=centre_id, compte__numero__regex=r'^[1-5]')
              .values('compte_id', 'compte__numero', 'tiers').annotate(d=Sum('debit'), c=Sum('credit'))
              .order_by('compte__numero', 'tiers'))
    from .models import Compte
    cumul = {}
    for s in soldes:
        tiers = s['tiers'] if s['compte__numero'].startswith('4') else ''
        cle = (s['compte_id'], tiers)
        cumul[cle] = cumul.get(cle, ZERO) + (s['d'] or ZERO) - (s['c'] or ZERO)
    comptes = Compte.objects.in_bulk({compte_id for compte_id, _ in cumul})
    lignes = []
    for (compte_id, tiers), solde in cumul.items():
        if solde > 0:
            lignes.append((comptes[compte_id], 'À nouveau', solde, ZERO, tiers))
        elif solde < 0:
            lignes.append((comptes[compte_id], 'À nouveau', ZERO, -solde, tiers))
    r = resultat(exercice, centre_id, tous=False)
    if r > 0:
        lignes.append((moteur.compte('resultat_excedent'), f'Excédent de l\'exercice {exercice}', ZERO, r, ''))
    elif r < 0:
        lignes.append((moteur.compte('resultat_deficit'), f'Déficit de l\'exercice {exercice}', -r, ZERO, ''))
    return lignes


def cloturer(exercice, par, malgre_avertissements=False):
    """Clôture l'exercice : à-nouveaux validés dans l'exercice suivant, exercice figé."""
    verif = controles(exercice)
    if verif['bloquants']:
        raise moteur.ErreurCompta("Clôture impossible : " + ' ; '.join(verif['bloquants']))
    if verif['avertissements'] and not malgre_avertissements:
        raise moteur.ErreurCompta("Des points restent à examiner : confirmez la clôture malgré eux.")
    jour_an = exercice.date_fin + timedelta(days=1)
    with transaction.atomic():
        suivant = moteur.exercice_pour(jour_an)
        a_nouveaux = []
        for centre_id in (Ecriture.all_objects.filter(exercice=exercice).order_by()
                          .values_list('centre_id', flat=True).distinct()):
            lignes = _lignes_a_nouveaux(exercice, centre_id)
            if len(lignes) < 2:
                continue
            a_nouveaux.append(_creer_an(exercice, suivant, centre_id, lignes, par))
        moteur.valider(a_nouveaux, par)
        exercice.statut = 'cloture'
        exercice.resultat = resultat(exercice)
        exercice.date_cloture = timezone.now()
        exercice.cloture_par = par
        exercice.save()
    return exercice


def _creer_an(exercice, suivant, centre_id, lignes, par):
    from centres.models import Centre
    centre = Centre.objects.get(pk=centre_id) if centre_id else None
    return moteur.creer_ecriture(
        moteur.journal('AN'), suivant.date_debut, f"À-nouveaux issus de l'exercice {exercice}", lignes,
        piece=f'AN-{exercice}', origine=_origine_an(exercice, centre_id), centre=centre, par=par)


def rouvrir(exercice, par):
    """Rouvre un exercice clos (correction tardive) : ses à-nouveaux sont retirés,
    à refaire par une nouvelle clôture. Seul le dernier exercice clos se rouvre."""
    if exercice.statut != 'cloture':
        raise moteur.ErreurCompta(f"L'exercice {exercice} n'est pas clôturé.")
    if Exercice.objects.filter(date_debut__gt=exercice.date_fin, statut='cloture').exists():
        raise moteur.ErreurCompta("Un exercice suivant est déjà clôturé : rouvrez d'abord celui-là.")
    with transaction.atomic():
        Ecriture.all_objects.filter(origine__startswith=f'an:{exercice.pk}:').delete()
        exercice.statut = 'ouvert'
        exercice.resultat = None
        exercice.date_cloture = None
        exercice.cloture_par = None
        exercice.save()
    return exercice
