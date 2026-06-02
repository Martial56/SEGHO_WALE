from django.db import models
from django.contrib.auth.models import User


class Chambre(models.Model):
    TYPE = [('simple','Simple'),('double','Double'),('vip','VIP'),('soins_intensifs','Soins intensifs'),('observation','Observation')]

    numero = models.CharField(max_length=20, unique=True)
    type_chambre = models.CharField(max_length=20, choices=TYPE, default='simple')
    service = models.ForeignKey('medecins.Service', on_delete=models.SET_NULL, null=True, blank=True)
    capacite = models.IntegerField(default=1)
    prix_jour = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    disponible = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    def __str__(self): return f"Chambre {self.numero} ({self.get_type_chambre_display()})"
    class Meta: verbose_name = "Chambre"


class Hospitalisation(models.Model):
    STATUT = [('admis','Admis'),('en_soins','En soins'),('sortie_prevue','Sortie prévue'),('sorti','Sorti'),('transfere','Transféré'),('decede','Décédé')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='hospitalisations')
    medecin_traitant = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True)
    chambre = models.ForeignKey(Chambre, on_delete=models.SET_NULL, null=True)
    date_admission = models.DateTimeField(auto_now_add=True)
    date_sortie_prevue = models.DateField(null=True, blank=True)
    date_sortie_effective = models.DateTimeField(null=True, blank=True)
    motif_admission = models.TextField()
    diagnostic_admission = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='admis')
    caution = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    caution_payee = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = Hospitalisation.objects.filter(date_admission__year=annee).count() + 1
            self.numero = f"HOSP{annee}{count:05d}"
        super().save(*args, **kwargs)

    @property
    def duree_sejour(self):
        from django.utils import timezone
        fin = self.date_sortie_effective or timezone.now()
        delta = fin - self.date_admission
        return delta.days

    def __str__(self): return f"Hosp. {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Hospitalisation"
        ordering = ['-date_admission']


class FicheVisite(models.Model):
    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE, related_name='fiches_visite')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True)
    date_visite = models.DateTimeField(auto_now_add=True)
    observation = models.TextField()
    evolution = models.TextField(blank=True)
    prescriptions = models.TextField(blank=True)
    constantes = models.JSONField(default=dict, blank=True)

    def __str__(self): return f"Visite {self.hospitalisation.numero} - {self.date_visite.strftime('%d/%m/%Y')}"
    class Meta:
        verbose_name = "Fiche de visite"
        ordering = ['-date_visite']


class ProtocoleHospitalisation(models.Model):
    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE, related_name='protocoles')
    titre = models.CharField(max_length=200)
    description = models.TextField()
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return f"Protocole: {self.titre}"
    class Meta: verbose_name = "Protocole hospitalisation"
