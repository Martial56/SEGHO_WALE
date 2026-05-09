from django.db import models
from django.contrib.auth.models import User


class TypeExamen(models.Model):
    code = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=200)
    categorie = models.CharField(max_length=100, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delai_resultat_heures = models.IntegerField(default=24)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Type d'examen"


class AnalyseLaboratoire(models.Model):
    STATUT = [('recu','Reçu'),('en_analyse','En analyse'),('resultat','Résultat'),('valide','Validé'),('envoye','Envoyé')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='analyses')
    examen_demande = models.OneToOneField('consultations.ExamenDemande', on_delete=models.SET_NULL, null=True, blank=True)
    type_examen = models.ForeignKey(TypeExamen, on_delete=models.SET_NULL, null=True)
    date_prelevement = models.DateTimeField(auto_now_add=True)
    date_resultat = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='recu')
    technicien = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='analyses_tech')
    validateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='analyses_val')
    commentaire = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = AnalyseLaboratoire.objects.filter(date_prelevement__year=annee).count() + 1
            self.numero = f"LAB{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Analyse {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Analyse laboratoire"
        ordering = ['-date_prelevement']


class ResultatAnalyse(models.Model):
    analyse = models.ForeignKey(AnalyseLaboratoire, on_delete=models.CASCADE, related_name='resultats')
    parametre = models.CharField(max_length=200)
    valeur = models.CharField(max_length=200)
    unite = models.CharField(max_length=50, blank=True)
    valeur_normale_min = models.CharField(max_length=100, blank=True)
    valeur_normale_max = models.CharField(max_length=100, blank=True)
    interpretation = models.CharField(max_length=20, choices=[('normal','Normal'),('eleve','Élevé'),('bas','Bas'),('critique','Critique')], blank=True)

    def __str__(self): return f"{self.parametre}: {self.valeur} {self.unite}"
    class Meta: verbose_name = "Résultat d'analyse"


class ExamenImagerie(models.Model):
    STATUT = [('recu','Reçu'),('en_cours','En cours'),('resultat','Résultat'),('valide','Validé')]
    TYPE = [('echographie','Échographie'),('radiographie','Radiographie'),('scanner','Scanner'),('irm','IRM'),('autre','Autre')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='imageries')
    examen_demande = models.OneToOneField('consultations.ExamenDemande', on_delete=models.SET_NULL, null=True, blank=True)
    type_imagerie = models.CharField(max_length=20, choices=TYPE)
    zone_examinee = models.CharField(max_length=200)
    date_examen = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='recu')
    compte_rendu = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    radiologue = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    image = models.FileField(upload_to='imagerie/', blank=True, null=True)
    urgent = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = ExamenImagerie.objects.filter(date_examen__year=annee).count() + 1
            self.numero = f"IMG{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Imagerie {self.numero} - {self.patient}"
    class Meta: verbose_name = "Examen imagerie"
