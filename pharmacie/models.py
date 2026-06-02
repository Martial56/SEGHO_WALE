from django.db import models
from django.contrib.auth.models import User


class CategorieMedicament(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Catégorie médicament"


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    actif = models.BooleanField(default=True)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Fournisseur"


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
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True)
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
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True)
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
            count = CommandePharmacies.objects.filter(date_commande__year=annee).count() + 1
            self.numero = f"CMD{annee}{count:05d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Commande {self.numero}"
    class Meta: verbose_name = "Commande pharmacie"
