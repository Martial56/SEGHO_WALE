from django.db import models


class TypeVisite(models.Model):
    nom           = models.CharField(max_length=200, verbose_name='Nom')
    code          = models.CharField(max_length=50, unique=True, verbose_name='Code')
    description   = models.TextField(blank=True, verbose_name='Description')
    actif         = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Type de visite"
        ordering = ['nom']
