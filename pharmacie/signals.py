from django.db.models.signals import post_save
from django.dispatch import receiver

from stock.models import Produit
from .models import StockPharmacie, PHARMACIES_WALE


@receiver(post_save, sender=Produit)
def creer_stock_pharmacie_initial(sender, instance, created, **kwargs):
    """Rend un nouveau produit du stock immédiatement visible dans chaque pharmacie (quantité 0)."""
    if not created:
        return
    for code, _ in PHARMACIES_WALE:
        StockPharmacie.objects.get_or_create(pharmacie=code, produit=instance)
