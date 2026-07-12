from django.db import models
from django.utils import timezone


class Fournisseur(models.Model):
    code              = models.CharField(max_length=20, unique=True, blank=True)
    nom               = models.CharField(max_length=150)
    telephone         = models.CharField(max_length=30, blank=True)
    telephone2        = models.CharField(max_length=30, blank=True)
    email             = models.EmailField(blank=True)
    adresse           = models.TextField(blank=True)
    ville             = models.CharField(max_length=100, blank=True)
    pays              = models.CharField(max_length=100, default="Côte d'Ivoire")
    contact_nom       = models.CharField("Nom du contact", max_length=150, blank=True)
    contact_telephone = models.CharField("Tél. contact", max_length=30, blank=True)
    contact_email     = models.EmailField("Email contact", blank=True)
    specialites       = models.TextField("Types de produits fournis", blank=True)
    conditions_paiement = models.CharField(max_length=200, blank=True)
    delai_livraison_moyen = models.PositiveIntegerField("Délai livraison moyen (j)", null=True, blank=True)
    actif             = models.BooleanField(default=True)
    notes             = models.TextField(blank=True)
    date_creation     = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nom

    def save(self, *args, **kwargs):
        if not self.code:
            annee = timezone.now().year
            dernier = Fournisseur.objects.filter(code__startswith=f'FRN{annee}').order_by('-code').first()
            seq = (int(dernier.code[-4:]) + 1) if dernier else 1
            self.code = f'FRN{annee}{seq:04d}'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Fournisseur"
        ordering = ['nom']


class BesoinAchat(models.Model):
    STATUT_CHOICES = [
        ('brouillon',  'Brouillon'),
        ('soumis',     'Soumis'),
        ('en_cours',   'En cours de traitement'),
        ('satisfait',  'Satisfait'),
        ('annule',     'Annulé'),
    ]
    numero               = models.CharField(max_length=20, unique=True, blank=True)
    titre                = models.CharField(max_length=200)
    date_besoin_souhaite = models.DateField("Date de livraison souhaitée", null=True, blank=True)
    statut               = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    fiche_besoins        = models.ForeignKey(
        'stock.FicheBesoins', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='besoins_achats', verbose_name="Fiche de besoins liée"
    )
    notes                = models.TextField(blank=True)
    cree_par             = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='besoins_achats_crees')
    date_creation        = models.DateTimeField(auto_now_add=True)
    date_modification    = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.numero} — {self.titre}"

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = BesoinAchat.objects.filter(numero__startswith=f'BAC{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'BAC{annee}{seq:04d}'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Besoin d'achat"
        verbose_name_plural = "Besoins d'achat"
        ordering = ['-date_creation']


class LigneBesoin(models.Model):
    besoin      = models.ForeignKey(BesoinAchat, on_delete=models.CASCADE, related_name='lignes')
    produit     = models.ForeignKey('stock.Produit', on_delete=models.PROTECT, null=True, blank=True)
    designation = models.CharField("Désignation libre", max_length=250, blank=True)
    quantite    = models.DecimalField(max_digits=12, decimal_places=2)
    unite       = models.CharField(max_length=50, default='unité')
    notes       = models.CharField(max_length=300, blank=True)

    @property
    def libelle(self):
        if self.produit:
            return self.produit.nom
        return self.designation

    def __str__(self): return f"{self.libelle} × {self.quantite}"

    class Meta:
        verbose_name = "Ligne de besoin"


class Proforma(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente de validation'),
        ('valide',     'Validé'),
        ('rejete',     'Rejeté'),
    ]
    numero                = models.CharField(max_length=20, unique=True, blank=True)
    besoin                = models.ForeignKey(BesoinAchat, on_delete=models.PROTECT, related_name='proformas')
    fournisseur           = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name='proformas')
    date_reception        = models.DateField("Date de réception du document")
    reference_fournisseur = models.CharField("Réf. fournisseur", max_length=100, blank=True)
    montant_total         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fichier               = models.FileField("Document proforma", upload_to='achats/proformas/', null=True, blank=True)
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')
    notes                 = models.TextField(blank=True)
    notes_direction       = models.TextField("Observations direction", blank=True)
    soumis_par            = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='proformas_soumis')
    valide_par            = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='proformas_valides')
    date_validation       = models.DateTimeField(null=True, blank=True)
    date_creation         = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.numero} — {self.fournisseur.nom}"

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = Proforma.objects.filter(numero__startswith=f'PRF{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'PRF{annee}{seq:04d}'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Proforma"
        ordering = ['-date_creation']


class LigneProforma(models.Model):
    proforma      = models.ForeignKey(Proforma, on_delete=models.CASCADE, related_name='lignes')
    ligne_besoin  = models.ForeignKey(LigneBesoin, on_delete=models.SET_NULL, null=True, blank=True, related_name='lignes_proforma')
    designation   = models.CharField(max_length=250)
    quantite      = models.DecimalField(max_digits=12, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes         = models.CharField(max_length=300, blank=True)

    @property
    def montant(self):
        return self.quantite * self.prix_unitaire

    def __str__(self): return f"{self.designation} × {self.quantite}"

    class Meta:
        verbose_name = "Ligne de proforma"


class CommandeAchat(models.Model):
    STATUT_CHOICES = [
        ('brouillon',    'Brouillon'),
        ('envoyee',      'Envoyée'),
        ('en_livraison', 'En livraison'),
        ('recue',        'Reçue'),
        ('annulee',      'Annulée'),
    ]
    numero                = models.CharField(max_length=20, unique=True, blank=True)
    proforma              = models.OneToOneField(Proforma, on_delete=models.PROTECT, related_name='commande')
    fournisseur           = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name='commandes_achats')
    date_commande         = models.DateField(default=timezone.now)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    montant_total         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes                 = models.TextField(blank=True)
    cree_par              = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes_achats_crees')
    date_creation         = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.numero} — {self.fournisseur.nom}"

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = CommandeAchat.objects.filter(numero__startswith=f'CAC{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'CAC{annee}{seq:04d}'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Commande d'achat"
        verbose_name_plural = "Commandes d'achat"
        ordering = ['-date_creation']


class LigneCommandeAchat(models.Model):
    commande           = models.ForeignKey(CommandeAchat, on_delete=models.CASCADE, related_name='lignes')
    ligne_proforma     = models.ForeignKey(LigneProforma, on_delete=models.SET_NULL, null=True, blank=True)
    designation        = models.CharField(max_length=250)
    quantite_commandee = models.DecimalField(max_digits=12, decimal_places=2)
    prix_unitaire      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes              = models.CharField(max_length=300, blank=True)

    @property
    def montant(self):
        return self.quantite_commandee * self.prix_unitaire

    def __str__(self): return f"{self.designation} × {self.quantite_commandee}"

    class Meta:
        verbose_name = "Ligne de commande"


class ReceptionAchat(models.Model):
    STATUT_CHOICES = [
        ('conforme',     'Conforme'),
        ('partielle',    'Partielle'),
        ('non_conforme', 'Non conforme'),
    ]
    numero             = models.CharField(max_length=20, unique=True, blank=True)
    commande           = models.ForeignKey(CommandeAchat, on_delete=models.PROTECT, related_name='receptions')
    date_reception     = models.DateField(default=timezone.now)
    statut             = models.CharField(max_length=20, choices=STATUT_CHOICES, default='conforme')
    notes              = models.TextField(blank=True)
    receptionne_par    = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='receptions_achats')
    integre_en_stock   = models.BooleanField("Intégré en stock", default=False)
    date_integration   = models.DateTimeField("Date d'intégration stock", null=True, blank=True)
    integre_par        = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='receptions_integrees')
    date_creation      = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Réception {self.numero} — {self.commande.numero}"

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            dernier = ReceptionAchat.objects.filter(numero__startswith=f'REC{annee}').order_by('-numero').first()
            seq = (int(dernier.numero[-4:]) + 1) if dernier else 1
            self.numero = f'REC{annee}{seq:04d}'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Réception d'achat"
        verbose_name_plural = "Réceptions d'achat"
        ordering = ['-date_creation']


class LigneReceptionAchat(models.Model):
    reception       = models.ForeignKey(ReceptionAchat, on_delete=models.CASCADE, related_name='lignes')
    ligne_commande  = models.ForeignKey(LigneCommandeAchat, on_delete=models.PROTECT)
    quantite_recue  = models.DecimalField(max_digits=12, decimal_places=2)
    conforme        = models.BooleanField(default=True)
    numero_lot      = models.CharField("N° de lot", max_length=100, blank=True)
    date_peremption = models.DateField("Date de péremption", null=True, blank=True)
    notes           = models.CharField(max_length=300, blank=True)

    @property
    def ecart(self):
        return self.quantite_recue - self.ligne_commande.quantite_commandee

    def __str__(self): return f"{self.ligne_commande.designation} × {self.quantite_recue}"

    class Meta:
        verbose_name = "Ligne de réception"
