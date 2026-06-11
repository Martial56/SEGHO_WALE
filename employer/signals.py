from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='employer.Employe')
def init_solde_conge(sender, instance, created, **kwargs):
    """Crée automatiquement un SoldeConge pour l'année en cours lors de l'embauche."""
    if not created or instance.statut != 'actif':
        return
    from datetime import date
    from employer.models import SoldeConge
    from employer.utils import quota_annuel
    annee = date.today().year
    SoldeConge.objects.get_or_create(
        employe=instance,
        annee=annee,
        defaults={'quota': quota_annuel(instance)},
    )
