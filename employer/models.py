from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE, SET_NULL
from datetime import date, time


# ══════════════════════════════════════════════════════════════════════════════
# DONNÉES DE RÉFÉRENCE RH
# (anciennement dans utilisateur — déplacé ici car géré depuis employer/config)
# ══════════════════════════════════════════════════════════════════════════════

class Specialite(models.Model):
    nom         = models.CharField(max_length=100)
    code        = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'utilisateur_specialite'   # même table, zéro migration BDD
        verbose_name     = "Spécialité"
        ordering         = ['nom']


class Diplome(models.Model):
    titre       = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self): return self.titre

    class Meta:
        db_table         = 'utilisateur_diplome'
        verbose_name     = "Diplôme"
        verbose_name_plural = "Diplômes"
        ordering         = ['titre']


class Departement(models.Model):
    nom         = models.CharField(max_length=100)
    code        = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    actif       = models.BooleanField(default=True)

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'utilisateur_departement'
        verbose_name     = "Département"
        verbose_name_plural = "Départements"
        ordering         = ['nom']


class Etiquette(models.Model):
    nom     = models.CharField(max_length=50, unique=True)
    couleur = models.CharField(max_length=7, blank=True, default='#0ea5e9')

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'utilisateur_etiquette'
        verbose_name     = "Étiquette"
        verbose_name_plural = "Étiquettes"
        ordering         = ['nom']


# ══════════════════════════════════════════════════════════════════════════════
# DONNÉES RH — GRILLES
# ══════════════════════════════════════════════════════════════════════════════

class Fonction(models.Model):
    nom         = models.CharField(max_length=100)
    code        = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'employes_fonction'
        ordering         = ['nom']
        verbose_name     = "Fonction"
        verbose_name_plural = "Fonctions"


class Grade(models.Model):
    nom         = models.CharField(max_length=100)
    code        = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'employes_grade'
        ordering         = ['nom']
        verbose_name     = "Grade"
        verbose_name_plural = "Grades"


class TypeContrat(models.Model):
    nom           = models.CharField(max_length=100)
    description   = models.TextField(blank=True)
    droit_au_conge = models.BooleanField(
        default=True,
        verbose_name="Droit au congé",
        help_text="Décocher pour les vacataires, prestataires et autres contrats sans droit au congé."
    )

    def __str__(self): return self.nom

    class Meta:
        db_table         = 'employes_typecontrat'
        ordering         = ['nom']
        verbose_name     = "Type de contrat"
        verbose_name_plural = "Types de contrat"


# ══════════════════════════════════════════════════════════════════════════════
# EMPLOYÉ — modèle unifié (RH + profil médical)
# ══════════════════════════════════════════════════════════════════════════════

class Employe(models.Model):
    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    TITRE_CHOICES = [
        ('', '—'), ('dr', 'Dr'), ('pr', 'Pr'),
        ('m', 'M.'), ('mme', 'Mme'), ('prof', 'Prof.'),
    ]
    STATUT_CHOICES = [
        ('actif',    'Actif'),
        ('suspendu', 'Suspendu'),
        ('quitte',   'Quitté'),
    ]
    SITUATION_CHOICES = [
        ('celibataire', 'Célibataire'),
        ('marie',       'Marié(e)'),
        ('divorce',     'Divorcé(e)'),
        ('veuf',        'Veuf/Veuve'),
    ]

    # ── Identifiant ──────────────────────────────────────────────────────────
    matricule    = models.CharField(max_length=15, unique=True, blank=True)
    numero_ordre = models.PositiveIntegerField(null=True, blank=True, verbose_name="N° d'ordre")

    # ── Identité ─────────────────────────────────────────────────────────────
    titre        = models.CharField(max_length=10, blank=True, choices=TITRE_CHOICES, verbose_name='Titre')
    nom          = models.CharField(max_length=100)
    prenoms      = models.CharField(max_length=200, blank=True)
    sexe         = models.CharField(max_length=1, choices=SEXE_CHOICES, blank=True)
    date_naissance    = models.DateField(null=True, blank=True)
    lieu_naissance    = models.CharField(max_length=150, blank=True)
    nationalite       = models.CharField(max_length=50, blank=True, default='Ivoirienne')
    situation_matrimoniale = models.CharField(max_length=20, choices=SITUATION_CHOICES, blank=True)
    nombre_enfants    = models.PositiveSmallIntegerField(default=0)
    photo        = models.ImageField(upload_to='employes/photos/', null=True, blank=True)
    signature    = models.ImageField(upload_to='employes/signatures/', null=True, blank=True, verbose_name='Signature')

    # ── Contact ───────────────────────────────────────────────────────────────
    telephone  = models.CharField(max_length=20, blank=True)
    telephone2 = models.CharField(max_length=20, blank=True)
    email      = models.EmailField(blank=True)
    adresse    = models.TextField(blank=True, verbose_name="Lieu d'habitation")

    # ── Profil médical ────────────────────────────────────────────────────────
    est_medecin         = models.BooleanField(default=False, verbose_name='Est Médecin/Docteur')
    est_referent        = models.BooleanField(default=False, verbose_name='Est Médecin Référent')
    specialite          = models.ForeignKey(
        Specialite, on_delete=models.SET_NULL, null=True, blank=True, related_name='employes_medecins'
    )
    ordre_medecin       = models.CharField(max_length=50, blank=True, verbose_name="N° d'ordre médecin")
    duree_consultation  = models.PositiveSmallIntegerField(default=15, verbose_name='Durée consultation (min)')
    chirurgien_principal = models.BooleanField(default=False)
    taux_honoraire      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_consultation = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Service de consultation'
    )
    service_suivi       = models.ForeignKey(
        'services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Service de suivi'
    )

    # ── Affectation RH ────────────────────────────────────────────────────────
    services     = models.ManyToManyField(
        Departement, blank=True, related_name='employes_rh'
    )
    fonction     = models.ForeignKey(Fonction,    on_delete=SET_NULL, null=True, blank=True, related_name='employes')
    grade        = models.ForeignKey(Grade,       on_delete=SET_NULL, null=True, blank=True, related_name='employes')
    type_contrat = models.ForeignKey(TypeContrat, on_delete=SET_NULL, null=True, blank=True, related_name='employes')
    date_embauche     = models.DateField(null=True, blank=True)
    date_fin_contrat  = models.DateField(null=True, blank=True)
    salaire_base      = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    etablissement     = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    langue            = models.CharField(max_length=50, blank=True, default='Français', verbose_name='Langue')
    statut       = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')

    # ── Notes ────────────────────────────────────────────────────────────────
    notes         = models.TextField(blank=True)
    notes_internes = models.TextField(blank=True, verbose_name='Notes internes')

    # ── Compte utilisateur ────────────────────────────────────────────────────
    user = models.OneToOneField(
        User, on_delete=SET_NULL, null=True, blank=True, related_name='employe_profile'
    )

    cree_le    = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    # ── Save auto-matricule ───────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        if not self.matricule and self.date_embauche:
            ini_nom    = self.nom[0].upper()     if self.nom     else 'X'
            ini_prenom = self.prenoms[0].upper() if self.prenoms else 'X'
            d = self.date_embauche
            if isinstance(d, str):
                from datetime import date as _date
                d = _date.fromisoformat(d)
            annee    = d.year
            year_str = str(annee)
            if self.numero_ordre:
                seq = self.numero_ordre
            else:
                last = Employe.objects.filter(
                    matricule__startswith=year_str
                ).order_by('matricule').last()
                seq = 1
                if last:
                    try:
                        seq = int(last.matricule[4:8]) + 1
                    except (ValueError, IndexError):
                        seq = 1
                self.numero_ordre = seq
            self.matricule = f'{annee}{seq:04d}{ini_nom}{ini_prenom}'
        super().save(*args, **kwargs)

    # ── Propriétés ────────────────────────────────────────────────────────────
    @property
    def nom_complet(self):
        return f"{self.nom} {self.prenoms}".strip()

    @property
    def initiales(self):
        parts = []
        if self.nom:     parts.append(self.nom[0].upper())
        if self.prenoms: parts.append(self.prenoms[0].upper())
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
        years  = today.year  - d.year
        months = today.month - d.month
        if months < 0:
            years  -= 1
            months += 12
        if years > 0:
            label = f"{years} an{'s' if years > 1 else ''}{f' {months} mois' if months else ''}"
        else:
            label = f"{months} mois" if months else "< 1 mois"
        return {'annees': years, 'mois': months, 'label': label}

    @property
    def docs_manquants(self):
        existants = set(self.documents.values_list('type_document', flat=True))
        return [d for d in DOCS_OBLIGATOIRES if d not in existants]

    def __str__(self):
        prefix = 'Dr' if self.est_medecin else ''
        base   = f"{self.nom} {self.prenoms}".strip()
        suffix = f" ({self.matricule})" if self.matricule else ''
        return f"{prefix} {base}{suffix}".strip()

    class Meta:
        db_table         = 'employes_employe'
        ordering         = ['nom', 'prenoms']
        verbose_name     = "Employé"
        verbose_name_plural = "Employés"


# ══════════════════════════════════════════════════════════════════════════════
# DIPLÔMES PERSONNELS (enfant de Employe)
# ══════════════════════════════════════════════════════════════════════════════

class DiplomePersonnel(models.Model):
    employe      = models.ForeignKey(Employe, on_delete=CASCADE, related_name='diplomes_personnels')
    titre        = models.CharField(max_length=200, verbose_name='Titre du diplôme')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    annee        = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Année')

    def __str__(self): return self.titre

    class Meta:
        db_table         = 'employes_diplomepersonnel'
        verbose_name     = "Diplôme personnel"
        verbose_name_plural = "Diplômes personnels"
        ordering         = ['-annee', 'titre']


# ══════════════════════════════════════════════════════════════════════════════
# DOCTEUR RÉFÉRENT (contact médical externe)
# ══════════════════════════════════════════════════════════════════════════════

class DocteurReferent(models.Model):
    TYPE_CHOICES  = [('individu', 'Individu'), ('societe', 'Société')]
    GENRE_CHOICES = [('', '—'), ('M', 'Masculin'), ('F', 'Féminin')]
    TITRE_CHOICES = [
        ('', '—'), ('dr', 'Dr'), ('pr', 'Pr'),
        ('m', 'M.'), ('mme', 'Mme'), ('prof', 'Prof.'),
    ]

    code          = models.CharField(max_length=20, unique=True, blank=True)
    type_contact  = models.CharField(max_length=10, choices=TYPE_CHOICES, default='individu', verbose_name='Type')
    titre         = models.CharField(max_length=10, blank=True, choices=TITRE_CHOICES, verbose_name='Titre')
    nom           = models.CharField(max_length=100)
    prenoms       = models.CharField(max_length=200, blank=True, verbose_name='Prénom(s)')
    genre         = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True, default='', verbose_name='Genre')
    photo         = models.ImageField(upload_to='medecins/referents/', blank=True, null=True)
    poste_occupe  = models.CharField(max_length=100, blank=True, verbose_name='Poste Occupé')
    specialite    = models.ForeignKey(Specialite, on_delete=SET_NULL, null=True, blank=True,
                                      verbose_name='Spécialité', related_name='+')
    etablissement = models.CharField(max_length=200, blank=True, verbose_name='Établissement')
    telephone     = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    mobile        = models.CharField(max_length=20, blank=True)
    email         = models.EmailField(blank=True)
    site_web      = models.URLField(blank=True, verbose_name='Site Web')
    langue        = models.CharField(max_length=50, blank=True, default='Français', verbose_name='Langue')
    etiquettes    = models.ManyToManyField(Etiquette, blank=True, verbose_name='Étiquettes',
                                           through='DocteurReferentEtiquette', related_name='+')
    adresse       = models.TextField(blank=True)
    tva           = models.CharField(max_length=50, blank=True, verbose_name='TVA')
    medecin_interne = models.ForeignKey(
        Employe, on_delete=SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Médecin interne lié'
    )
    est_referent          = models.BooleanField(default=True, verbose_name='Est le médecin référent')
    reference_externe     = models.CharField(max_length=100, blank=True, verbose_name='Référence')
    compte_client         = models.CharField(max_length=100, blank=True, verbose_name='Compte client')
    compte_fournisseur    = models.CharField(max_length=100, blank=True, verbose_name='Compte fournisseur')
    notes         = models.TextField(blank=True, verbose_name='Notes internes')
    actif         = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            from django.utils import timezone
            annee = timezone.now().year
            count = DocteurReferent.objects.filter(date_creation__year=annee).count() + 1
            self.code = f"REF{annee}{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.prenoms:
            return f"Dr {self.nom} {self.prenoms}".strip()
        return f"Dr {self.nom}"

    class Meta:
        db_table         = 'utilisateur_docteurreferent'
        verbose_name     = "Docteur Référent"
        verbose_name_plural = "Docteurs Référents"
        ordering         = ['nom']


class ContactAdresse(models.Model):
    TYPE_CHOICES = [
        ('contact',     'Contact'),
        ('facturation', 'Adresse de facturation'),
        ('livraison',   'Adresse de livraison'),
        ('autre',       'Autre adresse'),
    ]
    referent      = models.ForeignKey(DocteurReferent, on_delete=CASCADE, related_name='contacts_adresses')
    type_adresse  = models.CharField(max_length=20, choices=TYPE_CHOICES, default='contact', verbose_name='Type')
    nom           = models.CharField(max_length=100, blank=True, verbose_name='Nom')
    telephone     = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    email         = models.EmailField(blank=True, verbose_name='Courriel')
    adresse       = models.TextField(blank=True, verbose_name='Adresse')

    def __str__(self):
        return f"{self.get_type_adresse_display()} — {self.nom or self.referent.nom}"

    class Meta:
        db_table         = 'utilisateur_contactadresse'
        verbose_name     = "Contact / Adresse"
        verbose_name_plural = "Contacts / Adresses"


class DocteurReferentEtiquette(models.Model):
    docteurreferent = models.ForeignKey(DocteurReferent, on_delete=CASCADE)
    etiquette       = models.ForeignKey(Etiquette, on_delete=CASCADE)

    class Meta:
        db_table       = 'utilisateur_docteurreferent_etiquettes'
        unique_together = [('docteurreferent', 'etiquette')]


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTS & ALERTES
# ══════════════════════════════════════════════════════════════════════════════

TYPE_DOC_CHOICES = [
    ('cni',        "Carte Nationale d'Identité"),
    ('passeport',  'Passeport'),
    ('diplome',    'Diplôme / Attestation'),
    ('contrat',    'Contrat de travail'),
    ('certificat', 'Certificat médical'),
    ('photo',      "Photo d'identité"),
    ('autre',      'Autre document'),
]

DOCS_OBLIGATOIRES = ['cni', 'contrat', 'diplome']


class DocumentEmploye(models.Model):
    employe         = models.ForeignKey(Employe, on_delete=CASCADE, related_name='documents')
    type_document   = models.CharField(max_length=20, choices=TYPE_DOC_CHOICES, default='autre')
    titre           = models.CharField(max_length=200)
    fichier         = models.FileField(upload_to='employes/documents/%Y/')
    date_expiration = models.DateField(null=True, blank=True)
    date_ajout      = models.DateTimeField(auto_now_add=True)
    ajoute_par      = models.ForeignKey(User, on_delete=SET_NULL, null=True, blank=True)
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
        db_table         = 'employes_documentemploye'
        ordering         = ['-date_ajout']
        verbose_name     = "Document"
        verbose_name_plural = "Documents"


class AlerteDocument(models.Model):
    ECHEANCE_CHOICES = [('2_mois', '2 mois'), ('1_mois', '1 mois')]
    document        = models.ForeignKey(DocumentEmploye, on_delete=CASCADE, related_name='alertes')
    echeance        = models.CharField(max_length=10, choices=ECHEANCE_CHOICES)
    date_expiration = models.DateField()
    lue             = models.BooleanField(default=False)
    cree_le         = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table       = 'employes_alertedocument'
        unique_together = [('document', 'echeance')]
        ordering       = ['date_expiration']
        verbose_name   = "Alerte document"
        verbose_name_plural = "Alertes documents"

    @property
    def jours_restants(self):
        return (self.date_expiration - date.today()).days


class InfoSupplementaire(models.Model):
    employe = models.ForeignKey(Employe, on_delete=CASCADE, related_name='infos_supp')
    cle     = models.CharField(max_length=100)
    valeur  = models.TextField()
    ordre   = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.employe.nom} — {self.cle}"

    class Meta:
        db_table         = 'employes_infosupplementaire'
        ordering         = ['ordre', 'cle']
        verbose_name     = "Information supplémentaire"
        verbose_name_plural = "Informations supplémentaires"


class HistoriqueEmploye(models.Model):
    TYPE_CHOICES = [
        ('creation', 'Création'),
        ('statut',   'Changement de statut'),
        ('salaire',  'Changement de salaire'),
        ('service',  'Changement de service'),
        ('contrat',  'Renouvellement de contrat'),
        ('autre',    'Modification'),
    ]
    employe         = models.ForeignKey(Employe, on_delete=CASCADE, related_name='historique')
    type_changement = models.CharField(max_length=20, choices=TYPE_CHOICES)
    ancienne_valeur = models.CharField(max_length=300, blank=True)
    nouvelle_valeur = models.CharField(max_length=300, blank=True)
    note            = models.CharField(max_length=300, blank=True)
    date            = models.DateTimeField(auto_now_add=True)
    fait_par        = models.ForeignKey(User, on_delete=SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'employes_historiqueemploye'
        ordering = ['-date']
        verbose_name = "Historique employé"
        verbose_name_plural = "Historique employés"

    def __str__(self):
        return f"{self.employe} — {self.get_type_changement_display()} — {self.date:%d/%m/%Y}"


class AlerteContrat(models.Model):
    ECHEANCE_CHOICES = [('2_mois', '2 mois'), ('1_mois', '1 mois')]
    employe          = models.ForeignKey(Employe, on_delete=CASCADE, related_name='alertes_contrat')
    echeance         = models.CharField(max_length=10, choices=ECHEANCE_CHOICES)
    date_fin_contrat = models.DateField()
    lue              = models.BooleanField(default=False)
    cree_le          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table       = 'employes_alertecontrat'
        unique_together = [('employe', 'echeance')]
        ordering       = ['-cree_le']
        verbose_name   = "Alerte contrat"
        verbose_name_plural = "Alertes contrat"

    def __str__(self):
        return f"Alerte {self.echeance} — {self.employe}"

    @property
    def jours_restants(self):
        return (self.date_fin_contrat - date.today()).days


# ══════════════════════════════════════════════════════════════════════════════
# CONGÉS
# ══════════════════════════════════════════════════════════════════════════════

class Conge(models.Model):
    TYPE = [
        ('annuel',           'Congé annuel'),
        ('maladie',          'Congé maladie'),
        ('maternite',        'Congé maternité'),
        ('paternite',        'Congé paternité'),
        ('exceptionnel',     'Congé exceptionnel'),
        ('mariage_employe',  'Mariage (employé)'),
        ('mariage_enfant',   'Mariage (enfant)'),
        ('deces_conjoint',   'Décès conjoint'),
        ('deces_enfant',     'Décès enfant'),
        ('deces_parent',     'Décès parent/beau-parent'),
        ('deces_frere_soeur','Décès frère/sœur'),
        ('naissance_enfant', 'Naissance enfant (père)'),
        ('sans_solde',       'Congé sans solde'),
    ]
    STATUT = [
        ('demande',        'Demandé'),
        ('valide_service', 'Validé par le service'),
        ('approuve',       'Approuvé'),
        ('refuse',         'Refusé'),
        ('en_cours',       'En cours'),
        ('termine',        'Terminé'),
    ]
    employe      = models.ForeignKey(Employe, on_delete=CASCADE, related_name='conges')
    type_conge   = models.CharField(max_length=20, choices=TYPE)
    date_debut   = models.DateField()
    date_fin     = models.DateField()
    motif        = models.TextField(blank=True)
    statut       = models.CharField(max_length=20, choices=STATUT, default='demande')
    nb_jours_ouvres      = models.PositiveSmallIntegerField(default=0, help_text="Jours ouvrés décomptés du solde")
    approuve_par         = models.ForeignKey(User, on_delete=SET_NULL, null=True, blank=True, related_name='conges_approuves')
    date_demande         = models.DateTimeField(auto_now_add=True)
    date_approbation     = models.DateTimeField(null=True, blank=True)
    commentaire_rh       = models.TextField(blank=True)
    valide_par_service       = models.ForeignKey(User, null=True, blank=True, related_name='conges_valides_service', on_delete=SET_NULL)
    date_validation_service  = models.DateTimeField(null=True, blank=True)
    chef_service_commentaire = models.TextField(blank=True)
    conge_parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=SET_NULL,
        related_name='fragments', verbose_name="Congé parent (fractionné)",
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
        db_table         = 'employes_conge'
        verbose_name     = "Congé"
        verbose_name_plural = "Congés"
        ordering         = ['-date_demande']


class HistoriqueConge(models.Model):
    ACTION = [
        ('soumis',             'Demande soumise'),
        ('valide_service',     'Validé par le service'),
        ('approuve',           'Approuvé'),
        ('refuse',             'Refusé'),
        ('annule',             'Annulé'),
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
        db_table = 'employes_historiqueconge'
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
        db_table         = 'employes_notificationconge'
        ordering         = ['-cree_le']
        verbose_name     = "Notification congé"
        verbose_name_plural = "Notifications congés"


class SoldeConge(models.Model):
    employe        = models.ForeignKey(Employe, on_delete=CASCADE, related_name='soldes_conge')
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
        db_table       = 'employes_soldeconge'
        unique_together = ['employe', 'annee']
        ordering       = ['-annee']
        verbose_name   = "Solde de congé"
        verbose_name_plural = "Soldes de congé"


# ══════════════════════════════════════════════════════════════════════════════
# PRÉSENCE & JOURS FÉRIÉS
# ══════════════════════════════════════════════════════════════════════════════

class Presence(models.Model):
    employe             = models.ForeignKey(Employe, on_delete=CASCADE, related_name='presences')
    date                = models.DateField()
    heure_arrivee_matin = models.TimeField(null=True, blank=True, verbose_name="Arrivée matin")
    heure_depart_matin  = models.TimeField(null=True, blank=True, verbose_name="Départ matin")
    heure_arrivee_soir  = models.TimeField(null=True, blank=True, verbose_name="Arrivée soir")
    heure_depart_soir   = models.TimeField(null=True, blank=True, verbose_name="Départ soir")
    present             = models.BooleanField(default=True)
    motif_absence       = models.CharField(max_length=200, blank=True)
    remarques           = models.CharField(max_length=300, blank=True)

    def __str__(self): return f"Présence {self.employe} - {self.date}"

    @property
    def duree_matin(self):
        if self.heure_arrivee_matin and self.heure_depart_matin:
            from datetime import datetime, date as _date
            d   = _date.today()
            dt1 = datetime.combine(d, self.heure_arrivee_matin)
            dt2 = datetime.combine(d, self.heure_depart_matin)
            diff = (dt2 - dt1).seconds // 60
            return diff if diff > 0 else 0
        return None

    @property
    def duree_soir(self):
        if self.heure_arrivee_soir and self.heure_depart_soir:
            from datetime import datetime, date as _date
            d   = _date.today()
            dt1 = datetime.combine(d, self.heure_arrivee_soir)
            dt2 = datetime.combine(d, self.heure_depart_soir)
            diff = (dt2 - dt1).seconds // 60
            return diff if diff > 0 else 0
        return None

    @property
    def duree_totale(self):
        m = self.duree_matin or 0
        s = self.duree_soir  or 0
        return m + s if (m or s) else None

    @property
    def retard_matin_min(self):
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
        if self.date.weekday() >= 5 or not self.heure_arrivee_soir:
            return 0
        if self.heure_arrivee_soir <= time(15, 15):
            return 0
        from datetime import datetime as _dt
        ref = _dt.combine(self.date, time(15, 0))
        arr = _dt.combine(self.date, self.heure_arrivee_soir)
        return int((arr - ref).total_seconds() // 60)

    class Meta:
        db_table       = 'employes_presence'
        verbose_name   = "Présence"
        unique_together = ['employe', 'date']
        ordering       = ['-date']


class JourFerie(models.Model):
    date        = models.DateField(unique=True, verbose_name="Date")
    description = models.CharField(max_length=100, verbose_name="Désignation")

    def __str__(self): return f"{self.description} – {self.date:%d/%m/%Y}"

    class Meta:
        db_table            = 'employes_jourferie'
        ordering            = ['date']
        verbose_name        = 'Jour férié'
        verbose_name_plural = 'Jours fériés'
