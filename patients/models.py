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
    medecin_referent = models.ForeignKey(
        'employe.DocteurReferent', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='patients',
        verbose_name='Médecin référent'
    )
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

    @property
    def age_en_mois(self):
        from datetime import date
        today = date.today()
        mois = (today.year - self.date_naissance.year) * 12 + (today.month - self.date_naissance.month)
        if today.day < self.date_naissance.day:
            mois -= 1
        return max(0, mois)

    @property
    def age_display(self):
        import calendar as cal
        from datetime import date
        today = date.today()
        mois_total = self.age_en_mois
        if mois_total >= 60:
            return f"{self.age}Ans"
        ans = mois_total // 12
        mois = mois_total % 12
        if today.day >= self.date_naissance.day:
            jours = today.day - self.date_naissance.day
        else:
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1
            jours = cal.monthrange(prev_year, prev_month)[1] - self.date_naissance.day + today.day
        return f"{ans}Ans{mois}Mois{jours}Jours"

    @property
    def tranche_age(self):
        mois = self.age_en_mois
        if mois < 12:
            return 'mois_0_11'
        a = self.age
        if a <= 4:  return 'ans_1_4'
        if a <= 9:  return 'ans_5_9'
        if a <= 14: return 'ans_10_14'
        if a <= 19: return 'ans_15_19'
        if a <= 24: return 'ans_20_24'
        if a <= 49: return 'ans_25_49'
        return 'ans_50_plus'

    def __str__(self): return f"{self.nom} {self.prenoms} ({self.code_patient})"
    class Meta:
        verbose_name = "Patient"
        ordering = ['-date_creation']


class RendezVous(models.Model):
    STATUT = [('planifie','Planifié'),('confirme','Confirmé'),('termine','Terminé'),('annule','Annulé'),('absent','Absent')]
    TYPE = [('consultation','Consultation'),('controle','Contrôle'),('urgence','Urgence'),('examen','Examen'),('vaccination','Vaccination')]
    DEPARTEMENT = [
        ('medecine_generale', 'Médecine générale'),
        ('gynecologie_cpn', 'Gynécologie / CPN'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='rendez_vous')
    medecin = models.ForeignKey('employe.Employe', on_delete=models.SET_NULL, null=True, related_name='rendez_vous')
    departement = models.CharField(max_length=30, choices=DEPARTEMENT, blank=True, default='')
    date_heure = models.DateTimeField()
    duree_minutes = models.IntegerField(default=30)
    type_rdv = models.CharField(max_length=20, choices=TYPE, default='consultation')
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='planifie')
    notes = models.TextField(blank=True)
    code_confirmation = models.CharField(max_length=30, blank=True, default='')
    temps_constante_minutes = models.IntegerField(default=0)
    temps_attente_minutes = models.IntegerField(default=0)
    temps_consultation_minutes = models.IntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    @property
    def date_validite(self):
        from datetime import timedelta
        return (self.date_creation + timedelta(days=14)).date()

    def __str__(self): return f"RDV {self.patient} - {self.date_heure.strftime('%d/%m/%Y %H:%M')}"
    class Meta:
        verbose_name = "Rendez-vous"
        ordering = ['date_heure']
