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
    employe = models.OneToOneField(
        'employer.Employe', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fiche_medecin',
        verbose_name="Employé lié",
    )
    matricule = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True)
    departement = models.ForeignKey('Departement', on_delete=models.SET_NULL, null=True, blank=True, related_name='medecins', verbose_name="Département")
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    ordre_medecin = models.CharField(max_length=50, blank=True)
    photo = models.ImageField(upload_to='medecins/photos/', blank=True, null=True)
    taux_honoraire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Dr {self.nom} {self.prenoms}"
    class Meta:
        verbose_name = "Médecin"
        ordering = ['nom']


class Service(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    chef_service = models.ForeignKey(Medecin, on_delete=models.SET_NULL, null=True, blank=True, related_name='services_diriges')
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta: verbose_name = "Service"


class Departement(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Département"
        ordering = ['nom']


class ModuleSpecialise(models.Model):
    """Associe un module métier (ex: Gynécologie) à un ou plusieurs départements,
    pour piloter dynamiquement les vues spécialisées (ex: liste RDV Gynécologie)
    sans avoir à modifier le code."""
    code = models.CharField(max_length=30, unique=True)
    nom = models.CharField(max_length=100)
    departements = models.ManyToManyField(Departement, blank=True, related_name='modules_specialises')
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Module spécialisé"
        ordering = ['nom']
