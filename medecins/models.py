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
        'employer.Employe', on_delete=models.CASCADE,
        related_name='fiche_medecin',
        verbose_name="Employé lié",
    )
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True)
    departement = models.ForeignKey('Departement', on_delete=models.SET_NULL, null=True, blank=True, related_name='medecins', verbose_name="Département")
    service = models.ForeignKey('Service', on_delete=models.SET_NULL, null=True, blank=True, related_name='medecins', verbose_name="Service")
    ordre_medecin = models.CharField(max_length=50, blank=True)
    taux_honoraire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    # Identité et coordonnées désormais portées par l'Employé lié — un médecin
    # est avant tout un employé, pas une fiche d'identité séparée.
    @property
    def matricule(self): return self.employe.matricule
    @property
    def nom(self): return self.employe.nom
    @property
    def prenoms(self): return self.employe.prenoms
    @property
    def telephone(self): return self.employe.telephone
    @property
    def email(self): return self.employe.email
    @property
    def photo(self): return self.employe.photo

    def __str__(self): return f"Dr {self.nom} {self.prenoms}"
    class Meta:
        verbose_name = "Médecin"
        ordering = ['employe__nom']


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
