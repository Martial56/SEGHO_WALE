from django.db import models
from django.contrib.auth.models import User


class Caisse(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    solde_actuel = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    responsable = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actif = models.BooleanField(default=True)

    def __str__(self): return f"Caisse {self.nom}"
    class Meta: verbose_name = "Caisse"


class SessionCaisse(models.Model):
    STATUT = [('ouverte','Ouverte'),('fermee','Fermée')]
    caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='sessions')
    caissier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    date_ouverture = models.DateTimeField(auto_now_add=True)
    date_fermeture = models.DateTimeField(null=True, blank=True)
    solde_ouverture = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    solde_fermeture = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='ouverte')
    notes = models.TextField(blank=True)

    def __str__(self): return f"Session {self.caisse} - {self.date_ouverture.strftime('%d/%m/%Y')}"
    class Meta:
        verbose_name = "Session de caisse"
        ordering = ['-date_ouverture']


class TransactionCaisse(models.Model):
    TYPE = [('encaissement','Encaissement'),('decaissement','Décaissement'),('transfert','Transfert')]
    MODE = [('especes','Espèces'),('cheque','Chèque'),('mobile_money','Mobile Money'),('virement','Virement')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    session = models.ForeignKey(SessionCaisse, on_delete=models.CASCADE, related_name='transactions')
    type_transaction = models.CharField(max_length=20, choices=TYPE)
    mode_paiement = models.CharField(max_length=20, choices=MODE, default='especes')
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    reference = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    facture = models.ForeignKey('facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True)
    date_transaction = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = TransactionCaisse.objects.filter(date_transaction__year=annee).count() + 1
            self.numero = f"TRS{annee}{count:07d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.numero} - {self.montant} F"
    class Meta:
        verbose_name = "Transaction de caisse"
        ordering = ['-date_transaction']
