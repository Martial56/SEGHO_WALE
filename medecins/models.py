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


class Diplome(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self): return self.titre
    class Meta:
        verbose_name = "Diplôme"
        verbose_name_plural = "Diplômes"
        ordering = ['titre']


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


class Service(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, null=True, unique=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Service"
        ordering = ['nom']


class Medecin(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    matricule = models.CharField(max_length=20, unique=True, blank=True, null=True)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    photo = models.ImageField(upload_to='medecins/photos/', blank=True, null=True)
    diplome = models.ForeignKey(Diplome, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name='Éducation')
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True)
    departements = models.ManyToManyField(Departement, blank=True, related_name='medecins',
                                          verbose_name='Départements')
    service_consultation = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medecins_consultation', verbose_name='Service de consultation')
    service_suivi = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medecins_suivi', verbose_name='Service de suivi')
    fonction = models.CharField(max_length=100, blank=True, verbose_name='Fonction / Titre')
    telephone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    tva_numero_fiscal = models.CharField(max_length=50, blank=True, verbose_name='TVA / N° fiscal')
    ordre_medecin = models.CharField(max_length=50, blank=True)
    duree_consultation = models.PositiveSmallIntegerField(default=15,
                                                          verbose_name='Durée consultation (min)')
    chirurgien_principal = models.BooleanField(default=False)
    taux_honoraire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    employe_societe = models.BooleanField(default=True, verbose_name='Employé de la société')
    signature = models.ImageField(upload_to='medecins/signatures/', blank=True, null=True,
                                  verbose_name='Signature')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            annee = timezone.now().year
            count = Medecin.objects.filter(date_creation__year=annee).count() + 1
            self.code = f"DR{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Dr {self.nom} {self.prenoms}"
    class Meta:
        verbose_name = "Médecin"
        ordering = ['nom']


class Etiquette(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    couleur = models.CharField(max_length=7, blank=True, default='#0ea5e9')

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Étiquette"
        verbose_name_plural = "Étiquettes"
        ordering = ['nom']


class DocteurReferent(models.Model):
    TYPE_CHOICES = [('individu', 'Individu'), ('societe', 'Société')]
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
    photo = models.ImageField(upload_to='medecins/referents/', blank=True, null=True)
    poste_occupe = models.CharField(max_length=100, blank=True, verbose_name='Poste Occupé')
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name='Spécialité')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    telephone = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    site_web = models.URLField(blank=True, verbose_name='Site Web')
    langue = models.CharField(max_length=50, blank=True, default='Français',
                              verbose_name='Langue')
    etiquettes = models.ManyToManyField(Etiquette, blank=True, verbose_name='Étiquettes')
    adresse = models.TextField(blank=True)
    tva = models.CharField(max_length=50, blank=True, verbose_name='TVA')
    # Info de l'hôpital
    medecin_interne = models.ForeignKey(
        'Medecin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='referents_associes', verbose_name='Docteur référent (interne)')
    est_referent = models.BooleanField(default=True, verbose_name='Est le médecin référent')
    # Ventes & Achats
    reference_externe = models.CharField(max_length=100, blank=True, verbose_name='Référence')
    # Comptabilité
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


class ContactAdresse(models.Model):
    TYPE_CHOICES = [
        ('contact', 'Contact'),
        ('facturation', 'Adresse de facturation'),
        ('livraison', 'Adresse de livraison'),
        ('autre', 'Autre adresse'),
    ]
    referent = models.ForeignKey(DocteurReferent, on_delete=models.CASCADE,
                                 related_name='contacts_adresses')
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
