from django.db import models
from django.contrib.auth.models import User


class Specialite(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta: verbose_name = "Spécialité"


class Medecin(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    matricule = models.CharField(max_length=20, unique=True, blank=True, null=True)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True)
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    ordre_medecin = models.CharField(max_length=50, blank=True)
    taux_honoraire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Dr {self.nom} {self.prenoms}"
    class Meta:
        verbose_name = "Médecin"
        ordering = ['nom']


class Service(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    chef_service = models.ForeignKey(Medecin, on_delete=models.SET_NULL, null=True, blank=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta: verbose_name = "Service"
