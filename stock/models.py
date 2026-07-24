from functools import cached_property

from django.db import models
from django.utils import timezone


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


class CategorieStock(models.Model):
    TYPE_CHOICES = [
        ('medicament',  'Médicament'),
        ('consommable', 'Consommable médical'),
        ('equipement',  'Équipement & matériel'),
    ]
    nom         = models.CharField(max_length=100)
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES, default='medicament')
    description = models.TextField(blank=True)
    actif       = models.BooleanField(default=True)

    def __str__(self): return f"{self.nom} ({self.get_type_display()})"
    class Meta:
        verbose_name = "Catégorie de stock"
        ordering = ['type', 'nom']



class Produit(models.Model):
    TYPE_CHOICES = [
        ('medicament',  'Médicament'),
        ('consommable', 'Consommable médical'),
        ('equipement',  'Équipement & matériel'),
    ]
    FORME_CHOICES = [
        ('comprime',    'Comprimé'),
        ('gelule',      'Gélule'),
        ('sirop',       'Sirop'),
        ('injectable',  'Injectable'),
        ('creme',       'Crème'),
        ('pommade',     'Pommade'),
        ('gouttes',     'Gouttes'),
        ('suppositoire','Suppositoire'),
        ('autre',       'Autre'),
    ]
    code      = models.CharField(max_length=20, unique=True, blank=True)
    nom       = models.CharField(max_length=200)
    type      = models.CharField(max_length=20, choices=TYPE_CHOICES, default='medicament')
    categorie = models.ForeignKey(CategorieStock, on_delete=models.SET_NULL, null=True, blank=True)
    fournisseur_principal = models.ForeignKey(
        'achats.Fournisseur', on_delete=models.SET_NULL, null=True, blank=True
    )
    description  = models.TextField(blank=True)
    unite_mesure = models.ForeignKey(
        'UniteMesure', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Unité de mesure',
    )

    # Champs spécifiques médicaments
    dci    = models.CharField("DCI / Principe actif", max_length=200, blank=True)
    dosage = models.CharField(max_length=100, blank=True)
    forme  = models.CharField(max_length=20, choices=FORME_CHOICES, blank=True)
    prescription_obligatoire = models.BooleanField(default=False)

    # Stock
    stock_actuel  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_alerte  = models.DecimalField(max_digits=12, decimal_places=2, default=10)
    stock_minimum = models.DecimalField(max_digits=12, decimal_places=2, default=5)

    # Prix
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_vente = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    actif         = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    modifie_par   = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    modifie_le    = models.DateTimeField(null=True, blank=True)

    @property
    def en_rupture(self):
        return self.stock_actuel <= 0

    @property
    def en_alerte(self):
        return 0 < self.stock_actuel <= self.stock_alerte

    @cached_property
    def cmm(self):
        """Consommation Mensuelle Moyenne sur les 3 derniers mois.
        Mémorisé sur l'instance : couverture_jours/point_commande/
        qte_a_commander en dépendent tous et ne doivent pas chacun
        redéclencher la requête d'agrégation."""
        from django.db.models import Sum
        today = timezone.now().date()
        debut = today.replace(day=1)
        # Reculer de 3 mois
        import datetime
        for _ in range(3):
            debut = (debut - datetime.timedelta(days=1)).replace(day=1)
        total = self.mouvements.filter(
            type='livraison', date__date__gte=debut
        ).aggregate(t=Sum('quantite'))['t'] or 0
        return round(float(total) / 3, 1)

    @property
    def couverture_jours(self):
        """Nombre de jours de couverture = stock actuel / (CMM / 30)."""
        cmm = self.cmm
        if cmm <= 0:
            return None
        return round(float(self.stock_actuel) / (cmm / 30))

    @property
    def point_commande(self):
        """Point de commande = CMM × 1 mois (délai) + stock_minimum."""
        return round(self.cmm + float(self.stock_minimum))

    @property
    def qte_a_commander(self):
        """Quantité à commander = (CMM × 3 mois) - stock actuel + stock_minimum."""
        besoin = self.cmm * 3
        qte = max(0, besoin - float(self.stock_actuel) + float(self.stock_minimum))
        return round(qte)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.stock_minimum and self.stock_alerte and self.stock_minimum >= self.stock_alerte:
            raise ValidationError({'stock_minimum': 'Le stock minimum doit être inférieur au seuil d\'alerte.'})
        if self.prix_achat and self.prix_vente and self.prix_achat > self.prix_vente:
            raise ValidationError({'prix_vente': 'Le prix de vente ne peut pas être inférieur au prix d\'achat.'})

    def __str__(self): return self.nom
    def save(self, *args, **kwargs):
        if not self.code:
            prefix = {'medicament': 'MED', 'consommable': 'CONS', 'equipement': 'EQP'}.get(self.type, 'PRD')
            annee = timezone.now().year
            dernier = Produit.objects.filter(code__startswith=f'{prefix}{annee}').order_by('-code').first()
            seq = (int(dernier.code[-4:]) + 1) if dernier else 1
            self.code = f'{prefix}{annee}{seq:04d}'
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Produit"
        ordering = ['type', 'nom']
        indexes = [
            models.Index(fields=['actif', 'type']),
        ]


class LotProduit(models.Model):
    produit           = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='lots')
    numero_lot        = models.CharField(max_length=50)
    date_fabrication  = models.DateField(null=True, blank=True)
    date_peremption   = models.DateField(null=True, blank=True)
    quantite_initiale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantite_actuelle = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fournisseur       = models.ForeignKey('achats.Fournisseur', on_delete=models.SET_NULL, null=True, blank=True)
    date_reception    = models.DateField(default=timezone.now)
    prix_achat_lot    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes             = models.TextField(blank=True)

    @property
    def est_perime(self):
        return bool(self.date_peremption and self.date_peremption < timezone.now().date())

    @property
    def jours_restants(self):
        if not self.date_peremption:
            return None
        delta = (self.date_peremption - timezone.now().date()).days
        return delta  # négatif si périmé, positif si pas encore périmé

    def __str__(self): return f"{self.produit.nom} — Lot {self.numero_lot}"
    class Meta:
        verbose_name = "Lot"
        ordering = ['date_peremption']
        indexes = [
            models.Index(fields=['date_peremption', 'quantite_actuelle']),
        ]


PHARMACIES = [
    ('wale_toumbokro',    'Walé Toumbokro'),
    ('wale_yamoussoukro', 'Walé Yamoussoukro'),
]


class MouvementStock(models.Model):
    TYPE_CHOICES = [
        ('entree',    'Entrée en stock'),
        ('livraison', 'Livraison pharmacie'),
        ('ajustement','Ajustement inventaire'),
        ('peremption','Péremption'),
        ('retour',    'Retour fournisseur'),
    ]
    MOTIF_CHOICES = [
        ('achat',      'Achat fournisseur'),
        ('livraison',  'Livraison à une pharmacie'),
        ('inventaire', 'Inventaire'),
        ('peremption', 'Péremption / Perte'),
        ('retour',     'Retour fournisseur'),
        ('don',        'Don / Subvention'),
        ('autre',      'Autre'),
    ]
    produit     = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='mouvements')
    lot         = models.ForeignKey(LotProduit, on_delete=models.SET_NULL, null=True, blank=True)
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES)
    motif       = models.CharField(max_length=20, choices=MOTIF_CHOICES, blank=True)
    pharmacie   = models.CharField(max_length=30, choices=PHARMACIES, blank=True)
    quantite    = models.DecimalField(max_digits=12, decimal_places=2)
    stock_avant = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_apres = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date        = models.DateTimeField(default=timezone.now)
    reference   = models.CharField(max_length=100, blank=True)
    notes       = models.TextField(blank=True)
    cree_par    = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_mouvements')

    def __str__(self): return f"{self.get_type_display()} — {self.produit.nom} ({self.quantite})"
    class Meta:
        verbose_name = "Mouvement de stock"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['type', 'date']),
        ]


class CommandeStock(models.Model):
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('envoye',    'Envoyée'),
        ('partiel',   'Reçu partiellement'),
        ('recu',      'Reçu complet'),
        ('annule',    'Annulée'),
    ]
    numero        = models.CharField(max_length=20, unique=True, blank=True)
    fournisseur   = models.ForeignKey('achats.Fournisseur', on_delete=models.PROTECT, related_name='commandes_stock')
    statut        = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    date_commande = models.DateField(default=timezone.now)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    date_reception = models.DateField(null=True, blank=True)
    notes         = models.TextField(blank=True)
    montant_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cree_par      = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_commandes')
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Commande {self.numero} — {self.fournisseur}"
    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = CommandeStock.objects.filter(numero__startswith=f'CMD{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'CMD{annee}{seq:04d}'
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Commande de stock"
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['statut']),
        ]


class LigneCommande(models.Model):
    commande           = models.ForeignKey(CommandeStock, on_delete=models.CASCADE, related_name='lignes')
    produit            = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite_commandee = models.DecimalField(max_digits=12, decimal_places=2)
    quantite_recue     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_unitaire      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes              = models.CharField(max_length=200, blank=True)

    @property
    def montant(self):
        return self.quantite_commandee * self.prix_unitaire

    def __str__(self): return f"{self.produit.nom} × {self.quantite_commandee}"
    class Meta:
        verbose_name = "Ligne de commande"


class Inventaire(models.Model):
    STATUT_CHOICES = [
        ('brouillon', 'En cours'),
        ('valide',    'Validé'),
        ('annule',    'Annulé'),
    ]
    numero        = models.CharField(max_length=20, unique=True, blank=True)
    date_inventaire = models.DateField(default=timezone.now)
    statut        = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    notes         = models.TextField(blank=True)
    cree_par      = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='inventaires_stock')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    def __str__(self): return f"Inventaire {self.numero}"
    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = Inventaire.objects.filter(numero__startswith=f'INV{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'INV{annee}{seq:04d}'
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Inventaire"
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['statut']),
        ]


class LigneInventaire(models.Model):
    inventaire        = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    produit           = models.ForeignKey(Produit, on_delete=models.PROTECT)
    stock_theorique   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_reel        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ecart             = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_peremption   = models.DateField(null=True, blank=True)
    notes             = models.CharField(max_length=200, blank=True)

    def __str__(self): return f"{self.produit.nom} — Inv {self.inventaire.numero}"
    def save(self, *args, **kwargs):
        from decimal import Decimal
        self.ecart = Decimal(str(self.stock_reel)) - Decimal(str(self.stock_theorique))
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Ligne d'inventaire"


class DemandePharmacie(models.Model):
    STATUT_CHOICES = [
        ('en_attente',   'En attente'),
        ('en_livraison', 'En livraison'),
        ('approuvee',    'Confirmée'),
        ('partielle',    'Confirmée partiellement'),
        ('refusee',      'Refusée'),
    ]
    numero      = models.CharField(max_length=20, unique=True, blank=True)
    pharmacie   = models.CharField(max_length=30, choices=PHARMACIES)
    statut      = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    date_demande = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    notes       = models.TextField(blank=True)
    notes_stock = models.TextField(blank=True, verbose_name="Réponse du gestionnaire")
    cree_par    = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_pharmacie')
    traite_par  = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='dotations_traitees')

    def __str__(self): return f"Demande {self.numero} — {self.get_pharmacie_display()}"
    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = DemandePharmacie.objects.filter(numero__startswith=f'DEM{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'DEM{annee}{seq:04d}'
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = "Demande pharmacie"
        ordering = ['-date_demande']
        indexes = [
            models.Index(fields=['pharmacie', 'statut']),
        ]


class LigneDemande(models.Model):
    demande           = models.ForeignKey(DemandePharmacie, on_delete=models.CASCADE, related_name='lignes')
    produit           = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite_demandee = models.DecimalField(max_digits=12, decimal_places=2)
    quantite_approuvee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes             = models.CharField(max_length=200, blank=True)

    def __str__(self): return f"{self.produit.nom} × {self.quantite_demandee}"
    class Meta:
        verbose_name = "Ligne de demande"


# ── Fiche de besoins mensuelle pharmacie ──────────────────────────────────

class FicheBesoins(models.Model):
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('soumis',    'Soumis pour validation'),
        ('valide',    'Validé'),
        ('rejete',    'Rejeté'),
    ]
    numero          = models.CharField(max_length=20, unique=True, blank=True)
    pharmacie       = models.CharField(max_length=30, choices=PHARMACIES, blank=True, default='')
    periode_debut   = models.DateField()
    periode_fin     = models.DateField()
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    notes           = models.TextField(blank=True)
    notes_direction = models.TextField(blank=True, verbose_name='Observations direction')
    cree_par        = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='fiches_besoins_creees')
    valide_par      = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='fiches_besoins_validees')
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    def __str__(self): return f'Fiche {self.numero} — {self.periode_debut} / {self.periode_fin}'
    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = FicheBesoins.objects.filter(numero__startswith=f'FB{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'FB{annee}{seq:04d}'
        super().save(*args, **kwargs)
    class Meta:
        verbose_name = 'Fiche de besoins'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['statut', 'pharmacie']),
        ]


class LigneFicheBesoins(models.Model):
    fiche           = models.ForeignKey(FicheBesoins, on_delete=models.CASCADE, related_name='lignes')
    produit         = models.ForeignKey(Produit, on_delete=models.PROTECT)
    stock_initial   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    qte_recue       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    qte_dispensee   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cmm             = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    qte_commander   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    qte_accordee    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes           = models.CharField(max_length=200, blank=True)

    @property
    def stock_disponible(self):
        return self.stock_initial + self.qte_recue - self.qte_dispensee

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.qte_accordee and self.qte_commander and self.qte_accordee > self.qte_commander:
            raise ValidationError({'qte_accordee': 'La quantité accordée ne peut pas dépasser la quantité demandée.'})

    def __str__(self): return f'{self.produit.nom} — {self.fiche.numero}'
    class Meta:
        verbose_name = 'Ligne fiche besoins'
        ordering = ['produit__type', 'produit__nom']
