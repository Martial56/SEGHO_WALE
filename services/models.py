from django.db import models
from django.contrib.auth.models import User


class UniteMesure(models.Model):
    CATEGORIE_CHOICES = [
        ('volume', 'Volume'), ('masse', 'Masse'), ('quantite', 'Quantité'),
        ('conditionnement', 'Conditionnement'), ('autre', 'Autre'),
    ]
    nom = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Abréviation")
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='quantite', verbose_name="Catégorie")

    def __str__(self): return f"{self.nom} ({self.code})"
    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"
        ordering = ['nom']


class CategorieArticle(models.Model):
    code = models.CharField(max_length=10, unique=True)
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self): return f"{self.code} — {self.nom}"
    class Meta:
        verbose_name = "Catégorie d'article"
        ordering = ['code']


class FamilleArticle(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, blank=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Famille d'article"
        ordering = ['nom']


class CompagniePharma(models.Model):
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Compagnie pharmaceutique"
        ordering = ['nom']


class ArticleService(models.Model):

    FORME_CHOICES = [
        ('comprime', 'Comprimé'), ('sirop', 'Sirop'), ('injectable', 'Injectable'),
        ('pommade', 'Pommade'), ('gelule', 'Gélule'), ('solution', 'Solution'),
        ('suppositoire', 'Suppositoire'), ('patch', 'Patch'),
        ('sachet', 'Sachet'), ('gouttes', 'Gouttes'), ('autre', 'Autre'),
    ]
    VOIE_CHOICES = [
        ('orale', 'Orale'), ('injectable', 'Injectable / IV'),
        ('topique', 'Topique / Cutanée'), ('rectale', 'Rectale'),
        ('nasale', 'Nasale'), ('ophtalmique', 'Ophtalmique'), ('autre', 'Autre'),
    ]
    TYPE_ARTICLE_CHOICES = [
        ('consommable', 'Consommable'), ('stockable', 'Peut être stocké'),
        ('service', 'Service'), ('autre', 'Autre'),
    ]
    TYPE_PRODUIT_CHOICES = [
        ('medicament', 'Médicament'), ('consommable', 'Consommable médical'),
        ('equipement', 'Équipement'), ('service', 'Service médical'),
        ('examen', 'Examen / Analyse'), ('autre', 'Autre'),
    ]
    POLITIQUE_FACT_CHOICES = [
        ('qtes_commandees', 'Quantités commandées'),
        ('qtes_livrees', 'Quantités livrées'),
    ]
    REFACTURER_CHOICES = [
        ('non', 'Non'), ('au_cout', 'Au coût'), ('prix_vente', 'Prix de vente'),
    ]
    POLITIQUE_CONTROLE_CHOICES = [
        ('qtes_commandees', 'Sur les quantités commandées'),
        ('qtes_recues', 'Sur les quantités reçues'),
    ]

    # ── En-tête ───────────────────────────────────────────────
    nom = models.CharField(max_length=300, verbose_name="Nom de l'article")
    reference_interne = models.CharField(max_length=100, blank=True, verbose_name="Référence interne")
    photo = models.ImageField(upload_to='services/photos/', blank=True, null=True)
    favori = models.BooleanField(default=False, verbose_name="Favori")
    peut_etre_vendu = models.BooleanField(default=True, verbose_name="Peut être vendu")
    peut_etre_achete = models.BooleanField(default=True, verbose_name="Peut être acheté")

    # ── Onglet 1 : Détails du médicament ─────────────────────
    forme = models.CharField(max_length=20, choices=FORME_CHOICES, blank=True, verbose_name="Forme")
    voie_administration = models.CharField(max_length=20, choices=VOIE_CHOICES, blank=True, verbose_name="Voie d'administration")
    dosage = models.CharField(max_length=100, blank=True, verbose_name="Dosage")
    dosage_unite = models.CharField(max_length=50, blank=True, verbose_name="Unité de dosage")
    quantite_prescription_manuelle = models.BooleanField(default=False, verbose_name="Quantité de prescription manuelle")
    frequence = models.CharField(max_length=100, blank=True, verbose_name="Fréquence")
    composant_actif = models.CharField(max_length=200, blank=True, verbose_name="Composant actif")
    effet_therapeutique = models.CharField(max_length=200, blank=True, verbose_name="Effet thérapeutique")
    effets_indesirables = models.TextField(blank=True, verbose_name="Effets indésirables")
    compagnie_pharmaceutique = models.ForeignKey(
        CompagniePharma, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Compagnie pharmaceutique"
    )
    code_produit = models.CharField(max_length=100, blank=True, verbose_name="Code produit")
    url_produit = models.URLField(blank=True, verbose_name="URL du produit")
    nom_produit_fabricant = models.CharField(max_length=200, blank=True, verbose_name="Nom du produit")
    avertissement_grossesse = models.BooleanField(default=False, verbose_name="Avertissement de grossesse")
    avertissement_lactation = models.BooleanField(default=False, verbose_name="Avertissement de lactation")
    indications = models.TextField(blank=True, verbose_name="Indications")
    remarques = models.TextField(blank=True, verbose_name="Remarques")

    # ── Onglet 2 : Information Générale ──────────────────────
    type_article = models.CharField(max_length=20, choices=TYPE_ARTICLE_CHOICES, default='consommable', verbose_name="Type d'article")
    type_produit_hospitalier = models.CharField(max_length=20, choices=TYPE_PRODUIT_CHOICES, blank=True, verbose_name="Type de produit hospitalier")
    politique_facturation = models.CharField(max_length=20, choices=POLITIQUE_FACT_CHOICES, default='qtes_commandees', verbose_name="Politique de facturation")
    refacturer_depenses = models.CharField(max_length=20, choices=REFACTURER_CHOICES, default='non', verbose_name="Re-facturer les dépenses")
    unite_mesure = models.CharField(max_length=50, default='Unités', verbose_name="Unité de mesure")
    unite_achat = models.CharField(max_length=50, default='Unités', verbose_name="Unité d'achat")
    prix_vente = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Prix de vente (CFA)")
    taxes_vente = models.CharField(max_length=100, blank=True, verbose_name="Taxes à la vente")
    cout = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Coût")
    categorie = models.ForeignKey(
        CategorieArticle, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Catégorie d'article"
    )
    code_barres = models.CharField(max_length=100, blank=True, verbose_name="Code-barres")
    famille = models.ForeignKey(
        FamilleArticle, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Famille"
    )
    notes_internes = models.TextField(blank=True, verbose_name="Notes internes")

    # ── Onglet 4 : Vente ─────────────────────────────────────
    description_vente = models.TextField(blank=True, verbose_name="Description vente")

    # ── Onglet 5 : Achats ────────────────────────────────────
    taxes_fournisseur = models.CharField(max_length=100, blank=True, verbose_name="Taxes fournisseur")
    politique_controle = models.CharField(max_length=20, choices=POLITIQUE_CONTROLE_CHOICES, default='qtes_recues', verbose_name="Politique de contrôle")
    description_achat = models.TextField(blank=True, verbose_name="Description achat")

    # ── Onglet 6 : Stock ─────────────────────────────────────
    responsable = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_responsable', verbose_name="Responsable"
    )
    poids = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Poids (kg)")
    volume = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Volume (m³)")
    delai_livraison_client = models.DecimalField(max_digits=6, decimal_places=1, default=0, verbose_name="Délai de livraison au client (jours)")
    description_reception = models.TextField(blank=True, verbose_name="Description pour les réceptions")
    description_livraison = models.TextField(blank=True, verbose_name="Description pour les bons de livraison")
    description_transfert = models.TextField(blank=True, verbose_name="Description pour les transferts internes")

    # ── Onglet 7 : Comptabilité ──────────────────────────────
    compte_revenus = models.CharField(max_length=100, blank=True, verbose_name="Compte de revenus")
    compte_charges = models.CharField(max_length=100, blank=True, verbose_name="Compte de charges")
    compte_ecart_prix = models.CharField(max_length=100, blank=True, verbose_name="Compte d'écart de prix")

    # ── Meta ─────────────────────────────────────────────────
    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_crees', verbose_name="Créé par"
    )

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Article / Service"
        verbose_name_plural = "Articles / Services"
        ordering = ['nom']


class LigneFournisseurArticle(models.Model):
    article = models.ForeignKey(ArticleService, on_delete=models.CASCADE, related_name='fournisseurs')
    fournisseur = models.ForeignKey('pharmacie.Fournisseur', on_delete=models.CASCADE, verbose_name="Fournisseur")
    nom_article_fournisseur = models.CharField(max_length=200, blank=True, verbose_name="Nom de l'article chez le fournisseur")
    reference_fournisseur = models.CharField(max_length=100, blank=True, verbose_name="Référence fournisseur")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    quantite_min = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Quantité min.")
    unite_mesure = models.CharField(max_length=50, default='Unités', verbose_name="Unité de mesure")
    prix = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Prix (CFA)")
    delai_livraison = models.IntegerField(default=0, verbose_name="Délai de livraison (jours)")

    class Meta:
        verbose_name = "Fournisseur de l'article"
        ordering = ['fournisseur__nom']


class ConditionnementArticle(models.Model):
    article = models.ForeignKey(ArticleService, on_delete=models.CASCADE, related_name='conditionnements')
    conditionnement = models.CharField(max_length=100, verbose_name="Conditionnement")
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité contenue")
    unite_mesure = models.CharField(max_length=50, default='Unités', verbose_name="Unité de mesure")
    pour_vente = models.BooleanField(default=True, verbose_name="Ventes")
    pour_achat = models.BooleanField(default=True, verbose_name="Achats")

    class Meta:
        verbose_name = "Conditionnement"


class VarianteAttributArticle(models.Model):
    article = models.ForeignKey(ArticleService, on_delete=models.CASCADE, related_name='variantes')
    caracteristique = models.CharField(max_length=100, verbose_name="Caractéristique")
    valeurs = models.CharField(max_length=300, verbose_name="Valeurs")

    class Meta:
        verbose_name = "Attribut / Variante"


class ReglePrix(models.Model):
    article = models.ForeignKey(ArticleService, on_delete=models.CASCADE, related_name='regles_prix')
    liste_prix = models.CharField(max_length=100, verbose_name="Liste de prix")
    applique_sur = models.CharField(max_length=200, blank=True, verbose_name="Appliqué sur")
    quantite_min = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Quantité min.")
    prix = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Prix (CFA)")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        verbose_name = "Règle de prix"
        ordering = ['liste_prix']
