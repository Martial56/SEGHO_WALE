from django.db import models
from django.contrib.auth.models import User
from datetime import time


class PlanningPermanence(models.Model):
    """Planification hebdomadaire des permanences."""
    semaine_du  = models.DateField(unique=True, verbose_name="Semaine du (lundi)")
    heure_debut = models.TimeField(default=time(8, 0),  verbose_name="Heure d'arrivée")
    heure_fin   = models.TimeField(default=time(15, 0), verbose_name="Heure de départ")
    cree_par    = models.ForeignKey(User, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='+')
    cree_le     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Permanences semaine du {self.semaine_du:%d/%m/%Y}"

    class Meta:
        verbose_name = "Planning permanence"
        verbose_name_plural = "Plannings permanence"
        ordering = ['-semaine_du']


class AffectationPermanence(models.Model):
    """Affectation d'un employé en permanence pour un jour précis."""
    planning = models.ForeignKey(PlanningPermanence, on_delete=models.CASCADE,
                                  related_name='affectations')
    employe  = models.ForeignKey('employer.Employe', on_delete=models.CASCADE,
                                  related_name='permanences')
    date     = models.DateField(verbose_name="Date de permanence")

    def __str__(self):
        return f"{self.employe} — permanence {self.date:%d/%m/%Y}"

    class Meta:
        unique_together = ['employe', 'date']
        verbose_name = "Affectation permanence"
        verbose_name_plural = "Affectations permanence"
        ordering = ['date', 'employe__nom']
