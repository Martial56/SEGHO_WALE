from django.db import models
from django.contrib.auth.models import User


class Consultation(models.Model):
    STATUT = [('en_cours','En cours'),('termine','Terminé'),('annule','Annulé')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='consultations')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, related_name='consultations')
    rendez_vous = models.OneToOneField('patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True)
    date_heure = models.DateTimeField(auto_now_add=True)
    motif = models.TextField()
    anamnese = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='en_cours')
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = Consultation.objects.filter(date_heure__year=annee).count() + 1
            self.numero = f"CONS{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Consultation {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Consultation"
        ordering = ['-date_heure']


class Constante(models.Model):
    consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE, related_name='constantes')
    poids = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    taille = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    tension_systolique = models.IntegerField(null=True, blank=True)
    tension_diastolique = models.IntegerField(null=True, blank=True)
    pouls = models.IntegerField(null=True, blank=True)
    saturation_oxygene = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    glycemie = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    date_saisie = models.DateTimeField(auto_now_add=True)

    @property
    def imc(self):
        if self.poids and self.taille and self.taille > 0:
            taille_m = float(self.taille) / 100
            return round(float(self.poids) / (taille_m ** 2), 2)
        return None


class DiagnosticCIM(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=500)
    categorie = models.CharField(max_length=100, blank=True)

    def __str__(self): return f"{self.code} - {self.libelle}"
    class Meta: verbose_name = "Diagnostic CIM"


class Diagnostic(models.Model):
    TYPE = [('principal','Principal'),('associe','Associé'),('differentiel','Différentiel')]
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='diagnostics')
    cim = models.ForeignKey(DiagnosticCIM, on_delete=models.SET_NULL, null=True, blank=True)
    libelle_libre = models.CharField(max_length=500, blank=True)
    type_diagnostic = models.CharField(max_length=20, choices=TYPE, default='principal')
    notes = models.TextField(blank=True)

    def __str__(self): return self.libelle_libre or str(self.cim)


class Ordonnance(models.Model):
    STATUT = [('emise','Émise'),('delivree','Délivrée'),('partielle','Partielle'),('expiree','Expirée')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='ordonnances')
    date_emission = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='emise')
    notes = models.TextField(blank=True)
    type_ordonnance = models.CharField(max_length=20, choices=[('interne','Interne'),('externe','Externe')], default='interne')

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = Ordonnance.objects.filter(date_emission__year=annee).count() + 1
            self.numero = f"ORD{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Ordonnance {self.numero}"
    class Meta: verbose_name = "Ordonnance"


class LigneOrdonnance(models.Model):
    ordonnance = models.ForeignKey(Ordonnance, on_delete=models.CASCADE, related_name='lignes')
    medicament = models.ForeignKey('pharmacie.Medicament', on_delete=models.SET_NULL, null=True, blank=True)
    medicament_libre = models.CharField(max_length=200, blank=True)
    posologie = models.CharField(max_length=500)
    duree = models.CharField(max_length=100, blank=True)
    quantite = models.IntegerField(default=1)
    notes = models.TextField(blank=True)


class ExamenDemande(models.Model):
    STATUT = [('demande','Demandé'),('en_cours','En cours'),('resultat','Résultat disponible'),('valide','Validé')]
    TYPE = [('laboratoire','Laboratoire'),('imagerie','Imagerie'),('autre','Autre')]

    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='examens_demandes')
    type_examen = models.CharField(max_length=20, choices=TYPE)
    libelle = models.CharField(max_length=300)
    urgence = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='demande')
    date_demande = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.libelle} - {self.consultation.patient}"
    class Meta: verbose_name = "Examen demandé"
