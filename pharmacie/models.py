from django.db import models
from django.contrib.auth.models import User


class CategorieMedicament(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Catégorie médicament"



class Medicament(models.Model):
    FORME = [('comprime','Comprimé'),('sirop','Sirop'),('injectable','Injectable'),('pommade','Pommade'),('gelule','Gélule'),('solution','Solution'),('autre','Autre')]

    code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=300)
    dci = models.CharField(max_length=200, blank=True, verbose_name="Dénomination Commune Internationale")
    forme = models.CharField(max_length=20, choices=FORME, default='comprime')
    dosage = models.CharField(max_length=100, blank=True)
    categorie = models.ForeignKey(CategorieMedicament, on_delete=models.SET_NULL, null=True, blank=True)
    prix_vente = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_actuel = models.IntegerField(default=0)
    stock_alerte = models.IntegerField(default=10)
    stock_minimum = models.IntegerField(default=5)
    actif = models.BooleanField(default=True)

    def __str__(self): return f"{self.designation} ({self.dosage})"
    class Meta:
        verbose_name = "Médicament"
        ordering = ['designation']


class LotMedicament(models.Model):
    medicament = models.ForeignKey(Medicament, on_delete=models.CASCADE, related_name='lots')
    numero_lot = models.CharField(max_length=100)
    date_fabrication = models.DateField(null=True, blank=True)
    date_peremption = models.DateField()
    quantite_initiale = models.IntegerField()
    quantite_actuelle = models.IntegerField()
    fournisseur = models.ForeignKey('achats.Fournisseur', on_delete=models.SET_NULL, null=True, blank=True)
    date_reception = models.DateField(auto_now_add=True)

    def __str__(self): return f"{self.medicament} - Lot {self.numero_lot}"
    class Meta: verbose_name = "Lot médicament"


class MouvementStock(models.Model):
    TYPE = [('entree','Entrée'),('sortie','Sortie'),('ajustement','Ajustement'),('peremption','Péremption')]
    MOTIF = [('achat','Achat'),('vente','Vente'),('hospitalisation','Hospitalisation'),('urgence','Urgence'),('inventaire','Inventaire'),('perte','Perte')]

    medicament = models.ForeignKey(Medicament, on_delete=models.CASCADE, related_name='mouvements')
    lot = models.ForeignKey(LotMedicament, on_delete=models.SET_NULL, null=True, blank=True)
    type_mouvement = models.CharField(max_length=20, choices=TYPE)
    motif = models.CharField(max_length=20, choices=MOTIF)
    quantite = models.IntegerField()
    stock_avant = models.IntegerField()
    stock_apres = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    date_mouvement = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        ordering = ['-date_mouvement']


class CommandePharmacies(models.Model):
    STATUT = [('brouillon','Brouillon'),('envoye','Envoyé'),('recu','Reçu'),('partiel','Partiel'),('annule','Annulé')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    fournisseur = models.ForeignKey('achats.Fournisseur', on_delete=models.SET_NULL, null=True)
    date_commande = models.DateField(auto_now_add=True)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon')
    montant_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            prefix = f"CMD{annee}"
            last = CommandePharmacies.objects.filter(numero__startswith=prefix).order_by('-pk').first()
            count = (int(last.numero[len(prefix):]) + 1) if last else 1
            self.numero = f"{prefix}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Commande {self.numero}"
    class Meta: verbose_name = "Commande pharmacie"


# ── Module Pharmacie Walé ─────────────────────────────────────────────────

PHARMACIES_WALE = [
    ('wale_toumbokro',    'Walé Toumbokro'),
    ('wale_yamoussoukro', 'Walé Yamoussoukro'),
]


class StockPharmacie(models.Model):
    """Stock disponible dans chaque pharmacie (alimenté par les dotations)."""
    pharmacie   = models.CharField(max_length=30, choices=PHARMACIES_WALE)
    produit     = models.ForeignKey('stock.Produit', on_delete=models.CASCADE, related_name='stocks_pharmacie')
    quantite    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_maj    = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.get_pharmacie_display()} — {self.produit.nom} ({self.quantite})"
    class Meta:
        verbose_name = "Stock pharmacie"
        unique_together = ('pharmacie', 'produit')
        ordering = ['pharmacie', 'produit__nom']


class MouvementPharmacie(models.Model):
    """Traçabilité des mouvements internes à chaque pharmacie."""
    TYPE_CHOICES = [
        ('entree',      'Entrée (dotation)'),
        ('dispensation','Dispensation ordonnance'),
        ('vente',       'Vente caisse'),
        ('retour',      'Retour produit'),
        ('ajustement',  'Ajustement'),
    ]
    pharmacie   = models.CharField(max_length=30, choices=PHARMACIES_WALE)
    produit     = models.ForeignKey('stock.Produit', on_delete=models.CASCADE, related_name='mouvements_pharmacie')
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantite    = models.DecimalField(max_digits=12, decimal_places=2)
    stock_avant = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_apres = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date        = models.DateTimeField(auto_now_add=True)
    reference   = models.CharField(max_length=100, blank=True)
    notes       = models.TextField(blank=True)
    cree_par    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mouvements_pharmacie')

    def __str__(self): return f"{self.get_pharmacie_display()} — {self.produit.nom} ({self.get_type_display()})"
    class Meta:
        verbose_name = "Mouvement pharmacie"
        ordering = ['-date']


class DispensationOrdonnance(models.Model):
    """Lien entre une ordonnance et sa dispensation dans une pharmacie."""
    STATUT_CHOICES = [
        ('complete',  'Complète'),
        ('partielle', 'Partielle'),
    ]
    pharmacie    = models.CharField(max_length=30, choices=PHARMACIES_WALE)
    ordonnance   = models.OneToOneField('consultations.Ordonnance', on_delete=models.CASCADE, related_name='dispensation')
    statut       = models.CharField(max_length=20, choices=STATUT_CHOICES, default='complete')
    date         = models.DateTimeField(auto_now_add=True)
    notes        = models.TextField(blank=True)
    dispense_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='dispensations')

    def __str__(self): return f"Dispensation {self.ordonnance.numero} — {self.get_pharmacie_display()}"
    class Meta:
        verbose_name = "Dispensation ordonnance"
        ordering = ['-date']


class LigneDispensation(models.Model):
    """Détail des produits dispensés pour une ordonnance."""
    dispensation       = models.ForeignKey(DispensationOrdonnance, on_delete=models.CASCADE, related_name='lignes')
    produit            = models.ForeignKey('stock.Produit', on_delete=models.PROTECT, null=True, blank=True)
    medicament_libre   = models.CharField(max_length=200, blank=True)
    quantite_prescrite = models.IntegerField(default=1)
    quantite_dispensee = models.IntegerField(default=0)
    notes              = models.CharField(max_length=200, blank=True)

    def __str__(self): return f"{self.produit or self.medicament_libre} × {self.quantite_dispensee}"
    class Meta:
        verbose_name = "Ligne de dispensation"


class VentePharmacie(models.Model):
    MODES_PAIEMENT = [
        ('especes',      'Espèces'),
        ('mobile_money', 'Mobile Money'),
        ('assurance',    'Assurance'),
    ]
    STATUTS = [
        ('payee',   'Payée'),
        ('annulee', 'Annulée'),
    ]
    pharmacie     = models.CharField(max_length=30, choices=PHARMACIES_WALE)
    numero        = models.CharField(max_length=20, unique=True, editable=False)
    patient       = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventes_pharmacie')
    ordonnance    = models.ForeignKey('consultations.Ordonnance', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventes_pharmacie')
    date_vente    = models.DateTimeField(auto_now_add=True)
    mode_paiement = models.CharField(max_length=20, choices=MODES_PAIEMENT, default='especes')
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remise        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_net   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    statut        = models.CharField(max_length=20, choices=STATUTS, default='payee')
    notes         = models.TextField(blank=True)
    cree_par      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventes_pharmacie')

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = VentePharmacie.objects.filter(date_vente__year=annee).count() + 1
            self.numero = f"VNT{annee}{count:04d}"
        self.montant_net = self.montant_total - self.remise
        super().save(*args, **kwargs)

    def __str__(self): return f"Vente {self.numero}"
    class Meta:
        verbose_name = "Vente pharmacie"
        ordering = ['-date_vente']


class LigneVente(models.Model):
    vente         = models.ForeignKey(VentePharmacie, on_delete=models.CASCADE, related_name='lignes')
    produit       = models.ForeignKey('stock.Produit', on_delete=models.PROTECT)
    quantite      = models.DecimalField(max_digits=10, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    montant       = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.montant = self.quantite * self.prix_unitaire
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.produit.nom} x {self.quantite}"
    class Meta:
        verbose_name = "Ligne de vente"


class InventairePharmacie(models.Model):
    STATUTS = [('brouillon', 'Brouillon'), ('valide', 'Validé')]
    pharmacie         = models.CharField(max_length=30, choices=PHARMACIES_WALE)
    numero            = models.CharField(max_length=20, unique=True, editable=False)
    date_inventaire   = models.DateField()
    statut            = models.CharField(max_length=20, choices=STATUTS, default='brouillon')
    notes             = models.TextField(blank=True)
    cree_par          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventaires_pharmacie')
    valide_par        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventaires_pharmacie_valides')
    date_validation   = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = InventairePharmacie.objects.filter(date_inventaire__year=annee).count() + 1
            self.numero = f"INV-PH{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Inventaire {self.numero}"
    class Meta:
        verbose_name = "Inventaire pharmacie"
        ordering = ['-date_inventaire']


class LigneInventairePharmacie(models.Model):
    inventaire      = models.ForeignKey(InventairePharmacie, on_delete=models.CASCADE, related_name='lignes')
    produit         = models.ForeignKey('stock.Produit', on_delete=models.PROTECT)
    stock_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_reel      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes           = models.CharField(max_length=200, blank=True)

    @property
    def ecart(self):
        return self.stock_reel - self.stock_theorique

    def __str__(self): return f"{self.produit.nom} — écart {self.ecart}"
    class Meta:
        verbose_name = "Ligne inventaire pharmacie"
