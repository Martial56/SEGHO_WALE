from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Soin(models.Model):
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('en_attente_de_paiement', 'En attente de paiement'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]
    SEVERITE = [
        ('', '—'),
        ('moderee', 'Modérée'),
        ('severe', 'Sévère'),
    ]
    STATUT_MALADIE = [
        ('', '—'),
        ('aigu', 'Aigu'),
        ('chronique', 'Chronique'),
        ('inchange', 'Inchangé'),
        ('gueri', 'Guéri'),
        ('ameliorant', 'Améliorant'),
        ('aggravant', 'Aggravant'),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False, blank=True, verbose_name="Numéro")
    nom = models.CharField(max_length=200, blank=True, verbose_name="Nom")
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='soins', verbose_name="Patient"
    )
    infirmier = models.ForeignKey(
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_pris_en_charge', verbose_name="Infirmier responsable"
    )
    motif = models.CharField(max_length=500, blank=True, verbose_name="Motif")
    observations = models.TextField(blank=True, verbose_name="Observations")
    statut = models.CharField(max_length=25, choices=STATUT, default='brouillon', verbose_name="Statut")
    date_heure = models.DateTimeField(default=timezone.now, verbose_name="Date et heure")
    date_creation = models.DateTimeField(auto_now_add=True)

    photo = models.ImageField(upload_to='soins/photos/', blank=True, null=True, verbose_name="Photo")
    departement = models.ForeignKey(
        'medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins', verbose_name="Département"
    )
    statut_maladie = models.CharField(max_length=20, choices=STATUT_MALADIE, blank=True, verbose_name="Statut de la maladie")
    severite = models.CharField(max_length=20, choices=SEVERITE, blank=True, verbose_name="Sévérité")
    date_guerison = models.DateField(null=True, blank=True, verbose_name="Date de guérison")
    maladie_infectieuse = models.BooleanField(default=False, verbose_name="Maladie infectieuse")
    maladie_allergique = models.BooleanField(default=False, verbose_name="Maladie allergique")
    lactation = models.BooleanField(default=False, verbose_name="Lactation")
    avertissement_grossesse = models.BooleanField(default=False, verbose_name="Avertissement de grossesse")
    facture = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins', verbose_name="Facture"
    )
    hospitalisation = models.ForeignKey(
        'hospitalisation.Hospitalisation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_lies', verbose_name="Hospitalisation liée"
    )
    cree_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_crees', verbose_name="Créé par"
    )
    modifie_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_modifies', verbose_name="Modifié par"
    )
    date_modification = models.DateTimeField(null=True, blank=True, verbose_name="Date de modification")
    termine_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_termines', verbose_name="Terminé par"
    )
    date_termine = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            prefix = f"SN{str(annee)[2:]}"
            last = Soin.objects.filter(numero__startswith=prefix).order_by('-pk').first()
            if last:
                try:
                    count = int(last.numero[len(prefix):]) + 1
                except (ValueError, IndexError):
                    count = Soin.objects.filter(numero__startswith=prefix).count() + 1
            else:
                count = 1
            self.numero = f"{prefix}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero or 'Soin'} — {self.patient}"

    class Meta:
        verbose_name = "Soin"
        verbose_name_plural = "Soins"
        ordering = ['-date_creation']
        permissions = [
            ('can_creer_facture', 'Peut créer une facture de soin'),
            ('can_administrer_soin', 'Peut administrer un soin'),
        ]



class ProcedureSoin(models.Model):
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Numéro")
    soin = models.ForeignKey(
        'Soin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures', verbose_name="Soin infirmier"
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='procedures_soins', verbose_name="Patient"
    )
    infirmier = models.ForeignKey(
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_effectuees', verbose_name="Infirmier"
    )
    soin_type = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures', verbose_name="Soin"
    )
    prix = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Prix")
    departement = models.ForeignKey(
        'medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_soins', verbose_name="Département"
    )
    date = models.DateTimeField(default=timezone.now, verbose_name="Date")
    maladie = models.ForeignKey(
        'patients.Pathologie', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Maladie"
    )
    rendez_vous = models.ForeignKey(
        'patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_soins', verbose_name="Rendez-vous"
    )
    facture = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_soins', verbose_name="Facture"
    )
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon', verbose_name="État")
    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_creees', verbose_name="Créé par"
    )
    modifie_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures_modifiees', verbose_name="Modifié par"
    )
    date_modification = models.DateTimeField(null=True, blank=True, verbose_name="Date de modification")

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            prefix = f"DP{str(annee)[2:]}"
            last = ProcedureSoin.objects.filter(numero__startswith=prefix).order_by('-pk').first()
            if last:
                try:
                    count = int(last.numero[len(prefix):]) + 1
                except (ValueError, IndexError):
                    count = ProcedureSoin.objects.filter(numero__startswith=prefix).count() + 1
            else:
                count = 1
            self.numero = f"{prefix}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.patient}"

    class Meta:
        verbose_name = "Procédure de soin"
        verbose_name_plural = "Liste des soins"
        ordering = ['-date']


