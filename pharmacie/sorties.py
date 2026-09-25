"""Sortie du stock des produits portés par une facture.

Facturer un produit, c'est le remettre au patient : le comptoir doit en compter
un de moins. Le mouvement se fait **au paiement**, pas à la saisie — une facture
en brouillon n'immobilise rien, et tant que l'argent n'est pas encaissé le
produit reste disponible pour quelqu'un d'autre.

Trois précautions, et chacune répond à un cas réel :

* **On revérifie au paiement.** La dernière boîte a pu partir entre la saisie de
  la ligne et l'encaissement. Le règlement est alors refusé plutôt que de
  laisser le stock mentir : on ne prend pas l'argent d'un produit qu'on ne peut
  pas remettre.
* **On ne sort jamais deux fois.** Chaque mouvement porte le numéro de la
  facture ; un second appel — un double clic, un rejeu — ne trouve rien à faire.
* **Annuler rend le produit.** Une facture payée puis annulée remet ses produits
  en rayon, par un mouvement inverse tout aussi tracé.

Les lignes sans produit — un acte, un examen, une désignation tapée à la main —
ne concernent pas la pharmacie et sont ignorées.
"""

from django.db import transaction

from .models import MouvementPharmacie, StockPharmacie


#: Type de mouvement des sorties faites par la facturation, distinct de la vente
#: au comptoir (`vente`) : les deux portes existent et se lisent séparément dans
#: le journal de la pharmacie.
TYPE_SORTIE = 'facture'
TYPE_RETOUR = 'retour'


def _lignes_de_produit(facture):
    """Lignes de la facture qui portent un produit du stock."""
    return [l for l in facture.lignes.select_related('produit') if l.produit_id]


def deja_traitee(facture, pharmacie, type_mouvement=TYPE_SORTIE):
    """Cette facture a-t-elle déjà donné lieu à ce mouvement ?"""
    return MouvementPharmacie.objects.filter(
        pharmacie=pharmacie, type=type_mouvement, reference=facture.numero).exists()


def produits_indisponibles(facture, pharmacie):
    """Produits que la pharmacie ne peut plus servir, avec ce qui manque.

    Renvoie une liste de (nom, demandé, en rayon), vide quand tout est servable.
    Les quantités d'une même facture s'additionnent : deux lignes de cinq
    boîtes en demandent dix, pas cinq.
    """
    lignes = _lignes_de_produit(facture)
    if not lignes or pharmacie is None:
        return []

    demandes = {}
    for ligne in lignes:
        demandes[ligne.produit_id] = demandes.get(ligne.produit_id, 0) + ligne.quantite

    en_rayon = dict(
        StockPharmacie.objects
        .filter(pharmacie=pharmacie, produit_id__in=demandes)
        .values_list('produit_id', 'quantite')
    )
    noms = {l.produit_id: l.produit.nom for l in lignes}

    manquants = []
    for produit_id, demande in demandes.items():
        disponible = en_rayon.get(produit_id, 0)
        if disponible < demande:
            manquants.append((noms[produit_id], demande, disponible))
    return manquants


@transaction.atomic
def sortir_les_produits(facture, pharmacie, user=None):
    """Retire du stock les produits de la facture. Sans effet si déjà fait.

    Suppose la disponibilité déjà vérifiée par `produits_indisponibles` : c'est
    l'appelant qui décide quoi faire d'un manque, parce que lui seul sait s'il
    peut encore refuser le règlement.
    """
    lignes = _lignes_de_produit(facture)
    if not lignes or pharmacie is None or deja_traitee(facture, pharmacie):
        return 0

    sortis = 0
    for ligne in lignes:
        # `select_for_update` : deux caissiers encaissant en même temps liraient
        # sinon la même quantité de départ, et le second écraserait le premier.
        stock = (StockPharmacie.objects.select_for_update()
                 .filter(pharmacie=pharmacie, produit_id=ligne.produit_id).first())
        if stock is None:
            continue
        avant = stock.quantite
        stock.quantite = avant - ligne.quantite
        stock.save(update_fields=['quantite'])
        MouvementPharmacie.objects.create(
            pharmacie=pharmacie, produit_id=ligne.produit_id,
            type=TYPE_SORTIE, quantite=ligne.quantite,
            stock_avant=avant, stock_apres=stock.quantite,
            reference=facture.numero,
            notes=f"Facture {facture.numero} — {ligne.libelle}",
            cree_par=user,
        )
        sortis += 1
    return sortis


@transaction.atomic
def rendre_les_produits(facture, pharmacie, user=None):
    """Remet en rayon les produits d'une facture annulée après paiement."""
    lignes = _lignes_de_produit(facture)
    if (not lignes or pharmacie is None
            or not deja_traitee(facture, pharmacie)
            or deja_traitee(facture, pharmacie, TYPE_RETOUR)):
        return 0

    rendus = 0
    for ligne in lignes:
        stock, _ = StockPharmacie.objects.select_for_update().get_or_create(
            pharmacie=pharmacie, produit_id=ligne.produit_id)
        avant = stock.quantite
        stock.quantite = avant + ligne.quantite
        stock.save(update_fields=['quantite'])
        MouvementPharmacie.objects.create(
            pharmacie=pharmacie, produit_id=ligne.produit_id,
            type=TYPE_RETOUR, quantite=ligne.quantite,
            stock_avant=avant, stock_apres=stock.quantite,
            reference=facture.numero,
            notes=f"Annulation de la facture {facture.numero} — {ligne.libelle}",
            cree_par=user,
        )
        rendus += 1
    return rendus
