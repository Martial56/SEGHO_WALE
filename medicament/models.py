from django.db import models
from django.contrib.auth.models import User


# ─── CONFIGURATION ────────────────────────────────────────────────────────────

class CategorieMedicament(models.Model):
    nom  = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Catégorie médicament"
        ordering = ['nom']


class CompagniePharma(models.Model):
    nom        = models.CharField(max_length=200)
    code       = models.CharField(max_length=50, unique=True)
    partenaire = models.CharField(max_length=200, blank=True)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Compagnie pharmaceutique"
        ordering = ['nom']


class EffetTherapeutique(models.Model):
    nom  = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Effet thérapeutique"
        ordering = ['nom']


class DosageMedicament(models.Model):
    nom               = models.CharField(max_length=200)
    code              = models.CharField(max_length=50, blank=True)
    frequence         = models.CharField(max_length=100, blank=True)
    qte_totale_par_jour = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    jours             = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Dosage médicament"
        ordering = ['nom']


class RouteMedicament(models.Model):
    nom  = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Route des médicaments"
        ordering = ['nom']


class FormulaireType(models.Model):
    nom  = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Formulaire du médicament"
        ordering = ['nom']


# ─── MÉDICAMENT (catalogue) ───────────────────────────────────────────────────

class Medicament(models.Model):
    FORME = [
        ('comprime',   'Comprimé'),
        ('sirop',      'Sirop'),
        ('injectable', 'Injectable'),
        ('pommade',    'Pommade'),
        ('gelule',     'Gélule'),
        ('solution',   'Solution'),
        ('autre',      'Autre'),
    ]

    # Identification
    code             = models.CharField(max_length=50, unique=True)
    designation      = models.CharField(max_length=300)
    dci              = models.CharField(max_length=200, blank=True, verbose_name="DCI")
    forme            = models.CharField(max_length=20, choices=FORME, default='comprime')
    dosage           = models.CharField(max_length=100, blank=True)
    categorie        = models.ForeignKey(CategorieMedicament, on_delete=models.SET_NULL, null=True, blank=True)
    peut_etre_vendu  = models.BooleanField(default=True)
    peut_etre_achete = models.BooleanField(default=True)
    actif            = models.BooleanField(default=True)

    # Détails cliniques
    voie_administration            = models.CharField(max_length=200, blank=True)
    frequence                      = models.CharField(max_length=100, blank=True)
    composant_actif                = models.CharField(max_length=300, blank=True)
    effet_therapeutique            = models.ForeignKey(EffetTherapeutique, on_delete=models.SET_NULL, null=True, blank=True)
    effets_indesirables            = models.TextField(blank=True)
    quantite_prescription_manuelle = models.BooleanField(default=False)
    indications                    = models.TextField(blank=True)
    remarques                      = models.TextField(blank=True)

    # Grossesse
    avertissement_grossesse = models.BooleanField(default=False)
    avertissement_lactation = models.BooleanField(default=False)

    # Fabricant
    compagnie_pharma       = models.ForeignKey(CompagniePharma, on_delete=models.SET_NULL, null=True, blank=True)
    nom_produit_fabricant  = models.CharField(max_length=300, blank=True)
    code_produit_fabricant = models.CharField(max_length=100, blank=True)
    url_produit            = models.URLField(blank=True)

    # Tarifs & Stock
    prix_vente        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_achat        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_actuel      = models.IntegerField(default=0)
    stock_alerte      = models.IntegerField(default=10)
    stock_minimum     = models.IntegerField(default=5)
    reference_interne = models.CharField(max_length=100, blank=True)
    code_barres       = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.designation} ({self.dosage})" if self.dosage else self.designation

    class Meta:
        verbose_name = "Médicament"
        ordering    = ['designation']


# ─── GROUPE DE MÉDICAMENTS (formulaire catalogue) ─────────────────────────────

class GroupeMedicament(models.Model):
    nom      = models.CharField(max_length=200)
    medecin  = models.ForeignKey(
        'employer.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='groupes_medicament_catalogue'
    )
    limite   = models.IntegerField(default=0)
    maladies = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Groupe de médicaments"
        ordering = ['nom']


class LigneMedicamentGroupe(models.Model):
    groupe               = models.ForeignKey(GroupeMedicament, on_delete=models.CASCADE, related_name='lignes')
    medicament           = models.ForeignKey(Medicament, on_delete=models.CASCADE)
    autorise             = models.BooleanField(default=True)
    frequence_posologique = models.CharField(max_length=100, blank=True)
    dosage               = models.CharField(max_length=100, blank=True)
    unite_dosage         = models.CharField(max_length=50, blank=True)
    qte_par_jour         = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    jours                = models.IntegerField(default=1)
    qte_totale           = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    commentaire          = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.qte_totale = self.qte_par_jour * self.jours
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Ligne groupe médicament"
