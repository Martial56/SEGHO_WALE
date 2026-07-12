from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE, SET_NULL
from datetime import date, time


class Fonction(models.Model):
    CATEGORIE_CHOICES = [
        ('direction',    'Direction & Administration'),
        ('medical',      'Corps Médical'),
        ('paramedical',  'Paramédical'),
        ('communautaire','Communautaire'),
        ('support',      'Support'),
    ]
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, blank=True, default='support')
    description = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta:
        db_table = 'ressources_humaines_fonction'
        ordering = ['categorie', 'nom']
        verbose_name = "Fonction"
        verbose_name_plural = "Fonctions"


class Grade(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom
    class Meta:
        db_table = 'ressources_humaines_grade'
        ordering = ['nom']
        verbose_name = "Grade"
        verbose_name_plural = "Grades"


class TypeContrat(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    droit_au_conge = models.BooleanField(
        default=True,
        verbose_name="Droit au congé",
        help_text="Décocher pour les vacataires, prestataires et autres contrats sans droit au congé."
    )

    def __str__(self): return self.nom
    class Meta:
        db_table = 'ressources_humaines_typecontrat'
        ordering = ['nom']
        verbose_name = "Type de contrat"
        verbose_name_plural = "Types de contrat"


class Nationalite(models.Model):
    nom = models.CharField(max_length=100)

    def __str__(self): return self.nom
    class Meta:
        db_table = 'ressources_humaines_nationalite'
        ordering = ['nom']
        verbose_name = "Nationalité"
        verbose_name_plural = "Nationalités"


class Employe(models.Model):
    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    STATUT_CHOICES = [
        ('actif', 'Actif'),
        ('suspendu', 'Suspendu'),
        ('quitte', 'Quitté'),
    ]
    SITUATION_CHOICES = [
        ('celibataire', 'Célibataire'),
        ('marie', 'Marié(e)'),
        ('divorce', 'Divorcé(e)'),
        ('veuf', 'Veuf/Veuve'),
    ]

    matricule = models.CharField(max_length=15, unique=True, blank=True)

    # Identité
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    sexe = models.CharField(max_length=1, choices=SEXE_CHOICES, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=150, blank=True)
    nationalite = models.ForeignKey(
        Nationalite, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employes'
    )
    situation_matrimoniale = models.CharField(max_length=20, choices=SITUATION_CHOICES, blank=True)
    nombre_enfants = models.PositiveSmallIntegerField(default=0)
    photo = models.ImageField(upload_to='employes/photos/', null=True, blank=True)

    # Contact
    telephone = models.CharField(max_length=20, blank=True)
    telephone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)

    # Affectation et contrat
    service = models.ForeignKey(
        'medecins.Service', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employes'
    )
    fonction = models.ForeignKey(
        Fonction, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employes'
    )
    grade = models.ForeignKey(
        Grade, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employes'
    )
    type_contrat = models.ForeignKey(
        TypeContrat, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employes'
    )
    date_embauche = models.DateField()
    date_fin_contrat = models.DateField(null=True, blank=True)
    salaire_base = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    date_depart = models.DateField(
        null=True, blank=True, verbose_name="Date de départ",
        help_text="Renseignée automatiquement lors du passage au statut « quitté ».",
    )

    # Identification pointage
    biometric_id = models.CharField(
        max_length=100, blank=True,
        verbose_name="Identifiant biométrique",
        help_text="Identifiant renseigné par le lecteur d'empreinte digitale."
    )

    notes = models.TextField(blank=True)

    user = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='employe_profile'
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.matricule:
            ini_nom    = self.nom[0].upper()     if self.nom     else 'X'
            ini_prenom = self.prenoms[0].upper() if self.prenoms else 'X'
            d = self.date_embauche
            if isinstance(d, str):
                from datetime import date as _date
                d = _date.fromisoformat(d)
            prefix = f'{d.year:04d}'
            max_seq = 0
            for m in Employe.objects.filter(matricule__regex=r'^\d{7}').values_list('matricule', flat=True):
                try:
                    n = int(m[4:7])
                except (ValueError, IndexError):
                    continue
                if n > max_seq:
                    max_seq = n
            seq = max_seq + 1
            self.matricule = f'{prefix}{seq:03d}{ini_nom}{ini_prenom}'
        super().save(*args, **kwargs)

    @property
    def nom_complet(self):
        return f"{self.nom} {self.prenoms}"

    @property
    def initiales(self):
        parts = []
        if self.nom:
            parts.append(self.nom[0].upper())
        if self.prenoms:
            parts.append(self.prenoms[0].upper())
        return ''.join(parts[:2]) or '?'

    @property
    def age(self):
        if not self.date_naissance:
            return None
        today = date.today()
        return today.year - self.date_naissance.year - (
            (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
        )

    @property
    def anciennete(self):
        if not self.date_embauche:
            return {'annees': 0, 'mois': 0, 'label': '—'}
        today = date.today()
        d = self.date_embauche
        if isinstance(d, str):
            d = date.fromisoformat(d)
        years = today.year - d.year
        months = today.month - d.month
        if months < 0:
            years -= 1
            months += 12
        if years > 0:
            label = f"{years} an{'s' if years > 1 else ''}{f' {months} mois' if months else ''}"
        else:
            label = f"{months} mois" if months else "< 1 mois"
        return {'annees': years, 'mois': months, 'label': label}

    @property
    def docs_manquants(self):
        from .models import DOCS_OBLIGATOIRES
        existants = set(self.documents.values_list('type_document', flat=True))
        return [d for d in DOCS_OBLIGATOIRES if d not in existants]

    def __str__(self):
        return f"{self.nom} {self.prenoms} ({self.matricule})"

    class Meta:
        db_table = 'ressources_humaines_employe'
        ordering = ['nom', 'prenoms']
        verbose_name = "Employé"
        verbose_name_plural = "Employés"


TYPE_DOC_CHOICES = [
    ('cni',        "Carte Nationale d'Identité"),
    ('passeport',  'Passeport'),
    ('diplome',    'Diplôme / Attestation'),
    ('contrat',    'Contrat de travail'),
    ('certificat', 'Certificat médical'),
    ('photo',      "Photo d'identité"),
    ('autre',      'Autre document'),
]


class DocumentEmploye(models.Model):
    employe         = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='documents')
    type_document   = models.CharField(max_length=20, choices=TYPE_DOC_CHOICES, default='autre')
    titre           = models.CharField(max_length=200)
    fichier         = models.FileField(upload_to='employes/documents/%Y/')
    date_expiration = models.DateField(null=True, blank=True)
    date_ajout      = models.DateTimeField(auto_now_add=True)
    ajoute_par      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes           = models.TextField(blank=True)

    def __str__(self):
        return f"{self.employe.nom} — {self.titre}"

    @property
    def extension(self):
        name = self.fichier.name if self.fichier else ''
        return name.rsplit('.', 1)[-1].lower() if '.' in name else ''

    @property
    def is_image(self):
        return self.extension in ('jpg', 'jpeg', 'png', 'gif', 'webp')

    @property
    def is_pdf(self):
        return self.extension == 'pdf'

    class Meta:
        db_table = 'ressources_humaines_documentemploye'
        ordering = ['-date_ajout']
        verbose_name = "Document"
        verbose_name_plural = "Documents"


class AlerteDocument(models.Model):
    ECHEANCE_CHOICES = [('2_mois', '2 mois'), ('1_mois', '1 mois')]
    document        = models.ForeignKey(DocumentEmploye, on_delete=models.CASCADE, related_name='alertes')
    echeance        = models.CharField(max_length=10, choices=ECHEANCE_CHOICES)
    date_expiration = models.DateField()
    lue             = models.BooleanField(default=False)
    cree_le         = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ressources_humaines_alertedocument'
        unique_together = [('document', 'echeance')]
        ordering = ['date_expiration']
        verbose_name = "Alerte document"
        verbose_name_plural = "Alertes documents"

    @property
    def jours_restants(self):
        return (self.date_expiration - date.today()).days


class InfoSupplementaire(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='infos_supp')
    cle     = models.CharField(max_length=100)
    valeur  = models.TextField()
    ordre   = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.employe.nom} — {self.cle}"

    class Meta:
        db_table = 'ressources_humaines_infosupplementaire'
        ordering = ['ordre', 'cle']
        verbose_name = "Information supplémentaire"
        verbose_name_plural = "Informations supplémentaires"


DOCS_OBLIGATOIRES = ['cni', 'contrat', 'diplome']


class HistoriqueEmploye(models.Model):
    TYPE_CHOICES = [
        ('creation',  'Création'),
        ('statut',    'Changement de statut'),
        ('salaire',   'Changement de salaire'),
        ('service',   'Changement de service'),
        ('contrat',   'Renouvellement de contrat'),
        ('autre',     'Modification'),
    ]
    employe         = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='historique')
    type_changement = models.CharField(max_length=20, choices=TYPE_CHOICES)
    ancienne_valeur = models.CharField(max_length=300, blank=True)
    nouvelle_valeur = models.CharField(max_length=300, blank=True)
    note            = models.CharField(max_length=300, blank=True)
    date            = models.DateTimeField(auto_now_add=True)
    fait_par        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'ressources_humaines_historiqueemploye'
        ordering = ['-date']
        verbose_name = "Historique employé"
        verbose_name_plural = "Historique employés"

    def __str__(self):
        return f"{self.employe} — {self.get_type_changement_display()} — {self.date:%d/%m/%Y}"


class AlerteContrat(models.Model):
    ECHEANCE_CHOICES = [
        ('2_mois', '2 mois'),
        ('1_mois', '1 mois'),
    ]
    employe          = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='alertes_contrat')
    echeance         = models.CharField(max_length=10, choices=ECHEANCE_CHOICES)
    date_fin_contrat = models.DateField()
    lue              = models.BooleanField(default=False)
    cree_le          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ressources_humaines_alertecontrat'
        unique_together = [('employe', 'echeance')]
        ordering = ['-cree_le']
        verbose_name = "Alerte contrat"
        verbose_name_plural = "Alertes contrat"

    def __str__(self):
        return f"Alerte {self.echeance} — {self.employe}"

    @property
    def jours_restants(self):
        return (self.date_fin_contrat - date.today()).days


# ── Conservés pour le futur module Congés / Présence ─────────────────────────

class Conge(models.Model):
    TYPE = [
        ('annuel',          'Congé annuel'),
        ('maladie',         'Congé maladie'),
        ('maternite',       'Congé maternité'),
        ('paternite',       'Congé paternité'),
        ('exceptionnel',    'Congé exceptionnel'),
        ('mariage_employe', 'Mariage (employé)'),
        ('mariage_enfant',  'Mariage (enfant)'),
        ('deces_conjoint',  'Décès conjoint'),
        ('deces_enfant',    'Décès enfant'),
        ('deces_parent',    'Décès parent/beau-parent'),
        ('deces_frere_soeur','Décès frère/sœur'),
        ('naissance_enfant','Naissance enfant (père)'),
        ('sans_solde',      'Congé sans solde'),
    ]
    STATUT = [
        ('approuve',        'À venir'),
        ('en_cours',        'En cours'),
        ('termine',         'Terminé'),
        ('refuse',          'Annulé'),
        # Conservés pour compatibilité données existantes
        ('demande',         'Demandé'),
        ('valide_service',  'Validé service'),
    ]
    employe      = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='conges')
    type_conge   = models.CharField(max_length=20, choices=TYPE)
    date_debut   = models.DateField()
    date_fin     = models.DateField()
    motif        = models.TextField(blank=True)
    statut       = models.CharField(max_length=20, choices=STATUT, default='approuve')
    nb_jours_ouvres      = models.PositiveSmallIntegerField(default=0, help_text="Jours ouvrés décomptés du solde")
    approuve_par         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conges_approuves')
    date_demande         = models.DateTimeField(auto_now_add=True)
    date_approbation     = models.DateTimeField(null=True, blank=True)
    commentaire_rh       = models.TextField(blank=True)
    # Validation service
    valide_par_service        = models.ForeignKey(User, null=True, blank=True, related_name='conges_valides_service', on_delete=SET_NULL)
    date_validation_service   = models.DateTimeField(null=True, blank=True)
    chef_service_commentaire  = models.TextField(blank=True)
    # Congés fractionnés (Art. 25.7 CODI)
    conge_parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=SET_NULL,
        related_name='fragments',
        verbose_name="Congé parent (fractionné)",
    )

    @property
    def duree(self):
        return (self.date_fin - self.date_debut).days + 1

    @property
    def statut_couleur(self):
        return {
            'demande':        'amber',
            'valide_service': 'blue',
            'approuve':       'green',
            'refuse':         'red',
            'en_cours':       'blue',
            'termine':        'gray',
        }.get(self.statut, 'gray')

    def __str__(self): return f"Congé {self.employe} - {self.date_debut}"

    class Meta:
        db_table = 'ressources_humaines_conge'
        verbose_name = "Congé"
        verbose_name_plural = "Congés"
        ordering = ['-date_demande']


class HistoriqueConge(models.Model):
    ACTION = [
        ('soumis',        'Demande soumise'),
        ('valide_service','Validé par le service'),
        ('approuve',      'Approuvé'),
        ('refuse',        'Refusé'),
        ('annule',        'Annulé'),
        ('mis_en_cours',       'Mis en cours'),
        ('termine',            'Terminé'),
        ('prolonge',           'Prolongé'),
        ('absence_injustifiee','Absence non justifiée'),
    ]
    conge       = models.ForeignKey(Conge, on_delete=CASCADE, related_name='historique')
    action      = models.CharField(max_length=20, choices=ACTION)
    fait_par    = models.ForeignKey(User, null=True, blank=True, on_delete=SET_NULL)
    date        = models.DateTimeField(auto_now_add=True)
    commentaire = models.TextField(blank=True)

    def __str__(self):
        return f"{self.conge} — {self.get_action_display()} — {self.date:%d/%m/%Y}"

    class Meta:
        db_table = 'ressources_humaines_historiqueconge'
        ordering = ['-date']
        verbose_name = "Historique congé"
        verbose_name_plural = "Historique congés"


class NotificationConge(models.Model):
    TYPE = [
        ('nouvelle_demande', 'Nouvelle demande'),
        ('approuve',         'Approuvé'),
        ('refuse',           'Refusé'),
        ('valide_service',   'Validé service'),
        ('annule',           'Annulé'),
    ]
    destinataire = models.ForeignKey(User, on_delete=CASCADE, related_name='notifs_conge')
    conge        = models.ForeignKey(Conge, on_delete=CASCADE, related_name='notifications')
    type_notif   = models.CharField(max_length=20, choices=TYPE)
    message      = models.TextField()
    lue          = models.BooleanField(default=False)
    cree_le      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notif {self.destinataire} — {self.get_type_notif_display()}"

    class Meta:
        db_table = 'ressources_humaines_notificationconge'
        ordering = ['-cree_le']
        verbose_name = "Notification congé"
        verbose_name_plural = "Notifications congés"


class SoldeConge(models.Model):
    employe        = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='soldes_conge')
    annee          = models.PositiveSmallIntegerField()
    quota          = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    jours_pris     = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    jours_reporter = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    note           = models.TextField(blank=True)
    mis_a_jour_le  = models.DateTimeField(auto_now=True)

    @property
    def solde(self):
        return float(self.quota) + float(self.jours_reporter) - float(self.jours_pris)

    def __str__(self):
        return f"Solde {self.employe} — {self.annee}"

    class Meta:
        db_table = 'ressources_humaines_soldeconge'
        unique_together = ['employe', 'annee']
        ordering = ['-annee']
        verbose_name = "Solde de congé"
        verbose_name_plural = "Soldes de congé"


class Presence(models.Model):
    employe              = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='presences')
    date                 = models.DateField()
    # Sessions horaires (matin + soir)
    heure_arrivee_matin  = models.TimeField(null=True, blank=True, verbose_name="Arrivée matin")
    heure_depart_matin   = models.TimeField(null=True, blank=True, verbose_name="Départ matin")
    heure_arrivee_soir   = models.TimeField(null=True, blank=True, verbose_name="Arrivée soir")
    heure_depart_soir    = models.TimeField(null=True, blank=True, verbose_name="Départ soir")
    present              = models.BooleanField(default=True)
    permanence           = models.BooleanField(default=False, verbose_name="Permanence 8h–15h")
    motif_absence        = models.CharField(max_length=200, blank=True)
    remarques            = models.CharField(max_length=300, blank=True)
    # Verrouillage kiosk : True = heure enregistrée par pointage, non modifiable manuellement
    am_in_locked         = models.BooleanField(default=False)
    am_out_locked        = models.BooleanField(default=False)
    pm_in_locked         = models.BooleanField(default=False)
    pm_out_locked        = models.BooleanField(default=False)
    # Audit
    modifie_par          = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='presences_modifiees', verbose_name="Modifié par")
    modifie_le           = models.DateTimeField(null=True, blank=True, verbose_name="Modifié le")

    def __str__(self): return f"Présence {self.employe} - {self.date}"

    @property
    def duree_matin(self):
        """Durée session matin en minutes."""
        if self.heure_arrivee_matin and self.heure_depart_matin:
            from datetime import datetime, date as _date
            d = _date.today()
            dt1 = datetime.combine(d, self.heure_arrivee_matin)
            dt2 = datetime.combine(d, self.heure_depart_matin)
            diff = (dt2 - dt1).seconds // 60
            return diff if diff > 0 else 0
        return None

    @property
    def duree_soir(self):
        """Durée session soir en minutes."""
        if self.heure_arrivee_soir and self.heure_depart_soir:
            from datetime import datetime, date as _date
            d = _date.today()
            dt1 = datetime.combine(d, self.heure_arrivee_soir)
            dt2 = datetime.combine(d, self.heure_depart_soir)
            diff = (dt2 - dt1).seconds // 60
            return diff if diff > 0 else 0
        return None

    @property
    def duree_totale(self):
        """Durée totale journalière en minutes.
        Pour les permanences : de arrivée_matin à départ_soir."""
        if self.permanence:
            if self.heure_arrivee_matin and self.heure_depart_soir:
                from datetime import datetime as _dt
                d = self.date
                dt1 = _dt.combine(d, self.heure_arrivee_matin)
                dt2 = _dt.combine(d, self.heure_depart_soir)
                diff = int((dt2 - dt1).total_seconds() // 60)
                return diff if diff > 0 else 0
            return None
        m = self.duree_matin or 0
        s = self.duree_soir or 0
        return m + s if (m or s) else None

    @property
    def retard_matin_min(self):
        """Retard à l'arrivée — référence 08:00, tolérance 15 min."""
        if not self.heure_arrivee_matin:
            return 0
        if self.heure_arrivee_matin <= time(8, 15):
            return 0
        from datetime import datetime as _dt
        ref = _dt.combine(self.date, time(8, 0))
        arr = _dt.combine(self.date, self.heure_arrivee_matin)
        return int((arr - ref).total_seconds() // 60)

    @property
    def retard_soir_min(self):
        """Retard à la session soir — référence 15:00, tolérance 15 min.
        Pour les permanences ce champ n'est pas utilisé (ils n'ont pas de session soir)."""
        if self.permanence:
            return 0
        if self.date.weekday() >= 5 or not self.heure_arrivee_soir:
            return 0
        if self.heure_arrivee_soir <= time(15, 15):
            return 0
        from datetime import datetime as _dt
        ref = _dt.combine(self.date, time(15, 0))
        arr = _dt.combine(self.date, self.heure_arrivee_soir)
        return int((arr - ref).total_seconds() // 60)

    @property
    def depart_anticipe_min(self):
        """Départ avant 14h45 pour les employés de permanence (référence 15:00)."""
        if not self.permanence:
            return 0
        if not self.heure_depart_soir:
            return 0
        if self.heure_depart_soir >= time(14, 45):
            return 0
        from datetime import datetime as _dt
        ref = _dt.combine(self.date, time(15, 0))
        dep = _dt.combine(self.date, self.heure_depart_soir)
        return int((ref - dep).total_seconds() // 60)

    class Meta:
        db_table = 'ressources_humaines_presence'
        verbose_name = "Présence"
        unique_together = ['employe', 'date']
        ordering = ['-date']


class JourFerie(models.Model):
    date        = models.DateField(unique=True, verbose_name="Date")
    description = models.CharField(max_length=100, verbose_name="Désignation")

    def __str__(self): return f"{self.description} – {self.date:%d/%m/%Y}"

    class Meta:
        db_table            = 'ressources_humaines_jourferie'
        ordering            = ['date']
        verbose_name        = 'Jour férié'
        verbose_name_plural = 'Jours fériés'


class CredentialBiometrique(models.Model):
    """Credential WebAuthn (empreinte digitale) associé à un employé."""
    employe       = models.ForeignKey(
        Employe, on_delete=models.CASCADE, related_name='credentials_bio'
    )
    credential_id = models.TextField(unique=True, verbose_name="ID credential (base64url)")
    public_key    = models.TextField(verbose_name="Clé publique (base64url)")
    sign_count    = models.PositiveIntegerField(default=0)
    aaguid        = models.CharField(max_length=100, blank=True)
    device_name   = models.CharField(max_length=100, blank=True, verbose_name="Appareil")
    created_at    = models.DateTimeField(auto_now_add=True)
    last_used     = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Credential biométrique'
        verbose_name_plural = 'Credentials biométriques'
        ordering            = ['-created_at']

    def __str__(self):
        return f"Biométrie – {self.employe} – {self.device_name or self.credential_id[:12]}"
