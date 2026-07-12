from django.db import models
from django.contrib.auth.models import User


class Acte(models.Model):
    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=300)
    categorie = models.CharField(max_length=100, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    actif = models.BooleanField(default=True)

    def __str__(self): return f"{self.code} - {self.libelle}"
    class Meta: verbose_name = "Acte médical"


class Facture(models.Model):
    STATUT = [('brouillon','Brouillon'),('emise','Émise'),('payee','Payée'),('annulee','Annulée')]
    TYPE = [('consultation','Consultation'),('soins','Soins'),('hospitalisation','Hospitalisation'),('pharmacie','Pharmacie'),('laboratoire','Laboratoire'),('imagerie','Imagerie'),('autre','Autre')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='factures')
    consultation = models.ForeignKey('consultations.Consultation', on_delete=models.SET_NULL, null=True, blank=True)
    hospitalisation = models.ForeignKey('hospitalisation.Hospitalisation', on_delete=models.SET_NULL, null=True, blank=True)
    rendez_vous = models.ForeignKey(
        'patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='factures', verbose_name='Rendez-vous',
    )
    ordonnance = models.ForeignKey(
        'consultations.Ordonnance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='factures', verbose_name='Ordonnance',
    )
    type_facture = models.CharField(max_length=20, choices=TYPE, default='consultation')
    date_emission = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateField(null=True, blank=True)
    montant_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_assurance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ticket_moderateur = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_paye = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon')
    notes = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            now = timezone.now()
            annee = now.year
            date_part = now.strftime('%y%m%d')
            count = Facture.objects.count() + 1
            numero = f"VTES/{annee}/{date_part}{count:04d}"
            while Facture.objects.filter(numero=numero).exists():
                count += 1
                numero = f"VTES/{annee}/{date_part}{count:04d}"
            self.numero = numero
        super().save(*args, **kwargs)

    @property
    def solde_restant(self):
        return self.montant_total - self.montant_paye

    def recalculer_total(self, save=True):
        """Recalcule montant_total en sommant montant_ligne de toutes les lignes.
        Idempotent : plusieurs appels successifs produisent le même résultat."""
        total = sum(ligne.montant_ligne for ligne in self.lignes.all())
        self.montant_total = round(total, 2)
        if save:
            self.save(update_fields=['montant_total'])
        return self.montant_total

    def __str__(self): return f"Facture {self.numero}"
    class Meta:
        verbose_name = "Facture"
        ordering = ['-date_emission']
        permissions = [
            ('can_valider_facture', 'Peut valider une facture (brouillon → émise)'),
        ]


class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    acte = models.ForeignKey(Acte, on_delete=models.SET_NULL, null=True, blank=True)
    medicament = models.ForeignKey('pharmacie.Medicament', on_delete=models.SET_NULL, null=True, blank=True)
    libelle = models.CharField(max_length=300)
    quantite = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    remise = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    @property
    def montant_ligne(self):
        return self.quantite * self.prix_unitaire * (1 - self.remise / 100)


class Paiement(models.Model):
    MODE = [('especes','Espèces'),('cheque','Chèque'),('mobile_money','Mobile Money'),('virement','Virement'),('assurance','Assurance'),('bon','Bon')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODE)
    reference = models.CharField(max_length=100, blank=True)
    date_paiement = models.DateTimeField(auto_now_add=True)
    recu_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            prefix = f"PAI{annee}"
            last = Paiement.objects.filter(numero__startswith=prefix).order_by('-pk').first()
            count = (int(last.numero[len(prefix):]) + 1) if last else 1
            self.numero = f"{prefix}{count:07d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Paiement {self.numero} - {self.montant} F"
    class Meta:
        verbose_name = "Paiement"
        ordering = ['-date_paiement']
