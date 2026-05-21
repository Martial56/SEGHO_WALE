from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Specialite(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta:

        verbose_name = "Spécialité"
        ordering = ['nom']
        db_table = 'utilisateur_specialite'


class Diplome(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self): return self.titre
    class Meta:

        verbose_name = "Diplôme"
        verbose_name_plural = "Diplômes"
        ordering = ['titre']
        db_table = 'utilisateur_diplome'


class Departement(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:

        verbose_name = "Département"
        verbose_name_plural = "Départements"
        ordering = ['nom']
        db_table = 'utilisateur_departement'


class Employe(models.Model):
    GENRE_CHOICES = [('', '—'), ('M', 'Masculin'), ('F', 'Féminin')]
    TITRE_CHOICES = [
        ('', '—'), ('dr', 'Dr'), ('pr', 'Pr'),
        ('m', 'M.'), ('mme', 'Mme'), ('prof', 'Prof.'),
    ]

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='utilisateur_profile')
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    matricule = models.CharField(max_length=20, unique=True, blank=True, null=True)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True, default='', verbose_name='Genre')
    titre = models.CharField(max_length=10, blank=True, choices=TITRE_CHOICES, verbose_name='Titre')
    date_naissance = models.DateField(null=True, blank=True, verbose_name='Date de naissance')
    lieu_naissance = models.CharField(max_length=200, blank=True, verbose_name='Lieu de naissance')
    photo = models.ImageField(upload_to='medecins/photos/', blank=True, null=True)
    est_medecin = models.BooleanField(default=False, verbose_name='Est Médecin/Docteur')
    est_referent = models.BooleanField(default=False, verbose_name='Est Médecin Référent')
    diplome = models.ForeignKey(Diplome, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name='Éducation', related_name='+')
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    departements = models.ManyToManyField(Departement, blank=True, related_name='employes',
                                          verbose_name='Départements',
                                          through='EmployeDepartement')
    service_consultation = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='service de consultation')
    service_suivi = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='service de suivi')
    fonction = models.CharField(max_length=100, blank=True, verbose_name='Fonction / Poste')
    telephone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True, verbose_name='Email professionnel')
    adresse = models.TextField(blank=True, verbose_name="Lieu d'habitation")
    tva_numero_fiscal = models.CharField(max_length=50, blank=True, verbose_name='TVA / N° fiscal')
    ordre_medecin = models.CharField(max_length=50, blank=True)
    duree_consultation = models.PositiveSmallIntegerField(default=15,
                                                          verbose_name='Durée consultation (min)')
    chirurgien_principal = models.BooleanField(default=False)
    taux_honoraire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    employe_societe = models.BooleanField(default=True, verbose_name='Employé de la société')
    stagiaire_societe = models.BooleanField(default=False, verbose_name='Stagiaire de la société')
    signature = models.ImageField(upload_to='medecins/signatures/', blank=True, null=True,
                                  verbose_name='Signature')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    nationalite = models.CharField(max_length=100, blank=True, verbose_name='Nationalité')
    langue = models.CharField(max_length=50, blank=True, default='Français', verbose_name='Langue')
    notes_internes = models.TextField(blank=True, verbose_name='Notes internes')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            annee = timezone.now().year
            prefix = 'DR' if self.est_medecin else 'EMP'
            count = Employe.objects.filter(date_creation__year=annee).count() + 1
            self.code = f"{prefix}{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.est_medecin:
            return f"Dr {self.nom} {self.prenoms}"
        return f"{self.nom} {self.prenoms}"

    class Meta:

        verbose_name = "Employé"
        verbose_name_plural = "Employés"
        ordering = ['nom']
        db_table = 'utilisateur_employe'


class DiplomePersonnel(models.Model):
    employe = models.ForeignKey('Employe', on_delete=models.CASCADE,
                                related_name='utilisateur_diplomes_personnels',
                                verbose_name='Employé')
    titre = models.CharField(max_length=200, verbose_name='Titre du diplôme')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    annee = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Année')

    def __str__(self): return self.titre

    class Meta:

        verbose_name = "Diplôme personnel"
        verbose_name_plural = "Diplômes personnels"
        ordering = ['-annee', 'titre']
        db_table = 'utilisateur_diplomepersonnel'


class Etiquette(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    couleur = models.CharField(max_length=7, blank=True, default='#0ea5e9')

    def __str__(self): return self.nom
    class Meta:

        verbose_name = "Étiquette"
        verbose_name_plural = "Étiquettes"
        ordering = ['nom']
        db_table = 'utilisateur_etiquette'


class DocteurReferent(models.Model):
    TYPE_CHOICES = [('individu', 'Individu'), ('societe', 'Société')]
    GENRE_CHOICES = [('', '—'), ('M', 'Masculin'), ('F', 'Féminin')]
    TITRE_CHOICES = [
        ('', '—'),
        ('dr', 'Dr'),
        ('pr', 'Pr'),
        ('m', 'M.'),
        ('mme', 'Mme'),
        ('prof', 'Prof.'),
    ]

    code = models.CharField(max_length=20, unique=True, blank=True)
    type_contact = models.CharField(max_length=10, choices=TYPE_CHOICES, default='individu',
                                    verbose_name='Type')
    titre = models.CharField(max_length=10, blank=True, choices=TITRE_CHOICES,
                             verbose_name='Titre')
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200, blank=True, verbose_name='Prénom(s)')
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True, default='', verbose_name='Genre')
    photo = models.ImageField(upload_to='medecins/referents/', blank=True, null=True)
    poste_occupe = models.CharField(max_length=100, blank=True, verbose_name='Poste Occupé')
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name='Spécialité', related_name='+')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    telephone = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    site_web = models.URLField(blank=True, verbose_name='Site Web')
    langue = models.CharField(max_length=50, blank=True, default='Français',
                              verbose_name='Langue')
    etiquettes = models.ManyToManyField(Etiquette, blank=True, verbose_name='Étiquettes',
                                       through='DocteurReferentEtiquette', related_name='+')
    adresse = models.TextField(blank=True)
    tva = models.CharField(max_length=50, blank=True, verbose_name='TVA')
    medecin_interne = models.ForeignKey(
        'Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Docteur référent (interne)')
    est_referent = models.BooleanField(default=True, verbose_name='Est le médecin référent')
    reference_externe = models.CharField(max_length=100, blank=True, verbose_name='Référence')
    compte_client = models.CharField(max_length=100, blank=True, verbose_name='Compte client')
    compte_fournisseur = models.CharField(max_length=100, blank=True,
                                          verbose_name='Compte fournisseur')
    notes = models.TextField(blank=True, verbose_name='Notes internes')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            annee = timezone.now().year
            count = DocteurReferent.objects.filter(date_creation__year=annee).count() + 1
            self.code = f"REF{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.prenoms:
            return f"Dr {self.nom} {self.prenoms}".strip()
        return f"Dr {self.nom}"

    class Meta:

        verbose_name = "Docteur Référent"
        verbose_name_plural = "Docteurs Référents"
        ordering = ['nom']
        db_table = 'utilisateur_docteurreferent'


class ContactAdresse(models.Model):
    TYPE_CHOICES = [
        ('contact', 'Contact'),
        ('facturation', 'Adresse de facturation'),
        ('livraison', 'Adresse de livraison'),
        ('autre', 'Autre adresse'),
    ]
    referent = models.ForeignKey(DocteurReferent, on_delete=models.CASCADE,
                                 related_name='utilisateur_contacts_adresses')
    type_adresse = models.CharField(max_length=20, choices=TYPE_CHOICES, default='contact',
                                    verbose_name='Type')
    nom = models.CharField(max_length=100, blank=True, verbose_name='Nom')
    telephone = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Courriel')
    adresse = models.TextField(blank=True, verbose_name='Adresse')

    def __str__(self):
        return f"{self.get_type_adresse_display()} — {self.nom or self.referent.nom}"

    class Meta:

        verbose_name = "Contact / Adresse"
        verbose_name_plural = "Contacts / Adresses"
        db_table = 'utilisateur_contactadresse'


class EmployeDepartement(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, db_column='medecin_id')
    departement = models.ForeignKey(Departement, on_delete=models.CASCADE)

    class Meta:
        db_table = 'utilisateur_employe_departements'

        unique_together = [('employe', 'departement')]


class DocteurReferentEtiquette(models.Model):
    docteurreferent = models.ForeignKey(DocteurReferent, on_delete=models.CASCADE)
    etiquette = models.ForeignKey(Etiquette, on_delete=models.CASCADE)

    class Meta:
        db_table = 'utilisateur_docteurreferent_etiquettes'

        unique_together = [('docteurreferent', 'etiquette')]
