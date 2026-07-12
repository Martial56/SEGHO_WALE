from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(pre_save, sender='employer.Employe')
def set_date_depart(sender, instance, **kwargs):
    """Renseigne automatiquement la date de départ au moment où le statut
    passe à 'quitte' (et l'efface si le statut est corrigé vers autre chose).

    Remplace l'ancienne approximation du tableau de bord RH qui comptait les
    "départs de l'année" via modifie_le (n'importe quelle modification de la
    fiche, même sans rapport avec un départ, faussait ce chiffre)."""
    from datetime import date

    if not instance.pk:
        if instance.statut == 'quitte' and not instance.date_depart:
            instance.date_depart = date.today()
        return

    ancien_statut = sender.objects.filter(pk=instance.pk).values_list('statut', flat=True).first()
    if instance.statut == 'quitte' and ancien_statut != 'quitte':
        instance.date_depart = date.today()
    elif instance.statut != 'quitte' and ancien_statut == 'quitte':
        instance.date_depart = None


@receiver(post_save, sender='employer.Employe')
def init_solde_conge(sender, instance, created, **kwargs):
    """Crée automatiquement un SoldeConge pour l'année en cours lors de l'embauche."""
    if not created or instance.statut != 'actif':
        return
    from datetime import date
    from employer.models import SoldeConge
    from conges.utils import quota_annuel
    annee = date.today().year
    SoldeConge.objects.get_or_create(
        employe=instance,
        annee=annee,
        defaults={'quota': quota_annuel(instance)},
    )
