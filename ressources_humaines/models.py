from django.db import models
from django.contrib.auth.models import User


class Poste(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    service = models.ForeignKey('medecins.Service', on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Poste"


class Employe(models.Model):
    STATUT = [('actif','Actif'),('conge','En congé'),('suspendu','Suspendu'),('quitte','A quitté')]

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    matricule = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    poste = models.ForeignKey(Poste, on_delete=models.SET_NULL, null=True)
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    date_embauche = models.DateField()
    date_fin_contrat = models.DateField(null=True, blank=True)
    salaire_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUT, default='actif')

    def __str__(self): return f"{self.nom} {self.prenoms} ({self.matricule})"
    class Meta:
        verbose_name = "Employé"
        ordering = ['nom']


class Conge(models.Model):
    TYPE = [('annuel','Congé annuel'),('maladie','Congé maladie'),('maternite','Congé maternité'),('exceptionnel','Congé exceptionnel')]
    STATUT = [('demande','Demandé'),('approuve','Approuvé'),('refuse','Refusé'),('en_cours','En cours'),('termine','Terminé')]

    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='conges')
    type_conge = models.CharField(max_length=20, choices=TYPE)
    date_debut = models.DateField()
    date_fin = models.DateField()
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='demande')
    approuve_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date_demande = models.DateTimeField(auto_now_add=True)

    @property
    def duree(self):
        return (self.date_fin - self.date_debut).days + 1

    def __str__(self): return f"Congé {self.employe} - {self.date_debut}"
    class Meta: verbose_name = "Congé"


class Presence(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='presences')
    date = models.DateField()
    heure_arrivee = models.TimeField(null=True, blank=True)
    heure_depart = models.TimeField(null=True, blank=True)
    present = models.BooleanField(default=True)
    motif_absence = models.CharField(max_length=200, blank=True)

    def __str__(self): return f"Présence {self.employe} - {self.date}"
    class Meta:
        verbose_name = "Présence"
        unique_together = ['employe', 'date']
        ordering = ['-date']
