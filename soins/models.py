from django.db import models
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

    numero = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Numéro")
    nom = models.CharField(max_length=200, blank=True, verbose_name="Nom")
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='soins', verbose_name="Patient"
    )
    infirmier = models.ForeignKey(
<<<<<<< HEAD
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
=======
        'ressources_humaines.Employe', on_delete=models.SET_NULL, null=True, blank=True,
>>>>>>> origin/Martial_branch
        related_name='soins_effectues', verbose_name="Infirmier/Agent de soins"
    )
    rendez_vous = models.ForeignKey(
        'patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins', verbose_name="Rendez-vous"
    )
    date_heure = models.DateTimeField(default=timezone.now, verbose_name="Date et heure")
    motif = models.CharField(max_length=500, blank=True, verbose_name="Motif")
    observations = models.TextField(blank=True, verbose_name="Observations")
    statut = models.CharField(max_length=25, choices=STATUT, default='brouillon', verbose_name="Statut")
    date_creation = models.DateTimeField(auto_now_add=True)

    # Champs supplémentaires
    photo = models.ImageField(upload_to='soins/photos/', blank=True, null=True, verbose_name="Photo")
    departement = models.ForeignKey(
<<<<<<< HEAD
        'medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True,
=======
        'medecins.Service', on_delete=models.SET_NULL, null=True, blank=True,
>>>>>>> origin/Martial_branch
        related_name='soins', verbose_name="Département"
    )
    service_inscription = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='soins_inscrits', verbose_name="Service d'inscription"
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

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            count = Soin.objects.filter(date_heure__year=annee).count() + 1
            self.numero = f"SOIN{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Soin {self.numero} — {self.patient}"

    class Meta:
        verbose_name = "Soin"
        verbose_name_plural = "Soins"
        ordering = ['-date_heure']
        permissions = [
            ('can_creer_facture', 'Peut créer une facture de soin'),
            ('can_administrer_soin', 'Peut administrer un soin'),
        ]


class Maladie(models.Model):
    nom = models.CharField(max_length=200, unique=True, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    code_cim = models.CharField(max_length=20, blank=True, verbose_name="Code CIM-10")

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Maladie"
        verbose_name_plural = "Maladies"
        ordering = ['nom']


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
<<<<<<< HEAD
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
=======
        'ressources_humaines.Employe', on_delete=models.SET_NULL, null=True, blank=True,
>>>>>>> origin/Martial_branch
        related_name='procedures_effectuees', verbose_name="Infirmier"
    )
    soin_type = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='procedures', verbose_name="Soin"
    )
    prix = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Prix")
    departement = models.ForeignKey(
<<<<<<< HEAD
        'medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True,
=======
        'medecins.Service', on_delete=models.SET_NULL, null=True, blank=True,
>>>>>>> origin/Martial_branch
        related_name='procedures_soins', verbose_name="Département"
    )
    date = models.DateTimeField(default=timezone.now, verbose_name="Date")
    maladie = models.ForeignKey(
        'Maladie', on_delete=models.SET_NULL, null=True, blank=True,
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

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            count = ProcedureSoin.objects.filter(date__year=annee).count() + 1
            self.numero = f"DP{str(annee)[2:]}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.patient}"

    class Meta:
        verbose_name = "Procédure de soin"
        verbose_name_plural = "Liste des soins"
        ordering = ['-date']


