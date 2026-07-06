from decimal import Decimal

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver


# ──────────────────────────────────────────────────────────────
# Consultation → synchronisation statut RendezVous
# ──────────────────────────────────────────────────────────────

@receiver(post_save, sender='consultations.Consultation')
def sync_rdv_statut(sender, instance, created, **kwargs):
    if not instance.rendez_vous_id:
        return
    try:
        rdv = instance.rendez_vous
    except Exception:
        return

    TERMINAL = ('termine', 'annule', 'absent')

    if created:
        if rdv.statut == 'en_attente':
            rdv.statut = 'en_consultation'
            rdv.save(update_fields=['statut'])
    else:
        if instance.statut == 'termine' and rdv.statut not in TERMINAL:
            rdv.statut = 'termine'
            rdv.save(update_fields=['statut'])
        elif instance.statut == 'annule' and rdv.statut not in TERMINAL:
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])


# ──────────────────────────────────────────────────────────────
# LigneOrdonnance → déduction StockPharmacie.quantite
#
# Le module Pharmacie affiche StockPharmacie.quantite (stock
# local par pharmacie). On décrémente ce champ dès la création
# de l'ordonnance pour que la pharmacie voie immédiatement la
# réservation. La dispensation vérifie ensuite si le stock a
# déjà été réservé (MouvementPharmacie avec ref ORD:xxx) afin
# d'éviter toute double déduction.
# ──────────────────────────────────────────────────────────────

_PRE_REF_PREFIX = 'ORD:'


def _ref_pre(ordonnance_numero):
    return f'{_PRE_REF_PREFIX}{ordonnance_numero}'


def _get_ordonnance_numero(ligne):
    try:
        return ligne.ordonnance.numero
    except Exception:
        return ''


def _stock_pharmacie_le_plus_fourni(produit_id):
    """Retourne le StockPharmacie avec la quantité la plus élevée pour ce produit."""
    from pharmacie.models import StockPharmacie
    return (
        StockPharmacie.objects
        .filter(produit_id=produit_id, quantite__gt=0)
        .order_by('-quantite')
        .first()
    )


def _reserver_stock(produit_id, qte, ref):
    """
    Déduit qte de la pharmacie la mieux approvisionnée.
    Retourne l'instance StockPharmacie modifiée ou None.
    """
    from pharmacie.models import StockPharmacie, MouvementPharmacie
    sp = _stock_pharmacie_le_plus_fourni(produit_id)
    if not sp:
        return None
    avant = sp.quantite
    apres = max(Decimal('0'), avant - qte)
    sp.quantite = apres
    sp.save(update_fields=['quantite', 'date_maj'])
    MouvementPharmacie.objects.create(
        pharmacie=sp.pharmacie,
        produit_id=produit_id,
        type='dispensation',
        quantite=qte,
        stock_avant=avant,
        stock_apres=apres,
        reference=ref,
        notes='Réservation ordonnance (prescription)',
    )
    return sp


def _restituer_stock(produit_id, qte, ref):
    """
    Restitue qte dans la pharmacie qui avait fait la réservation
    (identifiée via MouvementPharmacie ref=ref, produit=produit_id).
    """
    from pharmacie.models import StockPharmacie, MouvementPharmacie
    mvt = MouvementPharmacie.objects.filter(
        reference=ref, produit_id=produit_id, type='dispensation'
    ).order_by('-date').first()
    if not mvt:
        return
    sp = StockPharmacie.objects.filter(
        pharmacie=mvt.pharmacie, produit_id=produit_id
    ).first()
    if not sp:
        return
    avant = sp.quantite
    apres = avant + qte
    sp.quantite = apres
    sp.save(update_fields=['quantite', 'date_maj'])
    MouvementPharmacie.objects.create(
        pharmacie=sp.pharmacie,
        produit_id=produit_id,
        type='retour',
        quantite=qte,
        stock_avant=avant,
        stock_apres=apres,
        reference=ref,
        notes='Annulation réservation ordonnance',
    )
    # Supprimer le MouvementPharmacie de réservation pour permettre
    # une nouvelle réservation propre si nécessaire.
    mvt.delete()


@receiver(pre_save, sender='consultations.LigneOrdonnance')
def ligne_ordonnance_pre_save(sender, instance, **kwargs):
    """Capture l'état précédent (produit + quantité) avant mise à jour."""
    if instance.pk:
        try:
            from consultations.models import LigneOrdonnance
            old = LigneOrdonnance.objects.get(pk=instance.pk)
            instance._old_produit_id = old.produit_id
            instance._old_quantite   = Decimal(str(old.quantite or 0))
        except Exception:
            instance._old_produit_id = None
            instance._old_quantite   = Decimal('0')
    else:
        instance._old_produit_id = None
        instance._old_quantite   = Decimal('0')


@receiver(post_save, sender='consultations.LigneOrdonnance')
def ligne_ordonnance_post_save(sender, instance, created, **kwargs):
    """
    Réserve le stock pharmacie lors de la création / modification
    d'une ligne d'ordonnance portant un produit catalogue.
    """
    ref     = _ref_pre(_get_ordonnance_numero(instance))
    new_pid = instance.produit_id
    new_qte = Decimal(str(instance.quantite or 0))
    old_pid = getattr(instance, '_old_produit_id', None)
    old_qte = getattr(instance, '_old_quantite',   Decimal('0'))

    if created:
        if new_pid and new_qte > 0:
            _reserver_stock(new_pid, new_qte, ref)
        return

    # ── Mise à jour ──────────────────────────────────────────
    produit_change = old_pid != new_pid

    if produit_change:
        # Restituer l'ancien produit, réserver le nouveau
        if old_pid and old_qte > 0:
            _restituer_stock(old_pid, old_qte, ref)
        if new_pid and new_qte > 0:
            _reserver_stock(new_pid, new_qte, ref)
    else:
        # Même produit : ajuster uniquement la différence
        if new_pid:
            diff = new_qte - old_qte
            if diff > 0:
                _reserver_stock(new_pid, diff, ref)
            elif diff < 0:
                _restituer_stock(new_pid, abs(diff), ref)


@receiver(post_delete, sender='consultations.LigneOrdonnance')
def ligne_ordonnance_post_delete(sender, instance, **kwargs):
    """Restitue le stock réservé quand une ligne est supprimée."""
    if not instance.produit_id:
        return
    qte = Decimal(str(instance.quantite or 0))
    if qte <= 0:
        return
    ref = _ref_pre(_get_ordonnance_numero(instance))
    _restituer_stock(instance.produit_id, qte, ref)
