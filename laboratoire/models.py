from django.db import models
from django.contrib.auth.models import User


class TypeExamen(models.Model):
    code = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=200)
    categorie = models.CharField(max_length=100, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delai_resultat_heures = models.IntegerField(default=24)
    def __str__(self): return self.nom
    class Meta: verbose_name = "Type d'examen"


class AnalyseLaboratoire(models.Model):
    STATUT = [('recu','Reçu'),('en_analyse','En analyse'),('resultat','Résultat'),('valide','Validé'),('envoye','Envoyé')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='analyses')
    examen_demande = models.OneToOneField('consultations.ExamenDemande', on_delete=models.SET_NULL, null=True, blank=True)
    type_examen = models.ForeignKey(TypeExamen, on_delete=models.SET_NULL, null=True)
    date_prelevement = models.DateTimeField(auto_now_add=True)
    date_resultat = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='recu')
    technicien = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='analyses_tech')
    validateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='analyses_val')
    commentaire = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = AnalyseLaboratoire.objects.filter(date_prelevement__year=annee).count() + 1
            self.numero = f"LAB{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Analyse {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Analyse laboratoire"
        ordering = ['-date_prelevement']


class ResultatAnalyse(models.Model):
    analyse = models.ForeignKey(AnalyseLaboratoire, on_delete=models.CASCADE, related_name='resultats')
    parametre = models.CharField(max_length=200)
    valeur = models.CharField(max_length=200)
    unite = models.CharField(max_length=50, blank=True)
    valeur_normale_min = models.CharField(max_length=100, blank=True)
    valeur_normale_max = models.CharField(max_length=100, blank=True)
    interpretation = models.CharField(max_length=20, choices=[('normal','Normal'),('eleve','Élevé'),('bas','Bas'),('critique','Critique')], blank=True)

    def __str__(self): return f"{self.parametre}: {self.valeur} {self.unite}"
    class Meta: verbose_name = "Résultat d'analyse"


class DemandeExamen(models.Model):
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('demande', 'Demandé'),
        ('accepte', 'Accepté'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
    ]
    TYPE_TEST = [
        ('hematologie', 'Hématologie'),
        ('biochimie', 'Biochimie'),
        ('bacteriologie', 'Bactériologie'),
        ('serologie', 'Sérologie'),
        ('parasitologie', 'Parasitologie'),
        ('pathologie', 'Pathologie'),
        ('imagerie', 'Imagerie'),
        ('autre', 'Autre'),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='demandes_examens')
    type_test = models.CharField(max_length=50, choices=TYPE_TEST, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='brouillon')
    date_prelevement = models.DateTimeField(null=True, blank=True)
    technicien = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_tech')
    commentaire = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_creees')
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    facture = models.ForeignKey('facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_examens')

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = DemandeExamen.objects.filter(date_creation__year=annee).count() + 1
            self.numero = f"DEM{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Demande {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Demande d'examen"
        ordering = ['-date_creation']


class LigneDemandeExamen(models.Model):
    demande = models.ForeignKey(DemandeExamen, on_delete=models.CASCADE, related_name='lignes')
    type_examen = models.ForeignKey(TypeExamen, on_delete=models.SET_NULL, null=True, blank=True)
    libelle = models.CharField(max_length=300, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    instructions = models.TextField(blank=True)

    def __str__(self): return f"{self.libelle or self.type_examen} — {self.demande.numero}"
    class Meta: verbose_name = "Ligne de demande d'examen"


class ExamenImagerie(models.Model):
    STATUT = [('recu','Reçu'),('en_cours','En cours'),('resultat','Résultat'),('valide','Validé')]
    TYPE = [('echographie','Échographie'),('radiographie','Radiographie'),('scanner','Scanner'),('irm','IRM'),('autre','Autre')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='imageries')
    examen_demande = models.OneToOneField('consultations.ExamenDemande', on_delete=models.SET_NULL, null=True, blank=True)
    type_imagerie = models.CharField(max_length=20, choices=TYPE)
    zone_examinee = models.CharField(max_length=200)
    date_examen = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='recu')
    compte_rendu = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    radiologue = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    image = models.FileField(upload_to='imagerie/', blank=True, null=True)
    urgent = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            count = ExamenImagerie.objects.filter(date_examen__year=annee).count() + 1
            self.numero = f"IMG{annee}{count:06d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"Imagerie {self.numero} - {self.patient}"
    class Meta: verbose_name = "Examen imagerie"


# =========================================================================== #
# Interopérabilité HPRIM Santé v2.4 (échange avec un logiciel de laboratoire)
# =========================================================================== #
class ConfigurationHPRIM(models.Model):
    """Paramètres de connexion FTP et identités émetteur/récepteur.
    Un seul enregistrement actif suffit (le plus récent actif est utilisé)."""
    nom = models.CharField(max_length=100, default="Configuration HPRIM",
                           help_text="Libellé de cette configuration")
    actif = models.BooleanField(default=True)

    # Identités HPRIM (segment H)
    emetteur_code = models.CharField(
        max_length=20, default="WALE",
        help_text="Code émetteur (ex. n° autorisation préfectorale) — champ 7.5")
    emetteur_nom = models.CharField(max_length=40, default="CMS WALE")
    recepteur_code = models.CharField(max_length=20, default="LABO",
                                      help_text="Code du laboratoire — champ 7.10")
    recepteur_nom = models.CharField(max_length=40, default="LABORATOIRE")
    type_liaison = models.CharField(
        max_length=1, default="L",
        choices=[("L", "Laboratoires"), ("C", "Clinique/hôpital"),
                 ("R", "Radiologie")],
        help_text="Table HPRIM 2 — champ 7.13")
    prefixe_fichier = models.CharField(
        max_length=4, default="WALE",
        help_text="Préfixe RADIX 50 des noms de fichiers (A-Z, 0-9)")

    # Connexion FTP — envoi des demandes (ORM)
    ftp_host = models.CharField(max_length=200, blank=True)
    ftp_port = models.IntegerField(default=21)
    ftp_user = models.CharField(max_length=100, blank=True)
    ftp_password = models.CharField(max_length=200, blank=True)
    ftp_tls = models.BooleanField(default=False, verbose_name="FTPS (TLS)")
    repertoire_envoi = models.CharField(
        max_length=300, blank=True,
        help_text="Dossier distant où déposer les demandes (ORM)")
    repertoire_reception = models.CharField(
        max_length=300, blank=True,
        help_text="Dossier distant où relever les résultats (ORU)")
    extension_temoin = models.CharField(max_length=10, default=".ok")

    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} ({'actif' if self.actif else 'inactif'})"

    class Meta:
        verbose_name = "Configuration HPRIM"
        verbose_name_plural = "Configurations HPRIM"

    @classmethod
    def active(cls):
        return cls.objects.filter(actif=True).order_by('-date_modification').first()


class EchangeHPRIM(models.Model):
    """Journal de chaque message HPRIM émis ou reçu (traçabilité)."""
    SENS = [("envoi", "Envoi (ORM)"), ("reception", "Réception (ORU)")]
    STATUT = [
        ("en_attente", "En attente"),
        ("transmis", "Transmis"),
        ("recu", "Reçu"),
        ("traite", "Traité"),
        ("erreur", "Erreur"),
    ]

    sens = models.CharField(max_length=15, choices=SENS)
    contexte = models.CharField(max_length=5, help_text="ORM / ORU")
    nom_fichier = models.CharField(max_length=20)
    demande = models.ForeignKey('DemandeExamen', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='echanges_hprim')
    statut = models.CharField(max_length=15, choices=STATUT, default="en_attente")
    contenu = models.TextField(blank=True, help_text="Message HPRIM brut")
    message_log = models.TextField(blank=True, verbose_name="Journal",
                                   help_text="Détails / erreurs")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_sens_display()} {self.nom_fichier} [{self.statut}]"

    class Meta:
        verbose_name = "Échange HPRIM"
        verbose_name_plural = "Échanges HPRIM"
        ordering = ['-date_creation']


class ErreurHPRIM(models.Model):
    """Erreur signalée par un message ERR reçu (§5.14), rattachée si possible
    à l'échange et à la demande d'origine."""
    GRAVITE = [
        ("T", "Rejet total du message"),
        ("P", "Rejet partiel du message"),
        ("I", "Pour information"),
    ]
    TYPE_ERREUR = [
        ("A", "Champ obligatoire absent"),
        ("I", "Donnée inconnue ou incohérente"),
        ("S", "Erreur de syntaxe"),
    ]

    echange = models.ForeignKey('EchangeHPRIM', on_delete=models.CASCADE,
                                related_name='erreurs')
    demande = models.ForeignKey('DemandeExamen', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='erreurs_hprim')
    nom_fichier_errone = models.CharField(max_length=20, blank=True,
                                          help_text="Fichier d'origine en erreur (25.3)")
    gravite = models.CharField(max_length=2, choices=GRAVITE, blank=True)
    type_erreur = models.CharField(max_length=2, choices=TYPE_ERREUR, blank=True)
    numero_ligne = models.CharField(max_length=10, blank=True)
    adresse_segment = models.CharField(max_length=200, blank=True,
                                       help_text="Segment fautif (25.7)")
    donnee_erronee = models.CharField(max_length=50, blank=True,
                                      help_text="N° HPRIM du champ (25.8)")
    valeur_erronee = models.TextField(blank=True)
    designation = models.TextField(blank=True, help_text="Description en clair (25.11)")
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_gravite_display()}] {self.designation[:60]}"

    class Meta:
        verbose_name = "Erreur HPRIM"
        verbose_name_plural = "Erreurs HPRIM"
        ordering = ['-date_creation']
