from django.db import models
from django.contrib.auth.models import User


class RapportMedical(models.Model):
    TYPE = [('mensuel','Mensuel'),('trimestriel','Trimestriel'),('annuel','Annuel'),('activite','Activité'),('directeur','Rapport directeur')]

    titre = models.CharField(max_length=300)
    type_rapport = models.CharField(max_length=20, choices=TYPE)
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    contenu = models.TextField(blank=True)
    fichier = models.FileField(upload_to='rapports/', blank=True, null=True)
    redige_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    valide = models.BooleanField(default=False)
    valide_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rapports_valides')

    def __str__(self): return self.titre
    class Meta:
        verbose_name = "Rapport médical"
        ordering = ['-date_creation']


class Vaccination(models.Model):
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='vaccinations')
    vaccin = models.CharField(max_length=200)
    date_vaccination = models.DateField()
    dose = models.CharField(max_length=50, blank=True)
    lot = models.CharField(max_length=100, blank=True)
    prochain_rappel = models.DateField(null=True, blank=True)
    administre_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    def __str__(self): return f"Vaccination {self.vaccin} - {self.patient}"
    class Meta:
        verbose_name = "Vaccination"
        ordering = ['-date_vaccination']
