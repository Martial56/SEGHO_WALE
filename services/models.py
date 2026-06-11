from django.db import models
from django.contrib.auth.models import User


class Typeservice(models.Model):
    nom = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Type de service"
        verbose_name_plural = "Types de service"
        ordering = ['nom']


class CategorieUniteMesure(models.Model):
    nom = models.CharField(max_length=100, unique=True, verbose_name="Nom")

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Catégorie d'unité de mesure"
        verbose_name_plural = "Catégories d'unités de mesure"
        ordering = ['nom']


class UniteMesure(models.Model):
    TYPE_CHOICES = [
        ('pgumr', "Plus grande que l'unité de mesure de référence"),
        ('umrc', "Unité de mesure de référence pour cette catégorie"),
        ('ppumr', "Plus petite que l'unité de mesure de référence"),
    ]
    nom = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Abréviation")
    categorie = models.ForeignKey(
        CategorieUniteMesure, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Catégorie", related_name='unites'
    )
    type_unite = models.CharField(max_length=10, choices=TYPE_CHOICES, default='umrc', verbose_name="Type")
    ratio = models.DecimalField(max_digits=12, decimal_places=6, default=1, verbose_name="Ratio")
    precision_arrondi = models.DecimalField(max_digits=8, decimal_places=5, default=0.01000, verbose_name="Précision d'arrondi")
    actif = models.BooleanField(default=True, verbose_name="Actif")

    def __str__(self): return f"{self.nom} ({self.code})"
    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"
        ordering = ['nom']


class CategorieArticle(models.Model):
    METHODE_COUT_CHOICES = [
        ('prix_standard', 'Prix standard'),
        ('avco', 'Coût moyen (AVCO)'),
        ('fifo', 'Premier entré, premier sorti (FIFO)'),
    ]
    VALORISATION_CHOICES = [
        ('manuelle', 'Manuelle'),
        ('automatique', 'Automatique'),
    ]
    RESERVATION_CHOICES = [
        ('partiels', 'Réserver des conditionnements partiels'),
        ('entiers', 'Réserver seulement des conditionnements entiers'),
    ]
    ENLEVEMENT_CHOICES = [
        ('', '—'),
        ('fifo', 'Premier entré, premier sorti (FIFO)'),
        ('fefo', 'Premier périmé, premier sorti (FEFO)'),
        ('lifo', 'Dernier entré, premier sorti (LIFO)'),
    ]

    # Identité
    code = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Code")
    nom = models.CharField(max_length=100, verbose_name="Nom")
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sous_categories', verbose_name="Catégorie parente"
    )
    description = models.TextField(blank=True, verbose_name="Description")

    # Code-barres
    sequence_code_barres = models.CharField(max_length=100, blank=True, verbose_name="Séquence de code-barres")

    # Numéro de série / lot
    bloquer_serie_lot = models.BooleanField(default=False, verbose_name="Bloquer les nouveaux numéros de série/lots")

    # Logistique
    routes = models.CharField(max_length=200, blank=True, verbose_name="Routes")
    strategie_enlevement = models.CharField(
        max_length=10, choices=ENLEVEMENT_CHOICES, blank=True,
        verbose_name="Forcer la stratégie d'enlèvement"
    )
    reservation_conditionnement = models.CharField(
        max_length=10, choices=RESERVATION_CHOICES, default='partiels',
        verbose_name="Réserver les conditionnements"
    )

    # Valorisation de l'inventaire
    methode_cout = models.CharField(
        max_length=20, choices=METHODE_COUT_CHOICES, default='prix_standard',
        verbose_name="Méthode de coût"
    )
    valorisation_inventaire = models.CharField(
        max_length=20, choices=VALORISATION_CHOICES, default='manuelle',
        verbose_name="Valorisation de l'inventaire"
    )

    # Propriétés du compte
    compte_revenus = models.CharField(max_length=200, blank=True, verbose_name="Compte de revenus")
    compte_charges = models.CharField(max_length=200, blank=True, verbose_name="Compte de charges")

    def save(self, *args, **kwargs):
        if not self.code:
            base = ''.join(c for c in self.nom.upper() if c.isalpha())[:6]
            candidate = base[:4]
            i = 1
            while CategorieArticle.objects.filter(code=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base[:3]}{i:02d}"
                i += 1
            self.code = candidate
        super().save(*args, **kwargs)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Catégorie d'article"
        verbose_name_plural = "Catégories d'article"
        ordering = ['nom']


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


class Articleservice(models.Model):

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
        ('prestation', 'Prestation'), ('consommable', 'Consommable'),
        ('stockable', 'Peut être stocké'), ('autre', 'Autre'),
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
    unite_mesure = models.ForeignKey(
        'UniteMesure', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_um', verbose_name="Unité de mesure"
    )
    unite_achat = models.ForeignKey(
        'UniteMesure', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_ua', verbose_name="Unité d'achat"
    )
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

    # ── Stock (affiché uniquement si type = consommable/stockable) ──
    quantite_stock = models.IntegerField(default=0, verbose_name="Quantité en stock")
    quantite_alerte = models.IntegerField(default=0, verbose_name="Quantité d'alerte")

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

    # ── Types de service ──────────────────────────────────────
    types = models.ManyToManyField(
        'Typeservice', blank=True,
        related_name='articles', verbose_name="Types de service"
    )

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
    article = models.ForeignKey(Articleservice, on_delete=models.CASCADE, related_name='fournisseurs')
    fournisseur = models.ForeignKey('achats.Fournisseur', on_delete=models.CASCADE, verbose_name="Fournisseur")
    nom_article_fournisseur = models.CharField(max_length=200, blank=True, verbose_name="Nom de l'article chez le fournisseur")
    reference_fournisseur = models.CharField(max_length=100, blank=True, verbose_name="Référence fournisseur")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    quantite_min = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Quantité min.")
    unite_mesure = models.ForeignKey(
        'UniteMesure', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Unité de mesure"
    )
    prix = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Prix (CFA)")
    delai_livraison = models.IntegerField(default=0, verbose_name="Délai de livraison (jours)")

    class Meta:
        verbose_name = "Fournisseur de l'article"
        ordering = ['fournisseur__nom']


class ConditionnementArticle(models.Model):
    article = models.ForeignKey(Articleservice, on_delete=models.CASCADE, related_name='conditionnements')
    conditionnement = models.CharField(max_length=100, verbose_name="Conditionnement")
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité contenue")
    unite_mesure = models.ForeignKey(
        'UniteMesure', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Unité de mesure"
    )
    pour_vente = models.BooleanField(default=True, verbose_name="Ventes")
    pour_achat = models.BooleanField(default=True, verbose_name="Achats")

    class Meta:
        verbose_name = "Conditionnement"


class VarianteAttributArticle(models.Model):
    article = models.ForeignKey(Articleservice, on_delete=models.CASCADE, related_name='variantes')
    caracteristique = models.CharField(max_length=100, verbose_name="Caractéristique")
    valeurs = models.CharField(max_length=300, verbose_name="Valeurs")

    class Meta:
        verbose_name = "Attribut / Variante"


class ReglePrix(models.Model):
    article = models.ForeignKey(Articleservice, on_delete=models.CASCADE, related_name='regles_prix')
    liste_prix = models.CharField(max_length=100, verbose_name="Liste de prix")
    applique_sur = models.CharField(max_length=200, blank=True, verbose_name="Appliqué sur")
    quantite_min = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Quantité min.")
    prix = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Prix (CFA)")
    date_debut = models.DateField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")

    class Meta:
        verbose_name = "Règle de prix"
        ordering = ['liste_prix']


class Consommable(models.Model):
    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Code")
    nom = models.CharField(max_length=300, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    categorie = models.ForeignKey(
        CategorieArticle, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Catégorie"
    )
    unite_mesure = models.ForeignKey(
        UniteMesure, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Unité de mesure"
    )
    prix_achat = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Prix d'achat (CFA)")
    prix_vente = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Prix de vente (CFA)")
    quantite_stock = models.IntegerField(default=0, verbose_name="Quantité en stock")
    quantite_alerte = models.IntegerField(default=0, verbose_name="Quantité d'alerte")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.code:
            from django.utils import timezone
            year = timezone.now().year
            prefix = f'CONS{year}'
            last = Consommable.objects.filter(code__startswith=prefix).order_by('code').last()
            if last:
                try:
                    seq = int(last.code[len(prefix):]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.code = f'{prefix}{seq:04d}'
        super().save(*args, **kwargs)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Consommable"
        verbose_name_plural = "Consommables"
        ordering = ['nom']
