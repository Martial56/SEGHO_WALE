from django.db import models
from django.contrib.auth.models import User

from centres.models import ModeleCentre


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
    # Demande d'origine, quand le résultat revient du laboratoire par HPRIM :
    # c'est elle qui sait quels examens ont été prescrits, et par qui.
    demande = models.ForeignKey('DemandeExamen', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='analyses')
    # Examen auquel répond ce résultat (OBR 9.5 du message ORU) : une demande
    # NFS + Goutte épaisse revient en deux analyses, une par examen.
    code_examen = models.CharField(max_length=50, blank=True)
    # Commentaire du biologiste (segments C), imprimé sous l'examen sur le bulletin.
    conclusion = models.TextField(blank=True)
    # Médecin à prévenir à l'arrivée du résultat (prescripteur, à défaut le
    # médecin de la consultation) et moment où il l'a ouvert : tant que
    # `vu_le` est vide, le résultat est signalé dans sa cloche et en rouge sur
    # l'onglet « Résultats d'examens » de la consultation.
    destinataire = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='resultats_a_lire')
    vu_le = models.DateTimeField(null=True, blank=True)
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
            from core.numerotation import prochain_code
            self.numero = prochain_code(
                AnalyseLaboratoire.objects, 'numero', f'LAB{annee}', 6)
        super().save(*args, **kwargs)

    def __str__(self): return f"Analyse {self.numero} - {self.patient}"

    @property
    def ligne_demande(self):
        """La ligne de la demande à laquelle répond ce résultat, retrouvée par
        le code HPRIM de l'examen."""
        if not (self.demande_id and self.code_examen):
            return None
        for ligne in self.demande.lignes.all():
            if ligne.article_service and ligne.article_service.code_hprim == self.code_examen:
                return ligne
        return None

    @property
    def rubrique(self):
        """Rubrique du bulletin (HÉMATOLOGIE, BIOCHIMIE…) : le « type de test »
        de l'examen dans le catalogue des prestations."""
        ligne = self.ligne_demande
        if ligne and ligne.article_service and ligne.article_service.type_test_labo:
            return ligne.article_service.type_test_labo
        return 'autre'

    @property
    def libelle_examen(self):
        """Ce qui a été analysé, en clair. Les demandes se font depuis le
        catalogue des prestations, pas depuis TypeExamen : sans repli sur les
        lignes de la demande, la fiche affichait « None »."""
        if self.type_examen_id:
            return str(self.type_examen)
        ligne = self.ligne_demande
        if ligne:
            return ligne.libelle
        if self.demande_id:
            libelles = [l.libelle for l in self.demande.lignes.all() if l.libelle]
            if libelles:
                return ", ".join(libelles)
        return ", ".join(r.parametre for r in self.resultats.all()) or "—"

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

    @property
    def anormal(self):
        return self.interpretation in ('eleve', 'bas', 'critique')

    @property
    def normes(self):
        if self.valeur_normale_min and self.valeur_normale_max:
            return f"{self.valeur_normale_min} – {self.valeur_normale_max}"
        return self.valeur_normale_min or self.valeur_normale_max or ""

    class Meta: verbose_name = "Résultat d'analyse"


class DemandeExamen(ModeleCentre):
    # « Facturée » : la demande porte une facture non annulée, elle attend
    # d'être envoyée au laboratoire (posé par laboratoire.signals).
    STATUT = [
        ('brouillon', 'Brouillon'),
        ('facturee', 'Facturée'),
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
    medecin_prescripteur = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_examens')
    commentaire = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_creees')
    date_creation = models.DateTimeField(auto_now_add=True)
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    facture = models.ForeignKey('facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_examens')
    # Consultation (rendez-vous) d'où la demande a été faite : c'est par elle
    # que l'onglet « Résultats d'examens » de la consultation retrouve ses résultats.
    rendez_vous = models.ForeignKey('patients.RendezVous', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='demandes_examens')

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            from core.numerotation import prochain_code
            # all_objects : numero est unique tous centres confondus.
            self.numero = prochain_code(
                DemandeExamen.all_objects, 'numero', f'DEM{annee}', 6)
        super().save(*args, **kwargs)

    def __str__(self): return f"Demande {self.numero} - {self.patient}"

    #: Pas encore partie au laboratoire : on peut encore l'y envoyer.
    STATUTS_AVANT_ENVOI = ('brouillon', 'facturee')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Demande d'examen"
        ordering = ['-date_creation']


class LigneDemandeExamen(models.Model):
    demande = models.ForeignKey(DemandeExamen, on_delete=models.CASCADE, related_name='lignes')
    type_examen = models.ForeignKey(TypeExamen, on_delete=models.SET_NULL, null=True, blank=True)
    article_service = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lignes_demande_examen',
        verbose_name="Article de service",
        help_text="Article du catalogue Services (catégorie Examens biologiques) "
                   "sélectionné à la création de la demande ; permet de retrouver le "
                   "code HPRIM du laboratoire partenaire."
    )
    libelle = models.CharField(max_length=300, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    instructions = models.TextField(blank=True)
    # Qui a voulu cet examen. Une ligne ajoutée à la caisse n'a été demandée
    # par aucun médecin : quand le résultat reviendra, le laboratoire, le
    # prescripteur et le patient doivent pouvoir savoir d'où elle sort.
    #
    # Stocké plutôt que déduit : l'origine est un fait au moment de la
    # création et ne change jamais. La deviner à l'absence de `type_examen`
    # ou d'un lien tiendrait le temps que ces champs gardent leur usage.
    ORIGINE = [('medecin', 'Demandé par le médecin'),
               ('caisse', 'Ajouté à la caisse')]
    origine = models.CharField(max_length=10, choices=ORIGINE, default='medecin')

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
            from core.numerotation import prochain_code
            self.numero = prochain_code(
                ExamenImagerie.objects, 'numero', f'IMG{annee}', 6)
        super().save(*args, **kwargs)

    def __str__(self): return f"Imagerie {self.numero} - {self.patient}"
    class Meta: verbose_name = "Examen imagerie"


# =========================================================================== #
# Interopérabilité HPRIM Santé v2.4 (échange avec un logiciel de laboratoire)
# =========================================================================== #
class ConfigurationHPRIM(ModeleCentre):
    """Paramètres de connexion FTP et identités émetteur/récepteur.
    Une configuration appartient à UN centre ; seul WALE Yakro utilise
    aujourd'hui le laboratoire SYSLAM via HPRIM (un seul enregistrement actif
    par centre suffit — le plus récent actif de ce centre est utilisé)."""
    nom = models.CharField(max_length=100, default="Configuration HPRIM",
                           help_text="Libellé de cette configuration")
    actif = models.BooleanField(default=True)

    # Identités HPRIM (segment H)
    # Valeurs imposées par le laboratoire partenaire (SYSLAM) :
    # « ACCWAL~WALE Accueil Auto » en 7.5, « WALE~CMS WALE » en 7.10.
    emetteur_code = models.CharField(
        max_length=20, default="ACCWAL",
        help_text="Code émetteur — champ 7.5")
    emetteur_nom = models.CharField(max_length=40, default="WALE Accueil Auto")
    recepteur_code = models.CharField(max_length=20, default="WALE",
                                      help_text="Code du récepteur — champ 7.10")
    recepteur_nom = models.CharField(max_length=40, default="CMS WALE")
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

    class Meta(ModeleCentre.Meta):
        verbose_name = "Configuration HPRIM"
        verbose_name_plural = "Configurations HPRIM"

    @classmethod
    def active(cls, centre):
        """Config HPRIM active du CENTRE donné, ou None (ex. un centre sans
        SYSLAM). Interroge `all_objects` : cette résolution ne doit jamais
        dépendre du centre actif ambiant de la requête en cours, seulement du
        centre explicitement demandé (celui de la DemandeExamen)."""
        if centre is None:
            return None
        return cls.all_objects.filter(actif=True, centre=centre).order_by('-date_modification').first()


class EchangeHPRIM(ModeleCentre):
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

    class Meta(ModeleCentre.Meta):
        verbose_name = "Échange HPRIM"
        verbose_name_plural = "Échanges HPRIM"
        ordering = ['-date_creation']


class ErreurHPRIM(ModeleCentre):
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

    class Meta(ModeleCentre.Meta):
        verbose_name = "Erreur HPRIM"
        verbose_name_plural = "Erreurs HPRIM"
        ordering = ['-date_creation']
