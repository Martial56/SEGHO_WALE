from django.contrib.auth.models import User
from django.db import models


class HistoriqueRapport(models.Model):
    FORMAT = [('xlsx', 'Excel'), ('csv', 'CSV')]

    slug = models.CharField(max_length=50, verbose_name="Rapport")
    nom = models.CharField(max_length=150, verbose_name="Nom du rapport")
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='rapports_generes')
    periode_debut = models.DateField(verbose_name="Période — début")
    periode_fin = models.DateField(verbose_name="Période — fin")
    format_fichier = models.CharField(max_length=10, choices=FORMAT)
    nb_lignes = models.PositiveIntegerField(default=0)
    fichier = models.FileField(upload_to='rapports/%Y/%m/', null=True, blank=True)
    date_generation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} — {self.utilisateur} ({self.date_generation:%d/%m/%Y %H:%M})"

    class Meta:
        verbose_name = "Rapport généré"
        verbose_name_plural = "Historique des rapports"
        ordering = ['-date_generation']
