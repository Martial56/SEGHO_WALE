from django.db import models
from django.contrib.auth.models import User


class Specialite(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    description = models.TextField(blank=True, verbose_name="Description")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Spécialité"
        verbose_name_plural = "Spécialités"
        ordering = ['nom']


class Diplome(models.Model):
    titre = models.CharField(max_length=200, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")

    def __str__(self): return self.titre

    class Meta:
        verbose_name = "Diplôme"
        verbose_name_plural = "Diplômes"
        ordering = ['titre']


class Departement(models.Model):
    nom         = models.CharField(max_length=100, verbose_name="Nom")
    code        = models.CharField(max_length=20, unique=True, verbose_name="Code")
    description = models.TextField(blank=True, verbose_name="Description")
    actif       = models.BooleanField(default=True, verbose_name="Actif")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Département"
        verbose_name_plural = "Départements"
        ordering = ['nom']


class TypeArticle(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Type d'article"
        verbose_name_plural = "Types d'articles"
        ordering = ['nom']


class CategorieArticle(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Catégorie d'article"
        verbose_name_plural = "Catégories d'articles"
        ordering = ['nom']


class UniteMesure(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"
        ordering = ['nom']


class Service(models.Model):
    # Identification
    nom               = models.CharField(max_length=100, verbose_name="Nom")
    reference_interne = models.CharField(max_length=50, blank=True, verbose_name="Référence interne")
    code_barres       = models.CharField(max_length=50, blank=True, verbose_name="Code barres")

    # Classification
    type_article      = models.ForeignKey(TypeArticle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Type")
    categorie_article = models.ForeignKey(CategorieArticle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Catégorie d'article")
    valeur_variante   = models.CharField(max_length=100, blank=True, verbose_name="Valeur de la variante")

    # Tarification
    prix_vente        = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, verbose_name="Prix de vente (FCFA)")
    cout              = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, verbose_name="Coût (FCFA)")
    unite             = models.ForeignKey(UniteMesure, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Unité de mesure")

    # Stock
    quantite_stock    = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Quantités en stock")
    quantite_prevue   = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Quantités prévues")

    description       = models.TextField(blank=True, verbose_name="Description")
    actif             = models.BooleanField(default=True, verbose_name="Actif")

    def __str__(self): return self.nom

    class Meta:
        verbose_name = "Service médical"
        verbose_name_plural = "Services médicaux"
        ordering = ['categorie_article', 'nom']


class Medecin(models.Model):
    # Code auto-généré DR + ANNÉE + 4 chiffres
    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Code médecin")
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Compte utilisateur")
    photo = models.ImageField(upload_to='medecins/photos/', blank=True, null=True, verbose_name="Photo")

    # Identité
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenoms = models.CharField(max_length=200, verbose_name="Prénoms")
    fonction = models.CharField(max_length=100, blank=True, verbose_name="Fonction / Titre", help_text="Ex: Directeur Médical, Médecin généraliste")

    # Infos médicales
    specialite = models.ForeignKey(Specialite, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Spécialité")
    departements = models.ManyToManyField(Departement, blank=True, related_name='medecins', verbose_name="Départements")
    chirurgien_principal = models.BooleanField(default=False, verbose_name="Chirurgien principal")
    service_consultation = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medecins_consultation', verbose_name="Service de consultation"
    )
    service_suivi = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medecins_suivi', verbose_name="Service de suivi"
    )
    duree_consultation = models.PositiveSmallIntegerField(
        default=15, verbose_name="Durée de consultation (min)",
        help_text="Durée par défaut en minutes"
    )
    ordre_medecin = models.CharField(max_length=50, blank=True, verbose_name="N° Ordre des médecins")

    # Infos personnelles
    telephone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    mobile = models.CharField(max_length=20, blank=True, verbose_name="Mobile")
    email = models.EmailField(blank=True, verbose_name="Email")
    adresse = models.TextField(blank=True, verbose_name="Adresse")
    tva_numero_fiscal = models.CharField(max_length=50, blank=True, verbose_name="TVA / Numéro fiscal")

    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    def save(self, *args, **kwargs):
        if not self.code:
            from django.utils import timezone
            annee = timezone.now().year
            derniere = (
                Medecin.objects.filter(code__startswith=f'DR{annee}')
                .order_by('code')
                .last()
            )
            if derniere and derniere.code:
                try:
                    seq = int(derniere.code[-4:]) + 1
                except ValueError:
                    seq = 1
            else:
                seq = 1
            self.code = f'DR{annee}{seq:04d}'
        super().save(*args, **kwargs)

    def __str__(self): return f"Dr {self.nom} {self.prenoms}"

    class Meta:
        verbose_name = "Médecin"
        verbose_name_plural = "Médecins"
        ordering = ['nom']


class MedecinDiplome(models.Model):
    medecin = models.ForeignKey(Medecin, on_delete=models.CASCADE, related_name='diplomes', verbose_name="Médecin")
    diplome = models.ForeignKey(Diplome, on_delete=models.CASCADE, verbose_name="Diplôme")
    institution = models.CharField(max_length=200, blank=True, verbose_name="Institution")
    annee_obtention = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Année d'obtention")

    def __str__(self): return f"{self.medecin} — {self.diplome}"

    class Meta:
        verbose_name = "Diplôme du médecin"
        verbose_name_plural = "Diplômes du médecin"
