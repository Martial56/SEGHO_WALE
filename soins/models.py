from django.db import models
from django.utils import timezone


class Soin(models.Model):
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('en_attente_de_paiement', 'Paiement en attente'),
        ('en_cours', 'Soins en cours'),
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
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
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
        'employer.Departement', on_delete=models.SET_NULL, null=True, blank=True,
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
            count = Soin.objects.count() + 1
            self.numero = f"SOIN{count:04d}"
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
        ('en_cours', 'Soins en cours'),
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
        'employer.Departement', on_delete=models.SET_NULL, null=True, blank=True,
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
            count = ProcedureSoin.objects.count() + 1
            self.numero = f"DP{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.patient}"

    class Meta:
        verbose_name = "Procédure de soin"
        verbose_name_plural = "Liste des soins"
        ordering = ['-date']


class DemandeExamen(models.Model):
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('demande',   'Demandé'),
        ('accepte',   'Accepté'),
        ('en_cours',  'En cours'),
        ('termine',   'Terminé'),
    ]
    TYPE_TEST = [
        ('pathologie',     'Pathologie'),
        ('biologie',       'Biologie'),
        ('microbiologie',  'Microbiologie'),
        ('hematologie',    'Hématologie'),
        ('biochimie',      'Biochimie'),
        ('immunologie',    'Immunologie'),
        ('autre',          'Autre'),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    soin = models.ForeignKey(
        'Soin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_examen', verbose_name="Soin"
    )
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='demandes_examen', verbose_name="Patient"
    )
    date = models.DateTimeField(default=timezone.now, verbose_name="Date")
    medecin_prescripteur = models.ForeignKey(
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_examen_prescrites', verbose_name="Docteur prescripteur"
    )
    lab_groupe = models.CharField(max_length=200, blank=True, verbose_name="Lab Groupe")
    est_demande_groupe = models.BooleanField(default=False, verbose_name="Est une demande de groupe")
    type_test = models.CharField(max_length=50, choices=TYPE_TEST, blank=True, verbose_name="Type du test")
    centre_collecte = models.CharField(max_length=200, blank=True, verbose_name="Centre de collecte")
    envoyer_autre_lab = models.BooleanField(default=False, verbose_name="Envoyer à un autre lab")
    sampler = models.CharField(max_length=200, blank=True, verbose_name="Sampler")
    date_actes = models.DateTimeField(null=True, blank=True, verbose_name="Date et heure des actes (prélèvement)")
    echantillon_du_test = models.BooleanField(default=False, verbose_name="Échantillon du test")
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon', verbose_name="Statut")
    raison_refus = models.TextField(blank=True, verbose_name="Raison du refus")
    rendez_vous = models.ForeignKey(
        'patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_examen', verbose_name="Rendez-vous"
    )

    # Champs HL7 / segment
    type_segment          = models.CharField(max_length=10,  default='H',            blank=True, verbose_name="Type de segment")
    nom_fichier           = models.CharField(max_length=100, default='WAL001.HPR',    blank=True, verbose_name="Nom du fichier")
    code_emetteur         = models.CharField(max_length=50,  default='001',           blank=True, verbose_name="Code émetteur")
    nom_emetteur          = models.CharField(max_length=200, blank=True,                          verbose_name="Nom émetteur")
    code_recepteur        = models.CharField(max_length=50,  default='002',           blank=True, verbose_name="Code récepteur")
    nom_recepteur         = models.CharField(max_length=200, default='CMSWALE.0000',  blank=True, verbose_name="Nom récepteur")
    identifiant_recepteur = models.CharField(max_length=200, default='WALE.SYSLAM',  blank=True, verbose_name="Identifiant récepteur")
    type_message          = models.CharField(max_length=10,  default='DRA',           blank=True, verbose_name="Type de message")
    mode_traitement       = models.CharField(max_length=10,  default='P',             blank=True, verbose_name="Mode de traitement")
    version_type          = models.CharField(max_length=10,  default='H2.4',          blank=True, verbose_name="Version et type")
    type_liaison          = models.CharField(max_length=10,  default='L',             blank=True, verbose_name="Type de liaison")
    liste_prix            = models.CharField(max_length=100, blank=True,                          verbose_name="Liste de prix")
    type_segment_patient  = models.CharField(max_length=10,  default='P',             blank=True, verbose_name="Type de segment patient")
    rang_segment_patient  = models.CharField(max_length=10,  default='D',             blank=True, verbose_name="Rang du segment patient")
    type_code             = models.CharField(max_length=10,  default='L',             blank=True, verbose_name="Type de code")
    priorite              = models.CharField(max_length=10,  default='C',             blank=True, verbose_name="Priorité")
    code_action           = models.CharField(max_length=10,  default='N',             blank=True, verbose_name="Code action")
    date_heure_resultats  = models.DateTimeField(null=True, blank=True,                           verbose_name="Date et heure des résultats")
    statuts_resultats     = models.CharField(max_length=10,  default='F',             blank=True, verbose_name="Statuts des résultats")
    couts_transport       = models.CharField(max_length=100, default='WALK',          blank=True, verbose_name="Coûts transport")
    type_segment_qbr      = models.CharField(max_length=10,  default='QBR',           blank=True, verbose_name="Type de segment QBR")
    type_segment_l        = models.CharField(max_length=10,  default='L',             blank=True, verbose_name="Type de segment L")

    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            count = DemandeExamen.objects.count() + 1
            self.numero = f"CASE{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.patient}"

    class Meta:
        verbose_name = "Demande d'examen"
        verbose_name_plural = "Demandes d'examen"
        ordering = ['-date_creation']


class LigneDemandeExamen(models.Model):
    demande = models.ForeignKey(
        DemandeExamen, on_delete=models.CASCADE,
        related_name='lignes', verbose_name="Demande"
    )
    type_examen = models.ForeignKey(
        'laboratoire.TypeExamen', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Test"
    )
    delai_execution = models.CharField(max_length=100, blank=True, verbose_name="Délai d'exécution")
    prix_vente = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Prix de vente")
    instructions_speciales = models.TextField(blank=True, verbose_name="Instructions spéciales")

    def __str__(self):
        return f"{self.demande.numero} — {self.type_examen}"

    class Meta:
        verbose_name = "Ligne de demande d'examen"
        verbose_name_plural = "Lignes de demande d'examen"

