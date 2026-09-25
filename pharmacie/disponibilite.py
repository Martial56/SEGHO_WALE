"""Ce que la pharmacie du centre actif a réellement en rayon.

Une seule règle, écrite une seule fois, pour la prescription, la facturation et
tout écran qui propose un produit au personnel.

**Pourquoi la pharmacie et non le magasin.** `stock.Produit` porte un
`stock_actuel` : c'est la quantité de la réserve centrale, pas celle du
comptoir. Proposer cette liste à Toumbokro revient à proposer ce qui dort à
Yamoussoukro, à quarante kilomètres — le patient repart les mains vides. La
quantité qui compte est celle de `StockPharmacie`, une ligne par produit **et
par pharmacie**.

**La règle.** Un produit dont la pharmacie du centre actif n'a plus rien — ou
qu'elle n'a jamais reçu — reste visible mais grisé, et ne peut être ni facturé
ni prescrit. Le grisé plutôt que l'effacement : cacher le produit ferait croire
qu'il n'existe pas, et la désignation serait ressaisie à la main, ce qu'on
cherche justement à éviter. S'il est indispensable, il part sur une ordonnance
physique, à acheter en externe.

**La façade grise, le serveur refuse.** `est_disponible` est le garde-fou : une
liste déroulante ne protège rien, et la dernière boîte peut partir entre le
moment où l'écran s'affiche et celui où l'on enregistre.
"""

from decimal import Decimal

from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce

from .models import PHARMACIE_CENTRE_CODE


#: Natures proposées par défaut. Les consommables en sont : une paire de gants
#: posée sur une facture d'examen est aussi légitime qu'un comprimé, et c'est
#: leur absence qui a lancé ce chantier. Les équipements en sont exclus — on ne
#: vend pas un tensiomètre à un patient.
TYPES_PROPOSES = ('medicament', 'consommable')


def pharmacie_du_centre(centre):
    """Code de pharmacie desservant ce centre, ou None s'il n'en a pas.

    Le rattachement vit dans `PHARMACIE_CENTRE_CODE` : un centre ajouté au
    déploiement sans y être inscrit n'a pas de pharmacie, et les listes sortent
    vides plutôt que de montrer celles d'un autre centre.
    """
    if centre is None:
        return None
    for pharmacie, code_centre in PHARMACIE_CENTRE_CODE.items():
        if code_centre == centre.code:
            return pharmacie
    return None


def pharmacie_active(request=None):
    """Pharmacie du centre actif de la personne connectée.

    Se déduit du centre où l'on est, et non du médecin choisi sur le
    formulaire : c'est là que le patient sera servi. Les 59 médecins du fichier
    n'ont d'ailleurs aucun compte utilisateur, donc aucun centre à interroger.
    """
    from core.middleware import get_current_centre

    centre = getattr(request, 'centre', None) if request is not None else None
    if centre is None:
        centre = get_current_centre()
    return pharmacie_du_centre(centre)


def produits_de_la_pharmacie(pharmacie, types=TYPES_PROPOSES, disponibles_seulement=False):
    """Produits proposables, avec la quantité de cette pharmacie annotée.

    L'annotation s'appelle `stock_pharma`. Elle vaut zéro pour un produit que
    la pharmacie n'a jamais reçu : la jointure est en `filter=` justement pour
    que ces produits sortent quand même, à zéro, plutôt que d'être écartés par
    la jointure — sans quoi « jamais reçu » et « en rupture » ne se
    présenteraient pas de la même façon à l'écran alors qu'ils veulent dire la
    même chose pour le patient.

    `disponibles_seulement` réduit à ce qui est réellement en rayon : c'est ce
    que veulent les traitements qui enregistrent, quand l'écran, lui, affiche
    aussi les ruptures en grisé.
    """
    from stock.models import Produit

    if pharmacie is None:
        return Produit.objects.none()

    qs = (
        Produit.objects
        .filter(type__in=types, actif=True)
        .annotate(
            stock_pharma=Coalesce(
                Sum('stocks_pharmacie__quantite',
                    filter=Q(stocks_pharmacie__pharmacie=pharmacie)),
                Decimal('0'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .order_by('type', 'nom')
    )
    return qs.filter(stock_pharma__gt=0) if disponibles_seulement else qs


def produits_proposes(request=None, types=TYPES_PROPOSES, disponibles_seulement=False):
    """Raccourci : les produits de la pharmacie du centre actif."""
    return produits_de_la_pharmacie(
        pharmacie_active(request), types=types,
        disponibles_seulement=disponibles_seulement,
    )


def en_rayon(produit):
    """Quantité annotée par `produits_de_la_pharmacie`, sous forme lisible."""
    return getattr(produit, 'stock_pharma', Decimal('0')) or Decimal('0')


def est_disponible(produit_id, pharmacie, quantite=1):
    """Cette pharmacie peut-elle servir cette quantité de ce produit ?

    Le garde-fou du serveur. L'écran grise les ruptures, mais une liste
    déroulante ne protège de rien : une URL forgée, un onglet resté ouvert une
    heure, ou simplement la dernière boîte partie entre l'affichage et
    l'enregistrement.
    """
    from .models import StockPharmacie

    if not produit_id or pharmacie is None:
        return False
    try:
        quantite = Decimal(str(quantite))
    except (TypeError, ValueError, ArithmeticError):
        return False
    if quantite <= 0:
        return False
    ligne = StockPharmacie.objects.filter(
        pharmacie=pharmacie, produit_id=produit_id).first()
    return ligne is not None and ligne.quantite >= quantite


def produits_pour_ecran(request=None, types=TYPES_PROPOSES, pharmacie=None):
    """Les produits proposables, sous la forme attendue par les écrans.

    Les clés reprennent celles que le gabarit d'ordonnance lisait déjà, pour
    qu'il n'ait pas à être réécrit : `stock_actuel` y désigne désormais le stock
    **de la pharmacie**, ce qu'il aurait toujours dû désigner.

    `rupture` est ce qui distingue cette liste de l'ancienne : la façade s'en
    sert pour griser et interdire le clic, plutôt que d'afficher un chiffre
    rouge sur lequel on pouvait tout de même appuyer.
    """
    if pharmacie is None:
        pharmacie = pharmacie_active(request)
    return [
        {
            'pk':            p.pk,
            'designation':   p.nom,
            'type':          p.type,
            'forme':         p.get_forme_display() if p.forme else '',
            'dosage':        p.dosage or '',
            'dci':           p.dci or '',
            'prix_vente':    float(p.prix_vente or 0),
            'stock_actuel':  float(en_rayon(p)),
            'stock_alerte':  float(p.stock_alerte),
            'stock_minimum': float(p.stock_minimum),
            'rupture':       en_rayon(p) <= 0,
        }
        for p in produits_de_la_pharmacie(pharmacie, types=types)
    ]
