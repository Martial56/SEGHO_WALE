from django.db import models
from django.utils import timezone


class Assurance(models.Model):
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    telephone = models.CharField(max_length=20, blank=True)
    taux_prise_en_charge = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Assurance"


class Patient(models.Model):
    SEXE = [('M', 'Masculin'), ('F', 'Féminin')]
    GROUPE_SANGUIN = [('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')]

    code_patient = models.CharField(max_length=20, unique=True, editable=False)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    date_naissance = models.DateField()
    lieu_naissance = models.CharField(max_length=100, blank=True)
    sexe = models.CharField(max_length=1, choices=SEXE)
    nationalite = models.CharField(max_length=50, default='Ivoirienne')
    profession = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20)
    telephone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    ville = models.CharField(max_length=100, default='Yamoussoukro')
    groupe_sanguin = models.CharField(max_length=3, choices=GROUPE_SANGUIN, blank=True)
    allergies = models.TextField(blank=True)
    antecedents = models.TextField(blank=True)
    assurance = models.ForeignKey(Assurance, null=True, blank=True, on_delete=models.SET_NULL)
    numero_assurance = models.CharField(max_length=100, blank=True)
    date_expiration_assurance = models.DateField(null=True, blank=True)
    contact_urgence_nom = models.CharField(max_length=200, blank=True)
    contact_urgence_telephone = models.CharField(max_length=20, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    actif = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='patients/', blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.code_patient:
            annee = timezone.now().year
            count = Patient.objects.filter(date_creation__year=annee).count() + 1
            self.code_patient = f"PAT{annee}{count:05d}"
        super().save(*args, **kwargs)

    @property
    def age(self):
        from datetime import date
        t = date.today()
        return t.year - self.date_naissance.year - ((t.month, t.day) < (self.date_naissance.month, self.date_naissance.day))

    def __str__(self): return f"{self.nom} {self.prenoms} ({self.code_patient})"
    class Meta:
        verbose_name = "Patient"
        ordering = ['-date_creation']


class RendezVous(models.Model):
    STATUT = [('planifie','Planifié'),('confirme','Confirmé'),('en_attente','En attente'),('en_consultation','En consultation'),('termine','Terminé'),('annule','Annulé'),('absent','Absent')]
    TYPE = [('consultation','Consultation'),('controle','Contrôle'),('urgence','Urgence'),('examen','Examen'),('vaccination','Vaccination')]
    DEPARTEMENT = [
        ('medecine_generale', 'Médecine générale'),
        ('gynecologie_cpn', 'Gynécologie / CPN'),
    ]
    URGENCE = [('normal', 'Normal'), ('urgent', 'Urgent'), ('tres_urgent', 'Très urgent')]

    code_rdv = models.CharField(max_length=20, blank=True, default='', verbose_name='Code RDV')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='rendez_vous')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous')
    docteur_jr = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='rdv_docteur_jr', verbose_name='Docteur Jr. responsable')
    departement = models.CharField(max_length=30, choices=DEPARTEMENT, blank=True, default='')
    salle_consultation = models.CharField(max_length=100, blank=True, verbose_name='Salle de consultation')
    date_heure = models.DateTimeField()
    date_suivi = models.DateTimeField(null=True, blank=True, verbose_name='Date de suivi')
    duree_minutes = models.IntegerField(default=30)
    type_rdv = models.CharField(max_length=20, choices=TYPE, default='consultation')
    niveau_urgence = models.CharField(max_length=20, choices=URGENCE, default='normal', verbose_name="Niveau d'urgence")
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='planifie')
    notes = models.TextField(blank=True)
    maladies = models.TextField(blank=True, verbose_name='Maladies')
    principales_plaintes = models.TextField(blank=True, verbose_name='Principales plaintes')
    antecedents_maladie = models.TextField(blank=True, verbose_name='Antécédents de la maladie actuelle')
    historique_passee = models.TextField(blank=True, verbose_name='Historique passée')
    rdv_exterieur = models.BooleanField(default=False, verbose_name='Rendez-vous extérieur')
    code_confirmation = models.CharField(max_length=30, blank=True, default='')
    temps_constante_minutes = models.IntegerField(default=0)
    temps_attente_minutes = models.IntegerField(default=0)
    temps_consultation_minutes = models.IntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code_rdv:
            count = RendezVous.objects.count() + 1
            candidate = f"AP{count:05d}"
            while RendezVous.objects.filter(code_rdv=candidate).exists():
                count += 1
                candidate = f"AP{count:05d}"
            self.code_rdv = candidate
        super().save(*args, **kwargs)

    @property
    def date_validite(self):
        from datetime import timedelta
        return (self.date_creation + timedelta(days=14)).date()

    @property
    def duree_display(self):
        h, m = divmod(self.duree_minutes, 60)
        return f"{h:02d}:{m:02d}"

    @property
    def temps_attente_display(self):
        h, m = divmod(self.temps_attente_minutes, 60)
        return f"{h:02d}:{m:02d}"

    @property
    def temps_consultation_display(self):
        h, m = divmod(self.temps_consultation_minutes, 60)
        return f"{h:02d}:{m:02d}"

    def __str__(self): return f"RDV {self.patient} - {self.date_heure.strftime('%d/%m/%Y %H:%M')}"
    class Meta:
        verbose_name = "Rendez-vous"
        ordering = ['date_heure']


class Naissance(models.Model):
    SEXE = [('M', 'Masculin'), ('F', 'Féminin')]
    MODE = [
        ('voie_basse', 'Voie basse'),
        ('cesarienne', 'Césarienne'),
        ('forceps', 'Forceps'),
        ('ventouse', 'Ventouse'),
    ]
    STATUT = [('vivant', 'Vivant'), ('mort_ne', 'Mort-né')]
    STATUT_DOSSIER = [('brouillon', 'Brouillon'), ('termine', 'Terminé')]
    GROUPE_SANGUIN = [('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')]
    EDUCATION = [('','—'),('aucun','Aucun'),('primaire','Primaire'),('secondaire','Secondaire'),('superieur','Supérieur')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    mere = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='naissances', verbose_name='Mère')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Médecin')
    date_accouchement = models.DateTimeField(verbose_name="Date d'accouchement")
    lieu_naissance = models.CharField(max_length=100, blank=True, verbose_name="Lieu de naissance")
    mode_accouchement = models.CharField(max_length=20, choices=MODE, default='voie_basse', verbose_name="Mode d'accouchement")
    nom_enfant = models.CharField(max_length=100, blank=True, verbose_name="Nom de l'enfant")
    prenoms_enfant = models.CharField(max_length=200, blank=True, verbose_name="Prénoms de l'enfant")
    sexe_enfant = models.CharField(max_length=1, choices=SEXE, verbose_name="Sexe de l'enfant")
    poids_naissance = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Poids (g)")
    groupe_sanguin_enfant = models.CharField(max_length=3, choices=GROUPE_SANGUIN, blank=True, verbose_name="Groupe sanguin")
    taux_hemoglobine = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Taux d'hémoglobine")
    taille_naissance = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Taille (cm)")
    apgar_1min = models.IntegerField(null=True, blank=True, verbose_name="Apgar 1 min")
    apgar_5min = models.IntegerField(null=True, blank=True, verbose_name="Apgar 5 min")
    statut = models.CharField(max_length=10, choices=STATUT, default='vivant')
    info_parents = models.TextField(blank=True, verbose_name="Information sur les parents")
    education_mere = models.CharField(max_length=20, choices=EDUCATION, blank=True, verbose_name="Éducation")
    age_mere = models.IntegerField(null=True, blank=True, verbose_name="Âge de la mère")
    parite = models.IntegerField(default=0, verbose_name="Parité")
    nombre_garcons = models.IntegerField(default=0, verbose_name="Garçon(s)")
    nombre_filles = models.IntegerField(default=0, verbose_name="Fille(s)")
    remarques = models.TextField(blank=True, verbose_name="Remarques")
    statut_dossier = models.CharField(max_length=20, choices=STATUT_DOSSIER, default='brouillon', verbose_name="Statut du dossier")
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            count = Naissance.objects.filter(date_creation__year=annee).count() + 1
            self.numero = f"NAISS{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.numero} - {self.mere}"
    class Meta:
        verbose_name = "Naissance"
        ordering = ['-date_accouchement']
