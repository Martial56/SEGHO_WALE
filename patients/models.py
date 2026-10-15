from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

from centres.models import CentreManager, ModeleCentre


class Assurance(models.Model):
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    telephone = models.CharField(max_length=20, blank=True)
    taux_prise_en_charge = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Assurance"


class PatientManager(CentreManager):
    """Le centre actif, et rien que des dossiers vivants.

    Une fiche masquée ou absorbée par une fusion n'est plus un dossier : elle
    ne doit plus paraître dans la liste des patients, dans la recherche, dans
    la fenêtre de saisie, ni dans les listes déroulantes d'un rendez-vous ou
    d'une facture. Poser la règle ici la pose partout d'un coup — y compris
    dans les `ModelChoiceField`, qui s'adressent au gestionnaire par défaut.

    `all_objects` reste non filtré : l'écran des doublons, le recalcul et la
    fiche ouverte par son adresse directe doivent, eux, continuer de la voir.
    """

    def get_queryset(self):
        return super().get_queryset().filter(masque=False, fusionne_dans__isnull=True)


class Patient(ModeleCentre):
    SEXE = [('M', 'Masculin'), ('F', 'Féminin')]
    GROUPE_SANGUIN = [('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')]

    code_patient = models.CharField(max_length=20, unique=True, editable=False)
    nom = models.CharField(max_length=100)
    prenoms = models.CharField(max_length=200)
    # Facultative : un dossier s'ouvre parfois sans elle — patient hors d'état
    # de la donner, pièce d'identité absente — et la refuser empêchait
    # d'enregistrer quelqu'un qu'on est en train de soigner. Les écrans qui
    # affichent un âge savent déjà n'en montrer aucun (voir `age`, `age_detail`
    # et le groupement « Âge inconnu » de patients.patient_listing).
    #
    # Indexée : le rapprochement de doublons (formulaire de création, import,
    # passerelle HPRIM) et le filtre par tranche d'âge de la liste patients
    # la cherchent, sur une table qui passe la dizaine de milliers de lignes.
    date_naissance = models.DateField(null=True, blank=True, db_index=True)
    # L'import convertit un âge en date à partir du jour où il tourne : « 34 ans »
    # importé le 1er octobre 2026 devient « né le 01/10/1992 ». 89 % de la base
    # porte ainsi le même jour et le même mois. Sans ce drapeau, la recherche de
    # doublons croit à de vraies dates identiques et rapproche n'importe qui.
    # Seule l'année d'une date cochée veut dire quelque chose.
    date_naissance_approx = models.BooleanField(
        default=False, verbose_name='Date de naissance approximative',
        help_text="Déduite d'un âge : seule l'année est fiable.")
    lieu_naissance = models.CharField(max_length=100, blank=True)
    sexe = models.CharField(max_length=1, choices=SEXE)
    nationalite = models.CharField(max_length=50, default='Ivoirienne')
    profession = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20)
    telephone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    ville = models.CharField(max_length=100, default='Yamoussoukro')
    groupe_sanguin = models.CharField(max_length=3, choices=GROUPE_SANGUIN, blank=True)
    allergies = models.TextField(blank=True)
    antecedents = models.TextField(blank=True)
    assurance = models.ForeignKey(Assurance, null=True, blank=True, on_delete=models.SET_NULL)
    numero_assurance = models.CharField(max_length=100, blank=True)
    date_expiration_assurance = models.DateField(null=True, blank=True)
    contact_urgence_nom = models.CharField(max_length=200, blank=True)
    contact_urgence_telephone = models.CharField(max_length=20, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    photo = models.ImageField(upload_to='patients/', blank=True, null=True)
    ancien_identifiant = models.CharField(
        max_length=50, blank=True,
        help_text="Identifiant du patient dans un système externe (conservé lors d'un import, non affiché)."
    )

    def save(self, *args, **kwargs):
        if not self.code_patient:
            from core.numerotation import prochain_code
            annee = timezone.now().year
            # all_objects : code_patient est unique tous centres confondus, la
            # numérotation ne doit donc jamais être filtrée par centre actif.
            self.code_patient = prochain_code(
                Patient.all_objects, 'code_patient', f'PAT{annee}', 5)
        super().save(*args, **kwargs)
        self._rafraichir_cles_phonetiques(kwargs.get('update_fields'))

    # ── Clés phonétiques ──────────────────────────────────────────────────
    # Elles ne dépendent que du nom, des prénoms et de la date. Les réécrire à
    # chaque enregistrement ferait deux requêtes de plus pour un changement
    # d'adresse ou de téléphone, qui n'y change rien.

    def _identite(self):
        return (self.nom, self.prenoms, self.date_naissance)

    @classmethod
    def from_db(cls, db, field_names, values):
        """Garde l'identité telle qu'elle était en base, pour la comparer à
        l'enregistrement. Une requête `.only()` qui n'a pas chargé ces champs
        ne laisse rien : on réécrira les clés, par sécurité."""
        instance = super().from_db(db, field_names, values)
        from .cles_phonetiques import CHAMPS_SURVEILLES
        if all(champ in field_names for champ in CHAMPS_SURVEILLES):
            instance._identite_chargee = instance._identite()
        return instance

    def _rafraichir_cles_phonetiques(self, update_fields=None):
        from .cles_phonetiques import doit_rafraichir, rafraichir
        if not doit_rafraichir(update_fields):
            return
        ancienne = getattr(self, '_identite_chargee', None)
        if ancienne is not None and ancienne == self._identite():
            return
        rafraichir([self])
        self._identite_chargee = self._identite()

    @property
    def age(self):
        if not self.date_naissance:
            return None
        from datetime import date
        t = date.today()
        return t.year - self.date_naissance.year - ((t.month, t.day) < (self.date_naissance.month, self.date_naissance.day))

    @property
    def date_precise(self):
        """Nom attendu par `patients.doublons.scorer`, qui n'a pas à connaître
        la façon dont le modèle enregistre l'information."""
        return not self.date_naissance_approx

    @property
    def age_detail(self):
        """Âge précis 'XAnsYMoisZJours' (années/mois/jours calendaires) — plus
        parlant que `age` pour les jeunes enfants (ex. nourrissons)."""
        if not self.date_naissance:
            return None
        from datetime import date
        from calendar import monthrange
        t = date.today()
        years = t.year - self.date_naissance.year
        months = t.month - self.date_naissance.month
        days = t.day - self.date_naissance.day
        if days < 0:
            months -= 1
            prev_month = t.month - 1 or 12
            prev_month_year = t.year if t.month > 1 else t.year - 1
            days += monthrange(prev_month_year, prev_month)[1]
        if months < 0:
            years -= 1
            months += 12
        return f'{years}Ans{months}Mois{days}Jours'

    @property
    def age_affiche(self):
        """Âge pour les formulaires : détaillé ('XAnsYMoisZJours') avant 5 ans,
        sinon 'N ans'."""
        age = self.age
        if age is None:
            return None
        return self.age_detail if age < 5 else f'{age} ans'

    # ── Fusion et masquage (posés par l'étape 4, lus dès maintenant) ──────
    # La détection de doublons doit déjà les ignorer : les ajouter plus tard
    # obligerait à relancer le recalcul complet sur toute la base.
    #
    # PROTECT, et non CASCADE : supprimer la fiche gardée emporterait les
    # fiches qu'elle a absorbées, c'est-à-dire l'historique de la fusion. On
    # préfère que la suppression échoue.
    fusionne_dans = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='fiches_absorbees', editable=False,
        verbose_name='Fusionnée dans',
        help_text="Renseigné par une fusion : la fiche n'est plus qu'une "
                  "redirection vers celle qui l'a absorbée.")
    masque = models.BooleanField(
        default=False, editable=False, verbose_name='Masquée',
        help_text="Dossier vide écarté à la main depuis l'écran des doublons.")
    # Masquer se fait toujours depuis un groupe : on sait donc de quelle fiche
    # celle-ci est le double. Sans cette référence, le bandeau de la fiche
    # masquée n'aurait rien à montrer, et l'import n'aurait pas où rediriger
    # ce qu'on tenterait d'y rattacher.
    doublon_de = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='fiches_masquees', editable=False,
        verbose_name='Doublon de')

    #: Les deux gestionnaires. `objects` écarte les fiches retirées, voir
    #: `PatientManager` ; `all_objects` ne filtre rien du tout.
    objects = PatientManager()
    all_objects = models.Manager()

    @property
    def remplacee_par(self):
        """La fiche à ouvrir à la place de celle-ci, ou None.

        Une fusion la renseigne par `fusionne_dans`, un masquage par
        `doublon_de` : pour tout ce qui doit rediriger — le bandeau, l'import,
        la passerelle HPRIM — c'est la même question.
        """
        return self.fusionne_dans or self.doublon_de

    @property
    def retiree(self):
        """Vrai si la fiche n'est plus un dossier ouvert."""
        return self.masque or self.fusionne_dans_id is not None

    def __str__(self): return f"{self.nom} {self.prenoms} ({self.code_patient})"
    class Meta(ModeleCentre.Meta):
        verbose_name = "Patient"
        ordering = ['-date_creation']
        permissions = [
            # Passer outre un dossier déjà existant : réservé, et tracé au
            # journal. Une permission plutôt qu'`is_superuser`, pour qu'on
            # puisse l'accorder à la major de l'accueil dans /admin/ sans lui
            # donner les clés du reste.
            ('forcer_creation_doublon',
             "Peut créer un dossier malgré un doublon signalé"),
            # L'écran des doublons : écarter une paire, masquer une fiche,
            # désigner celle qu'on garde. Séparée de `forcer_creation_doublon`,
            # qui ne concerne que la saisie.
            ('gerer_doublons',
             "Peut traiter les doublons de patients"),
        ]


class ClePhonetique(ModeleCentre):
    """Un mot du nom d'une fiche, réduit à sa prononciation.

    Une ligne par fiche et par mot — 2,7 en moyenne, 129 000 pour les 47 800
    fiches de la base. Une table plutôt qu'un champ texte unique : « KWASI
    AMENAN KAROLIN » dans une colonne ne se chercherait qu'en `LIKE '%KWASI%'`,
    qu'aucun index ne sert. Les tableaux indexés (`ArrayField` + GIN)
    règleraient le problème, mais n'existent que sur PostgreSQL, et le
    développement tourne sur SQLite.

    L'année de naissance est recopiée ici : la présélection croise toujours la
    clé avec un second indice — une clé seule ramènerait les 3 092 fiches de
    « KWASI » —, et la recopier évite une jointure sur `patients_patient`.

    Table de travail : elle se régénère entièrement depuis les fiches (voir
    `patients.cles_phonetiques`), rien n'y est saisi.
    """

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE,
                                related_name='cles_phonetiques')
    cle = models.CharField(max_length=32)
    annee = models.PositiveSmallIntegerField(null=True, blank=True)

    def __str__(self): return f'{self.cle} ({self.patient_id})'

    class Meta(ModeleCentre.Meta):
        verbose_name = 'Clé phonétique'
        verbose_name_plural = 'Clés phonétiques'
        constraints = [
            models.UniqueConstraint(fields=['patient', 'cle'],
                                    name='cle_phonetique_unique_par_fiche'),
        ]
        indexes = [
            # Sur la clé d'abord, pas sur le centre : la présélection cherche
            # `cle IN (…)` sans contrainte de centre — le périmètre est déjà
            # appliqué par la requête qui l'englobe — et un index qui commence
            # par le centre ne lui sert alors à rien.
            models.Index(fields=['cle', 'annee'], name='cle_phon_cle_annee'),
        ]


class DoublonPaire(ModeleCentre):
    """Deux fiches que le rapprochement a jugées proches.

    Reconstruite en entier par le recalcul : rien de ce qu'une personne a
    décidé ne vit ici (voir `PaireEcartee` et `ChoixFicheGardee`). Les groupes
    ne sont pas stockés non plus — ils se calculent à la lecture depuis ces
    paires, ce qui évite d'avoir à les réconcilier avec les décisions humaines
    à chaque passage.

    `patient_a` porte toujours le plus petit identifiant : sans cet ordre, la
    même paire s'écrirait deux fois et la contrainte d'unicité ne servirait à
    rien.
    """

    NIVEAU = [('certain', 'Quasi certain'), ('avertissement', 'À vérifier')]

    patient_a = models.ForeignKey(Patient, on_delete=models.CASCADE,
                                  related_name='doublons_a')
    patient_b = models.ForeignKey(Patient, on_delete=models.CASCADE,
                                  related_name='doublons_b')
    score = models.PositiveSmallIntegerField()
    niveau = models.CharField(max_length=15, choices=NIVEAU)
    details = models.JSONField(default=dict, blank=True)
    date_calcul = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f'{self.patient_a_id} ≈ {self.patient_b_id} ({self.score} %)'

    class Meta(ModeleCentre.Meta):
        verbose_name = 'Paire de doublons'
        verbose_name_plural = 'Paires de doublons'
        ordering = ['-score']
        constraints = [
            models.UniqueConstraint(fields=['patient_a', 'patient_b'],
                                    name='doublon_paire_unique'),
            models.CheckConstraint(condition=models.Q(patient_a__lt=models.F('patient_b')),
                                   name='doublon_paire_ordonnee'),
        ]
        indexes = [
            models.Index(fields=['centre', 'niveau', '-score'],
                         name='doublon_paire_centre_niveau'),
        ]


class PaireEcartee(ModeleCentre):
    """« Ce n'est pas un doublon » : la décision d'une personne.

    Le recalcul ne touche jamais cette table. Comme la paire est désignée par
    les deux identifiants, et non par ce que les fiches contiennent, la
    décision survit à la modification de l'une ou de l'autre : corriger un
    prénom ne fait pas revenir la question.
    """

    patient_a = models.ForeignKey(Patient, on_delete=models.CASCADE,
                                  related_name='paires_ecartees_a')
    patient_b = models.ForeignKey(Patient, on_delete=models.CASCADE,
                                  related_name='paires_ecartees_b')
    utilisateur = models.ForeignKey(User, null=True, blank=True,
                                    on_delete=models.SET_NULL)
    date = models.DateTimeField(auto_now_add=True)
    raison = models.TextField(blank=True)

    def __str__(self): return f'{self.patient_a_id} ≠ {self.patient_b_id}'

    class Meta(ModeleCentre.Meta):
        verbose_name = 'Paire écartée'
        verbose_name_plural = 'Paires écartées'
        constraints = [
            models.UniqueConstraint(fields=['patient_a', 'patient_b'],
                                    name='paire_ecartee_unique'),
            models.CheckConstraint(condition=models.Q(patient_a__lt=models.F('patient_b')),
                                   name='paire_ecartee_ordonnee'),
        ]


class ChoixFicheGardee(ModeleCentre):
    """« Quand cette fiche paraît dans un groupe, c'est elle qu'on garde. »

    Attachée à la fiche, pas au groupe : un groupe n'est pas une ligne, il se
    recompose à chaque recalcul, et une décision qui y serait rangée se
    perdrait au premier passage. La suggestion automatique — la fiche la plus
    complète, puis la plus ancienne — s'efface devant ce choix.

    Si deux fiches choisies se retrouvent dans le même groupe, la plus récente
    l'emporte.
    """

    patient = models.OneToOneField(Patient, on_delete=models.CASCADE,
                                   related_name='choix_fiche_gardee')
    utilisateur = models.ForeignKey(User, null=True, blank=True,
                                    on_delete=models.SET_NULL)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f'garder {self.patient_id}'

    class Meta(ModeleCentre.Meta):
        verbose_name = 'Fiche à garder'
        verbose_name_plural = 'Fiches à garder'


class RendezVous(ModeleCentre):

    STATUT = [('planifie','Planifié'),('confirme','Confirmé'),('en_attente','En attente'),('en_consultation','En consultation'),('termine','Terminé'),('annule','Annulé'),('absent','Absent')]
    TYPE = [('consultation','Consultation'),('controle','Contrôle'),('urgence','Urgence'),('examen','Examen'),('vaccination','Vaccination')]

    URGENCE = [('normal', 'Normal'), ('urgent', 'Urgent'), ('tres_urgent', 'Très urgent')]
    TYPE_VISITE_CPN = [
        ('cpn1',    'CPN 1'),
        ('cpn1_at', 'CPN 1 – Autre trimestre'),
        ('cpn2',    'CPN 2'),
        ('cpn2_at', 'CPN 2 – Autre trimestre'),
        ('cpn3',    'CPN 3'),
        ('cpn3_at', 'CPN 3 – Autre trimestre'),
        ('cpn4',    'CPN 4'),
        ('cpn4_at',  'CPN 4 – Autre trimestre'),
        ('cpn5plus', 'CPN 5 et plus'),
        ('autre',    'Autre'),
    ]

    code_rdv = models.CharField(max_length=20, blank=True, default='', verbose_name='Code RDV')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='rendez_vous')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous')
    docteur_jr = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='rdv_docteur_jr', verbose_name='Docteur Jr. responsable')
    departement = models.ForeignKey('medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous', verbose_name='Département')
    type_consultation = models.ForeignKey('services.Articleservice', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous', verbose_name='Type de consultation')
    salle_consultation = models.CharField(max_length=100, blank=True, verbose_name='Salle de consultation')
    date_heure = models.DateTimeField()
    date_suivi = models.DateTimeField(null=True, blank=True, verbose_name='Date de suivi')
    duree_minutes = models.IntegerField(default=0)
    type_rdv = models.CharField(max_length=20, choices=TYPE, default='consultation')
    type_visite_cpn = models.CharField(max_length=10, choices=TYPE_VISITE_CPN, blank=True, default='', verbose_name='Type de visite CPN')
    niveau_urgence = models.CharField(max_length=20, choices=URGENCE, default='normal', verbose_name="Niveau d'urgence")
    motif = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=STATUT, default='planifie')
    notes = models.TextField(blank=True)
    maladies = models.TextField(blank=True, verbose_name='Maladies')
    principales_plaintes = models.TextField(blank=True, verbose_name='Principales plaintes')
    antecedents_maladie = models.TextField(blank=True, verbose_name='Antécédents de la maladie actuelle')
    historique_passee = models.TextField(blank=True, verbose_name='Historique passée')
    rdv_exterieur = models.BooleanField(default=False, verbose_name='Rendez-vous extérieur')
    code_confirmation = models.CharField(max_length=30, blank=True, default='')
    temps_constante_minutes = models.IntegerField(default=0)
    temps_attente_minutes = models.IntegerField(default=0)
    temps_consultation_minutes = models.IntegerField(default=0)
    date_confirme = models.DateTimeField(null=True, blank=True)
    date_en_attente = models.DateTimeField(null=True, blank=True)
    date_en_consultation = models.DateTimeField(null=True, blank=True)
    date_termine = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    demarre_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rdv_demarres',
        verbose_name='Consultation démarrée par',
        help_text="Utilisateur connecté au moment du passage « En consultation » — peut différer du médecin assigné si un autre a pris le relais.",
    )
    termine_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='rdv_termines',
        verbose_name='Consultation terminée par',
    )

    MODE_ENTREE = [
        ('venu_lui_meme', 'Patient venu de lui-même'),
        ('reference_centre', "Référence d'un centre de santé"),
        ('refere_tradipraticien', 'Référé par un tradipraticien'),
        ('autre', 'Autre'),
    ]
    cpn_mode_entree = models.CharField(max_length=30, choices=MODE_ENTREE, blank=True, default='', verbose_name="Mode d'entrée CPN")
    cpn_mode_entree_autre = models.CharField(max_length=200, blank=True, default='', verbose_name="Mode d'entrée CPN (préciser)")
    cpn_type_visite = models.ForeignKey('gynecologie.TypeVisite', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous_cpn', verbose_name='Type de visite CPN')

    CUR_MODE_ENTREE = [
        ('venu_lui_meme', 'Patient venu de lui-même'),
        ('reference_centre', "Référence d'un centre de santé"),
        ('refere_tradipraticien', 'Référé par un tradipraticien'),
        ('autre', 'Autre'),
    ]
    cur_mode_entree = models.CharField(max_length=30, choices=CUR_MODE_ENTREE, blank=True, default='', verbose_name="Mode d'entrée curatif")
    cur_mode_entree_autre = models.CharField(max_length=200, blank=True, default='', verbose_name="Mode d'entrée curatif (préciser)")
    # Pointait auparavant vers gynecologie.TypeVisite (les CPN), ce qui était une
    # erreur : les visites curatives ont leurs propres types, configurables depuis
    # le menu Configurations des rendez-vous.
    cur_type_visite = models.ForeignKey('patients.TypeVisiteCurative', on_delete=models.SET_NULL, null=True, blank=True, related_name='rendez_vous_curatifs', verbose_name='Type de visite curative')

    def save(self, *args, **kwargs):
        if not self.code_rdv:
            # all_objects : le code reste unique tous centres confondus. Le
            # compter sur `objects`, cloisonné, redonnerait un code déjà pris
            # dans l'autre centre.
            count = RendezVous.all_objects.count() + 1
            candidate = f"AP{count:05d}"
            while RendezVous.all_objects.filter(code_rdv=candidate).exists():
                count += 1
                candidate = f"AP{count:05d}"
            self.code_rdv = candidate
        update_fields = kwargs.get('update_fields')
        if update_fields is None:
            self.duree_minutes = self.temps_constante_minutes + self.temps_attente_minutes + self.temps_consultation_minutes
        super().save(*args, **kwargs)

    @property
    def date_validite(self):
        from datetime import timedelta
        return (self.date_creation + timedelta(days=14)).date()

    @property
    def duree_display(self):
        h, m = divmod(self.duree_minutes, 60)
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def _fmt_sec(sec):
        sec = max(0, int(sec))
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @property
    def temps_constante_display(self):
        if self.date_en_attente and self.date_confirme:
            return self._fmt_sec((self.date_en_attente - self.date_confirme).total_seconds())
        return self._fmt_sec(self.temps_constante_minutes * 60)

    @property
    def temps_attente_display(self):
        if self.date_en_consultation and self.date_en_attente:
            return self._fmt_sec((self.date_en_consultation - self.date_en_attente).total_seconds())
        return self._fmt_sec(self.temps_attente_minutes * 60)

    @property
    def temps_consultation_display(self):
        if self.date_termine and self.date_en_consultation:
            return self._fmt_sec((self.date_termine - self.date_en_consultation).total_seconds())
        return self._fmt_sec(self.temps_consultation_minutes * 60)

    def __str__(self): return f"RDV {self.patient} - {self.date_heure.strftime('%d/%m/%Y %H:%M')}"
    class Meta(ModeleCentre.Meta):
        verbose_name = "Rendez-vous"
        ordering = ['date_heure']
        # Une permission par étape de la fiche (cf. patients/rdv_droits.py).
        permissions = [
            ('confirmer_rendezvous', 'Rendez-vous : peut confirmer (Brouillon → Confirmé)'),
            ('mettre_en_attente_rendezvous', 'Rendez-vous : peut mettre en attente (évaluation, médecin)'),
            ('consulter_rendezvous', 'Rendez-vous : peut mener la consultation (En attente → Terminé)'),
            ('annuler_rendezvous', 'Rendez-vous : peut annuler'),
        ]


class RegistreCPN(models.Model):
    rdv = models.OneToOneField(RendezVous, on_delete=models.CASCADE, related_name='registre_cpn')
    donnees = models.JSONField(default=dict, blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = "Registre CPN"

class RegistreAccouchement(models.Model):
    rdv = models.OneToOneField(RendezVous, on_delete=models.CASCADE, related_name='registre_accouchement')
    donnees = models.JSONField(default=dict, blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = "Registre Accouchement"

class RegistrePostnatale(models.Model):
    rdv = models.OneToOneField(RendezVous, on_delete=models.CASCADE, related_name='registre_postnatale')
    donnees = models.JSONField(default=dict, blank=True)
    date_modification = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = "Registre Postnatale"

class RegistreCuratif(models.Model):
    rdv = models.OneToOneField(RendezVous, on_delete=models.CASCADE, related_name='registre_curatif')
    donnees = models.JSONField(default=dict, blank=True)
    date_modification = models.DateTimeField(auto_now=True)

    @property
    def diagnostic_display(self):
        """Retourne les noms des pathologies sélectionnées dans cur_diagnostic."""
        raw = self.donnees.get('cur_diagnostic', [])
        if isinstance(raw, str):
            raw = [raw] if raw else []
        pks = [int(v) for v in raw if str(v).strip().isdigit()]
        if not pks:
            return ''
        return ', '.join(
            Pathologie.objects.filter(pk__in=pks).order_by('nom').values_list('nom', flat=True)
        )

    class Meta:
        verbose_name = "Registre Curatif"


class Pathologie(models.Model):
    CATEGORIE = [
        ('generale',         'Générale'),
        ('grossesse',        'Pathologie sur grossesse'),
        ('infectieuse',      'Maladie infectieuse'),
        ('non_infectieuse',  'Autre maladie non infectieuse'),
        ('ist',              'IST / MST'),
        ('epidemiologie',    'Épidémiologie (déclaration obligatoire)'),
        ('autre_gyneco',     'Autre maladie gynécologique'),
    ]

    nom           = models.CharField(max_length=300, verbose_name='Nom')
    description   = models.TextField(blank=True, verbose_name='Description')
    categorie     = models.CharField(max_length=20, choices=CATEGORIE, default='generale', verbose_name='Catégorie')
    departement   = models.ForeignKey('medecins.Departement', on_delete=models.SET_NULL, null=True, blank=True, related_name='pathologies', verbose_name='Département')
    actif         = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Pathologie"
        ordering = ['nom']


class Naissance(models.Model):
    SEXE = [('M', 'Masculin'), ('F', 'Féminin')]
    MODE = [
        ('voie_basse', 'Voie basse'),
        ('cesarienne', 'Césarienne'),
        ('forceps', 'Forceps'),
        ('ventouse', 'Ventouse'),
    ]
    STATUT = [('vivant', 'Vivant'), ('mort_ne', 'Mort-né')]
    STATUT_DOSSIER = [('brouillon', 'Brouillon'), ('termine', 'Terminé')]
    GROUPE_SANGUIN = [('A+','A+'),('A-','A-'),('B+','B+'),('B-','B-'),('AB+','AB+'),('AB-','AB-'),('O+','O+'),('O-','O-')]
    EDUCATION = [('','—'),('aucun','Aucun'),('primaire','Primaire'),('secondaire','Secondaire'),('superieur','Supérieur')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    mere = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='naissances', verbose_name='Mère')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Médecin')
    date_accouchement = models.DateTimeField(verbose_name="Date d'accouchement")
    lieu_naissance = models.CharField(max_length=100, blank=True, verbose_name="Lieu de naissance")
    mode_accouchement = models.CharField(max_length=20, choices=MODE, default='voie_basse', verbose_name="Mode d'accouchement")
    nom_enfant = models.CharField(max_length=100, blank=True, verbose_name="Nom de l'enfant")
    prenoms_enfant = models.CharField(max_length=200, blank=True, verbose_name="Prénoms de l'enfant")
    sexe_enfant = models.CharField(max_length=1, choices=SEXE, verbose_name="Sexe de l'enfant")
    poids_naissance = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Poids (g)")
    groupe_sanguin_enfant = models.CharField(max_length=3, choices=GROUPE_SANGUIN, blank=True, verbose_name="Groupe sanguin")
    taux_hemoglobine = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Taux d'hémoglobine")
    taille_naissance = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Taille (cm)")
    apgar_1min = models.IntegerField(null=True, blank=True, verbose_name="Apgar 1 min")
    apgar_5min = models.IntegerField(null=True, blank=True, verbose_name="Apgar 5 min")
    statut = models.CharField(max_length=10, choices=STATUT, default='vivant')
    info_parents = models.TextField(blank=True, verbose_name="Information sur les parents")
    education_mere = models.CharField(max_length=20, choices=EDUCATION, blank=True, verbose_name="Éducation")
    age_mere = models.IntegerField(null=True, blank=True, verbose_name="Âge de la mère")
    parite = models.IntegerField(default=0, verbose_name="Parité")
    nombre_garcons = models.IntegerField(default=0, verbose_name="Garçon(s)")
    nombre_filles = models.IntegerField(default=0, verbose_name="Fille(s)")
    remarques = models.TextField(blank=True, verbose_name="Remarques")
    statut_dossier = models.CharField(max_length=20, choices=STATUT_DOSSIER, default='brouillon', verbose_name="Statut du dossier")
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            annee = timezone.now().year
            self.numero = prochain_code(
                Naissance.objects, 'numero', f'NAISS{annee}', 4)
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.numero} - {self.mere}"
    class Meta:
        verbose_name = "Naissance"
        ordering = ['-date_accouchement']


class TypeVisiteCurative(models.Model):
    """Types de visite des consultations curatives, configurables.

    Remplace trois valeurs qui étaient écrites en dur dans le formulaire de
    rendez-vous (Consultant / Contrôle / Soins). Le `code` est la valeur
    historiquement enregistrée dans le registre curatif (`donnees` →
    `cur_type_visite`) et lue par les rapports : il doit rester stable.

    Le pendant gynécologique est `gynecologie.TypeVisite` (les CPN).
    """
    nom           = models.CharField(max_length=200, verbose_name='Nom')
    code          = models.CharField(max_length=50, unique=True, verbose_name='Code')
    description   = models.TextField(blank=True, verbose_name='Description')
    actif         = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nom

    @property
    def filtre_code(self):
        """Valeur utilisée dans l'URL pour filtrer sur ce type de visite."""
        from .rdv_listing import PREFIXE_VISITE_CURATIVE
        return f'{PREFIXE_VISITE_CURATIVE}{self.code}'

    class Meta:
        verbose_name = "Type de visite curative"
        verbose_name_plural = "Types de visite curative"
        ordering = ['nom']
