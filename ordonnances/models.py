from django.db import models
from django.utils import timezone


class Maladie(models.Model):
    nom = models.CharField(max_length=300, verbose_name="Nom de la maladie")
    code = models.CharField(max_length=20, blank=True, verbose_name="Code CIM-10")

    def __str__(self):
        return f"{self.code} — {self.nom}" if self.code else self.nom

    class Meta:
        verbose_name = "Maladie"
        verbose_name_plural = "Maladies"
        ordering = ['nom']


class GroupeMedicaments(models.Model):
    nom = models.CharField(max_length=300, verbose_name="Nom du groupe")
    medecin = models.ForeignKey(
        'medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Docteur"
    )
    maladie = models.ForeignKey(
        'Maladie', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Maladie"
    )
    limite = models.IntegerField(default=0, verbose_name="Limite")

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Groupe de médicaments"
        verbose_name_plural = "Groupes de médicaments"
        ordering = ['nom']


class LigneGroupeMedicaments(models.Model):
    groupe = models.ForeignKey(
        GroupeMedicaments, on_delete=models.CASCADE, related_name='lignes',
        verbose_name="Groupe"
    )
    medicament = models.ForeignKey(
        'pharmacie.Medicament', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Nom du médicament"
    )
    medicament_libre = models.CharField(max_length=200, blank=True, verbose_name="Médicament (libre)")
    autorise = models.BooleanField(default=True, verbose_name="Autorisé")
    frequence_posologique = models.CharField(max_length=200, blank=True, verbose_name="Fréquence posologique")
    dosage = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Dosage")
    unite_dosage = models.CharField(max_length=100, blank=True, verbose_name="Unité de dosage")
    qte_par_jour = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Qté par jour")
    jours = models.IntegerField(null=True, blank=True, verbose_name="Jours")
    commentaire = models.CharField(max_length=500, blank=True, verbose_name="Commentaire")

    @property
    def qte_totale(self):
        if self.qte_par_jour and self.jours:
            return self.qte_par_jour * self.jours
        return None

    def __str__(self):
        nom = str(self.medicament) if self.medicament else self.medicament_libre
        return f"{nom} — {self.groupe.nom}"

    class Meta:
        verbose_name = "Ligne de groupe de médicaments"
        verbose_name_plural = "Lignes de groupe de médicaments"


class Ordonnance(models.Model):
    STATUT = [('brouillon', 'Brouillon'), ('prescrit', 'Prescrit')]
    TYPE = [('interne', 'Ordonnance interne'), ('externe', 'Ordonnance externe')]

    numero = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Numéro")
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordonnances', verbose_name="Patient"
    )
    medecin = models.ForeignKey(
        'medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordonnances', verbose_name="Docteur prescripteur"
    )
    consultation = models.ForeignKey(
        'consultations.Consultation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordonnances', verbose_name="Consultation"
    )
    groupe_medicaments = models.ForeignKey(
        GroupeMedicaments, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Groupe de médicaments"
    )
    ancienne_ordonnance = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Ancienne ordonnance"
    )
    maladie = models.ForeignKey(
        'Maladie', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Maladie"
    )
    date_ordonnance = models.DateTimeField(default=timezone.now, verbose_name="Date d'ordonnance")
    avertissement_grossesse = models.BooleanField(default=False, verbose_name="Avertissement de grossesse")
    type_ordonnance = models.CharField(max_length=20, choices=TYPE, default='interne', verbose_name="Type d'ordonnance")
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon', verbose_name="Statut")
    notes = models.TextField(blank=True, verbose_name="Notes d'ordonnance")

    # Informations générales
    rendez_vous = models.ForeignKey(
        'patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Rendez-vous"
    )
    facture = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Facture"
    )
    cueillettes = models.CharField(max_length=300, blank=True, verbose_name="Cueillettes")
    livre = models.BooleanField(default=False, verbose_name="Livré")
    hospitalisation = models.ForeignKey(
        'hospitalisation.Hospitalisation', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Hospitalisation"
    )
    police_assurance = models.ForeignKey(
        'patients.Assurance', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Police d'assurance"
    )
    compagnie_assurance = models.CharField(max_length=200, blank=True, verbose_name="Compagnie d'assurance")
    reclamation = models.CharField(max_length=300, blank=True, verbose_name="Réclamation")

    def save(self, *args, **kwargs):
        if not self.numero:
            annee = timezone.now().year
            count = Ordonnance.objects.filter(date_ordonnance__year=annee).count() + 1
            self.numero = f"ORD{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Ordonnance {self.numero}"
    class Meta:
        verbose_name = "Ordonnance"
        ordering = ['-date_ordonnance']


class LigneOrdonnance(models.Model):
    ordonnance = models.ForeignKey(Ordonnance, on_delete=models.CASCADE, related_name='lignes')
    medicament = models.ForeignKey(
        'pharmacie.Medicament', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Nom du médicament"
    )
    medicament_libre = models.CharField(max_length=200, blank=True, verbose_name="Médicament (saisie libre)")
    quantite = models.DecimalField(max_digits=8, decimal_places=2, default=1, verbose_name="Quantité")
    unite_dosage = models.CharField(max_length=100, blank=True, verbose_name="Unité de dosage")
    qte_par_jour = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Qté par jour")
    jours = models.IntegerField(null=True, blank=True, verbose_name="Jours")
    commentaire = models.CharField(max_length=500, blank=True, verbose_name="Commentaire")

    @property
    def qte_totale(self):
        if self.qte_par_jour and self.jours:
            return self.qte_par_jour * self.jours
        return None

    def __str__(self):
        nom = str(self.medicament) if self.medicament else self.medicament_libre
        return f"{nom} — {self.ordonnance.numero}"

    class Meta:
        verbose_name = "Ligne d'ordonnance"
        verbose_name_plural = "Lignes d'ordonnance"
