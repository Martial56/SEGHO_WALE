"""
Achats et dons en nature (lot 8 du module Comptabilité).

Les stocks se tiennent en **inventaire intermittent**, la méthode courante
des structures sanitaires OHADA : un achat de médicaments va directement en
charge (601, 604) ; le stock (31x) n'est ajusté qu'une fois l'an, par
l'inventaire de clôture (variation 603x, voir cloture.py). On n'a donc pas à
valoriser chaque dispensation.

- **Facture fournisseur** : charge (ou immobilisation) au débit, dette 401 au
  crédit, dès la réception de la facture. Elle peut reprendre la valeur reçue
  d'une commande de stock ou d'achat.
- **Règlement fournisseur** : la dette s'éteint, la trésorerie baisse.
- **Don en nature** : les produits reçus entrent dans le stock central (lot,
  péremption, mouvement « Don ») ; leur valeur fait le montant du don, porté à
  l'actif du stock en contrepartie de la ressource.
"""
from decimal import Decimal

from django.db import transaction

from . import ecritures as moteur
from .models import Compte, Ecriture, FactureFournisseur, LigneDon, LigneFactureFournisseur, ReglementFournisseur

ZERO = Decimal('0')


class ErreurAchat(Exception):
    """Refus d'une opération d'achat, avec un message pour l'utilisateur."""


def _francs(m):
    return f"{m:,.0f}".replace(',', ' ')


def noms_fournisseurs():
    """Fournisseurs connus des modules Achats et Stock, et des factures déjà saisies."""
    from achats.models import Fournisseur as FournisseurAchats
    from stock.models import Fournisseur as FournisseurStock
    noms = set(FournisseurAchats.objects.filter(actif=True).values_list('nom', flat=True))
    noms |= set(FournisseurStock.objects.filter(actif=True).values_list('nom', flat=True))
    noms |= set(FactureFournisseur.objects.values_list('fournisseur', flat=True).distinct())
    return sorted(n for n in noms if n)


def _compte_achat(type_):
    try:
        return moteur.compte(f'achat:{type_}')
    except moteur.ErreurCompta:
        return moteur.compte('sortie_defaut')


def lignes_commande_stock(commande):
    """Valeur reçue d'une commande de stock, regroupée par type de produit."""
    par_type = {}
    for l in commande.lignes.select_related('produit'):
        montant = (l.quantite_recue * l.prix_unitaire).quantize(Decimal('0.01'))
        if montant:
            par_type[l.produit.type] = par_type.get(l.produit.type, ZERO) + montant
    from stock.models import Produit
    libelles = dict(Produit.TYPE_CHOICES)
    return [(_compte_achat(t), f'{libelles.get(t, t)} — commande {commande.numero}', m) for t, m in par_type.items()]


def lignes_commande_achat(commande):
    """Valeur reçue d'une commande d'achat (somme de ses réceptions), par type d'article."""
    from achats.models import LigneReceptionAchat
    par_type = {}
    for l in (LigneReceptionAchat.objects.filter(reception__commande=commande)
              .select_related('ligne_commande__ligne_proforma__ligne_besoin__article')):
        lc = l.ligne_commande
        article = getattr(getattr(lc.ligne_proforma, 'ligne_besoin', None), 'article', None)
        type_ = article.type if article else 'autre'
        montant = (l.quantite_recue * lc.prix_unitaire).quantize(Decimal('0.01'))
        if montant:
            par_type[type_] = par_type.get(type_, ZERO) + montant
    return [(_compte_achat(t), f'Commande {commande.numero}', m) for t, m in par_type.items()]


# ─── Factures et règlements ────────────────────────────────────────────────────

def comptes_d_achat():
    """Comptes acceptés sur une ligne de facture : immobilisations et charges."""
    return Compte.objects.filter(actif=True, numero__regex=r'^[26]')


def enregistrer_facture(facture, lignes, par):
    """Enregistre la facture et ses lignes [(compte, libellé, montant)], puis
    prépare son écriture d'achat en brouillon."""
    lignes = [(c, (lib or '').strip(), m) for c, lib, m in lignes if m]
    if not lignes:
        raise ErreurAchat("Une facture compte au moins une ligne avec un montant.")
    for c, _, m in lignes:
        if m <= 0:
            raise ErreurAchat("Les montants des lignes doivent être positifs.")
        if c.classe not in ('2', '6'):
            raise ErreurAchat(f"Le compte {c.numero} n'est ni une charge (classe 6) ni une immobilisation (classe 2).")
    if facture.pk and Ecriture.all_objects.filter(origine=f'facture_fournisseur:{facture.pk}',
                                                  statut='validee').exists():
        raise ErreurAchat("Cette facture est déjà comptabilisée et validée : contre-passez son écriture "
                          "pour la corriger.")
    total = sum((m for _, _, m in lignes), ZERO)
    if facture.pk and total < facture.montant_regle:
        raise ErreurAchat(f"Le total ({_francs(total)} F) serait inférieur à ce qui est déjà réglé.")
    with transaction.atomic():
        facture.montant_total = total
        if not facture.cree_par_id:
            facture.cree_par = par
        facture.save()
        facture.lignes.all().delete()
        LigneFactureFournisseur.objects.bulk_create([
            LigneFactureFournisseur(facture=facture, compte=c, libelle=lib or facture.objet or facture.fournisseur,
                                    montant=m) for c, lib, m in lignes])
        Ecriture.all_objects.filter(origine=f'facture_fournisseur:{facture.pk}', statut='brouillon').delete()
        moteur.ecriture_facture_fournisseur(facture)
    return facture


def regler(facture, montant, jour, mode, par, compte_tresorerie=None, reference=''):
    if montant is None or montant <= 0:
        raise ErreurAchat("Le montant réglé doit être positif.")
    if montant > facture.reste:
        raise ErreurAchat(f"Il ne reste que {_francs(facture.reste)} F à régler sur cette facture.")
    with transaction.atomic():
        reglement = ReglementFournisseur.objects.create(
            facture=facture, date=jour, montant=montant, mode=mode, compte_tresorerie=compte_tresorerie,
            reference=reference, cree_par=par, centre=facture.centre)
        moteur.ecriture_reglement_fournisseur(reglement)
    return reglement


# ─── Dons en nature : entrée en stock ──────────────────────────────────────────

def entrer_don_en_stock(don, lignes, par):
    """Fait entrer dans le stock central les produits d'un don en nature.

    `lignes` : [(produit, quantité, valeur unitaire, n° de lot, péremption)].
    Le montant du don devient la valeur des produits reçus, et son écriture
    (encore en brouillon) est refaite pour les porter au stock.
    """
    from stock.models import LotProduit, MouvementStock, Produit

    if don.nature != 'nature':
        raise ErreurAchat("Seul un don en nature entre en stock.")
    if don.lignes.exists():
        raise ErreurAchat("Les produits de ce don sont déjà entrés en stock.")
    if Ecriture.all_objects.filter(origine=f'don:{don.pk}', statut='validee').exists():
        raise ErreurAchat("L'écriture de ce don est déjà validée : son montant ne peut plus changer.")
    lignes = [l for l in lignes if l[1] and l[1] > 0]
    if not lignes:
        raise ErreurAchat("Indiquez au moins un produit reçu, avec sa quantité.")
    if any(l[2] is None or l[2] < 0 for l in lignes):
        raise ErreurAchat("La valeur unitaire d'un produit ne peut pas être négative.")
    with transaction.atomic():
        for produit, quantite, valeur, numero_lot, peremption in lignes:
            produit = Produit.objects.select_for_update().get(pk=produit.pk)
            lot = LotProduit.objects.create(
                produit=produit, numero_lot=numero_lot or f'{don.numero}-{produit.code}',
                quantite_initiale=quantite, quantite_actuelle=quantite, date_reception=don.date,
                prix_achat_lot=valeur, date_peremption=peremption, notes=f'Don {don.numero} — {don.nom_donateur}')
            avant = produit.stock_actuel
            mouvement = MouvementStock.objects.create(
                produit=produit, lot=lot, type='entree', motif='don', quantite=quantite,
                stock_avant=avant, stock_apres=avant + quantite, reference=don.numero,
                notes=f'Don de {don.nom_donateur}', cree_par=par)
            produit.stock_actuel = avant + quantite
            produit.save(update_fields=['stock_actuel'])
            LigneDon.objects.create(don=don, produit=produit, quantite=quantite, valeur_unitaire=valeur,
                                    numero_lot=lot.numero_lot, date_peremption=peremption, mouvement=mouvement)
        don.montant = sum((l.montant for l in don.lignes.all()), ZERO)
        don.save(update_fields=['montant'])
        Ecriture.all_objects.filter(origine=f'don:{don.pk}', statut='brouillon').delete()
        if don.montant:
            moteur.ecriture_don(don)
    return don
