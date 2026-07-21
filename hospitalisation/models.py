from django.db import models, transaction, IntegrityError
from django.contrib.auth.models import User


class Batiment(models.Model):
    nom         = models.CharField(max_length=100, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")

    def __str__(self): return self.nom
    class Meta:
        verbose_name = "Bâtiment"
        verbose_name_plural = "Bâtiments"
        ordering = ['nom']


class Chambre(models.Model):
    TYPE  = [
        ('general',        'Général'),
        ('semi_special',   'Semi-spécial'),
        ('luxe',           'De luxe'),
        ('super_luxe',     'Super luxe'),
        ('suite',          'Suite'),
        ('partage',        'Partage'),
        ('soins_intensifs','Soins intensifs (ICU)'),
        ('dialyse',        'Dialyse'),
        ('salle_reveil',   'Salle de réveil'),
    ]
    GENRE = [
        ('unisexe',  'Unisexe'),
        ('masculin', 'Masculin'),
        ('feminin',  'Féminin'),
    ]

    # Identification
    nom          = models.CharField(max_length=100, default='', verbose_name="Nom")
    salle_no     = models.CharField(max_length=10, unique=True, editable=False,
                                    verbose_name="Salle No.")
    type_chambre = models.CharField(max_length=20, choices=TYPE, default='general',
                                    verbose_name="Salle/Chambre Type")
    statut       = models.BooleanField(default=True, verbose_name="Disponible")
    nombre_lits  = models.PositiveIntegerField(default=1, verbose_name="Nombre de lits")

    # Caractéristiques
    prive     = models.BooleanField(default=False, verbose_name="Privé")
    genre     = models.CharField(max_length=20, choices=GENRE, default='unisexe',
                                  verbose_name="Genre")

    # Équipements (onglet Établissement)
    acces_internet     = models.BooleanField(default=False, verbose_name="Accès Internet")
    climatisation      = models.BooleanField(default=False, verbose_name="Climatisation")
    salle_bains_privee = models.BooleanField(default=False, verbose_name="Salle de bains privée")
    television         = models.BooleanField(default=False, verbose_name="Télévision")
    telephone_chambre  = models.BooleanField(default=False, verbose_name="Téléphone")
    lit_visiteur       = models.BooleanField(default=False, verbose_name="Lit de visiteur")
    four_micro_onde    = models.BooleanField(default=False, verbose_name="Four micro onde")
    danger_biologique  = models.BooleanField(default=False, verbose_name="Danger biologique")
    refrigerateur      = models.BooleanField(default=False, verbose_name="Réfrigérateur")

    description = models.TextField(blank=True, verbose_name="Notes")

    def save(self, *args, **kwargs):
        if not self.salle_no:
            for _ in range(3):
                try:
                    with transaction.atomic():
                        last = Chambre.objects.select_for_update().filter(
                            salle_no__regex=r'^\d+$'
                        ).order_by('salle_no').last()
                        self.salle_no = f"{int(last.salle_no) + 1:02d}" if last else "00"
                        super().save(*args, **kwargs)
                        return
                except IntegrityError:
                    self.salle_no = ''
                    continue
            raise IntegrityError("Impossible de générer un numéro de salle unique après 3 tentatives.")
        super().save(*args, **kwargs)

    def __str__(self): return self.nom or f"Chambre {self.salle_no}"
    class Meta:
        verbose_name = "Chambre"
        ordering = ['salle_no']


# Signification des statuts :
#   brouillon   : demande créée (souvent depuis une consultation), tout est modifiable
#   confirme    : demande validée, lignes à facturer générées, en attente de paiement
#   hospitalise : facture payée, patient installé, heure_entree figée
#   decharge    : sortie MÉDICALE — le médecin autorise la sortie, heure_sortie figée ;
#                 si transfert=True sur ResumeDecharge, etablissement_destination + motif_reference sont renseignés
#   termine     : clôture ADMINISTRATIVE — bloquée tant qu'il reste des services à facturer
#                 non facturés ou des factures impayées sur ce dossier
#   annule      : possible uniquement depuis brouillon ou confirme
class Hospitalisation(models.Model):
    STATUT = [
        ('brouillon',   'Brouillon'),
        ('confirme',    'Confirmé'),
        ('hospitalise', 'Hospitalisé'),
        ('decharge',    'Déchargé'),
        ('termine',     'Terminé'),
        ('annule',      'Annulé'),
    ]

    # Identification
    numero         = models.CharField(max_length=20, unique=True, editable=False)
    statut         = models.CharField(max_length=20, choices=STATUT, default='brouillon')

    # En-tête du formulaire
    patient        = models.ForeignKey('patients.Patient', on_delete=models.CASCADE,
                                       related_name='hospitalisations', verbose_name="Patient")
    medecin_traitant = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name='hospitalisations_principales',
                                         verbose_name="Docteur principal")
    maladie        = models.ForeignKey('patients.Pathologie', on_delete=models.SET_NULL,
                                       null=True, blank=True, verbose_name="Maladie")
    date_admission = models.DateTimeField(verbose_name="Date de la demande d'hospitalisation")
    consultation   = models.ForeignKey('consultations.Consultation', on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='hospitalisations',
                                       verbose_name="Consultation d'origine")
    mise_en_observation = models.TextField(blank=True, verbose_name="Mise en observation")

    # Onglet 1 — Informations générales
    nom_parent_gardien   = models.CharField(max_length=200, blank=True,
                                            verbose_name="Nom du parent (gardien) du patient")
    phone_parent_gardien = models.CharField(max_length=20, blank=True,
                                            verbose_name="Phone du parent (gardien) du patient")
    medecin_referent     = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL,
                                             null=True, blank=True, related_name='hospitalisations_referent',
                                             verbose_name="Médecin référent")
    chambre              = models.ForeignKey(Chambre, on_delete=models.SET_NULL,
                                             null=True, blank=True, verbose_name="Salle/Chambre")
    numero_lit           = models.PositiveIntegerField(null=True, blank=True,
                                                       verbose_name="Numéro de lit")

    # Onglet Soins
    infirmiere_primaire  = models.ForeignKey(
        'medecins.Medecin', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hospitalisations_infirmiere',
        verbose_name="Infirmière primaire"
    )
    soins_apportes       = models.ManyToManyField(
        'services.Articleservice',
        blank=True, related_name='hospitalisations_soins',
        verbose_name="Soins apportés"
    )

    # Onglet Détails juridiques
    cas_legal            = models.BooleanField(default=False, verbose_name="Cas légal")
    signale_police       = models.CharField(
        max_length=3, blank=True, default='',
        choices=[('oui', 'Oui'), ('non', 'Non'), ('', '—')],
        verbose_name="Signalé à la police"
    )

    # Champs métier
    motif_admission      = models.TextField(blank=True, verbose_name="Motif d'admission")
    notes                = models.TextField(blank=True)

    # Horodatages figés à la transition de statut
    heure_entree = models.DateTimeField(null=True, blank=True, editable=False,
                                        verbose_name="Heure d'entrée")
    heure_sortie = models.DateTimeField(null=True, blank=True, editable=False,
                                        verbose_name="Heure de sortie")

    # Champs transfert (renseignés lors d'une décharge avec transfert=True sur ResumeDecharge)
    etablissement_destination = models.CharField(max_length=200, blank=True,
                                                  verbose_name="Établissement de destination")
    motif_reference           = models.TextField(blank=True, verbose_name="Motif du transfert")

    # Traçabilité
    cree_par          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='hospitalisations_creees')
    modifie_par       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='hospitalisations_modifiees',
                                          verbose_name="Modifié par")
    date_modification = models.DateTimeField(null=True, blank=True,
                                             verbose_name="Date de modification")
    termine_par       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='hospitalisations_terminees',
                                          verbose_name="Terminé par")
    date_termine      = models.DateTimeField(null=True, blank=True,
                                             verbose_name="Date de clôture")

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            for _ in range(3):
                try:
                    with transaction.atomic():
                        annee = timezone.now().year
                        prefix = f"HOSP{annee}"
                        last = Hospitalisation.objects.select_for_update().filter(
                            numero__startswith=prefix
                        ).order_by('-pk').first()
                        count = (int(last.numero[len(prefix):]) + 1) if last else 1
                        self.numero = f"{prefix}{count:05d}"
                        super().save(*args, **kwargs)
                        return
                except IntegrityError:
                    self.numero = ''
                    continue
            raise IntegrityError("Impossible de générer un numéro d'hospitalisation unique après 3 tentatives.")
        super().save(*args, **kwargs)

    @property
    def duree_observation(self):
        """Durée en secondes entre heure_entree et heure_sortie (ou maintenant)."""
        if not self.heure_entree:
            return None
        from django.utils import timezone
        fin = self.heure_sortie or timezone.now()
        return int((fin - self.heure_entree).total_seconds())

    @property
    def date_confirme(self):
        """Date du passage au statut Confirmé — dérivée du journal d'activité,
        aucun champ dédié n'existe pour cet horodatage."""
        from django.contrib.contenttypes.models import ContentType
        from core.models import LogActivite
        ct = ContentType.objects.get_for_model(self)
        log = LogActivite.objects.filter(
            content_type=ct, object_id=self.pk, type='statut', message__icontains='Confirmé',
        ).order_by('date').first()
        return log.date if log else None

    @property
    def temps_avant_hospitalisation(self):
        """Durée en secondes entre la confirmation et heure_entree."""
        if not self.heure_entree:
            return None
        confirme = self.date_confirme
        if not confirme:
            return None
        return int((self.heure_entree - confirme).total_seconds())

    def __str__(self): return f"Hosp. {self.numero} - {self.patient}"
    class Meta:
        verbose_name = "Hospitalisation"
        ordering = ['-date_admission']
        permissions = [
            # Rôles typiques indiqués en commentaire — attribution via init_groupes_hospitalisation
            ('can_confirmer_demande', "Peut confirmer une demande d'hospitalisation"),   # Médecin, Major
            # Attention : codename dupliqué avec soins.Soin — toujours qualifier
            # (user.has_perm('hospitalisation.can_creer_facture')), jamais un
            # Permission.objects.get(codename='can_creer_facture') non qualifié.
            ('can_creer_facture',     "Peut créer une facture d'hospitalisation"),        # Caisse
            ('can_installer_patient', "Peut installer le patient (passage en Hospitalisé)"),  # Infirmier, Major
            ('can_ajouter_soin',      "Peut ajouter des soins infirmiers (patient hospitalisé)"),  # Infirmier, Major
            ('can_decharger_patient', "Peut décharger un patient (sortie médicale)"),    # Médecin, Soins
            ('can_cloturer_dossier',  "Peut clôturer un dossier (passage à Terminé)"),   # Caisse, Admin
            ('can_annuler_demande',   "Peut annuler une demande"),                        # Médecin, Accueil, Major
        ]


class FicheVisite(models.Model):
    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE, related_name='fiches_visite')
    medecin = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL, null=True)
    date_visite = models.DateTimeField(auto_now_add=True)
    observation = models.TextField()
    evolution = models.TextField(blank=True)
    prescriptions = models.TextField(blank=True)
    constantes = models.JSONField(default=dict, blank=True)

    def __str__(self): return f"Visite {self.hospitalisation.numero} - {self.date_visite.strftime('%d/%m/%Y')}"
    class Meta:
        verbose_name = "Fiche de visite"
        ordering = ['-date_visite']



class VisiteInfirmiere(models.Model):
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE,
                                        related_name='visites_infirmieres')
    date            = models.DateTimeField(null=True, blank=True, verbose_name="Date")
    soin            = models.ForeignKey('services.Articleservice', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Soin / Acte")
    quantite        = models.DecimalField(max_digits=8, decimal_places=2, default=1,
                                          verbose_name="Quantité")
    unite_mesure    = models.ForeignKey('stock.UniteMesure', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Unité de mesure")
    infirmiere      = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Infirmière")
    remarques       = models.TextField(blank=True, verbose_name="Remarques")
    ordre           = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'date']


class VisiteDocteur(models.Model):
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE,
                                        related_name='visites_docteur')
    date            = models.DateTimeField(null=True, blank=True, verbose_name="Date")
    soin            = models.ForeignKey('services.Articleservice', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Soin / Acte")
    instruction     = models.TextField(blank=True, verbose_name="Instruction")
    docteur         = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Docteur")
    remarques       = models.TextField(blank=True, verbose_name="Remarques")
    ordre           = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'date']


class ServiceAFacturer(models.Model):
    SOURCE = [
        ('visite_infirmiere', 'Visite infirmière'),
        ('visite_docteur',    'Visite docteur'),
        ('soin',              'Soin apporté'),
        ('meo',               'Mise en observation'),
        ('manuel',            'Manuel'),
    ]
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE,
                                        related_name='services_a_facturer')
    service      = models.ForeignKey('services.Articleservice', on_delete=models.SET_NULL,
                                     null=True, blank=True, verbose_name="Service")
    unite_mesure = models.ForeignKey('stock.UniteMesure', on_delete=models.SET_NULL,
                                     null=True, blank=True, verbose_name="Unité de mesure")
    quantite     = models.DecimalField(max_digits=8, decimal_places=2, default=1, verbose_name="Quantité")
    date         = models.DateField(null=True, blank=True, verbose_name="Date")
    source       = models.CharField(max_length=20, choices=SOURCE, default='manuel', verbose_name="Origine")
    facture      = models.ForeignKey('facturation.Facture', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='services_hospitalisation',
                                     verbose_name="Facture")
    ordre        = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']


class ResumeDecharge(models.Model):
    hospitalisation      = models.OneToOneField('Hospitalisation', on_delete=models.CASCADE,
                                                related_name='resume_decharge')
    transfert            = models.BooleanField(default=False, verbose_name="Transfert")
    registre_deces       = models.ForeignKey('RegistreDeces', on_delete=models.SET_NULL,
                                             null=True, blank=True, verbose_name="Registre des décès")
    diagnostic_decharge  = models.TextField(blank=True, verbose_name="Diagnostic de décharge")
    note_preoperatoire   = models.TextField(blank=True, verbose_name="Note préopératoire")
    cours_post_operatoire = models.TextField(blank=True, verbose_name="Cours post-opératoire")
    plan_sortie          = models.TextField(blank=True, verbose_name="Plan de sortie")
    instructions         = models.TextField(blank=True, verbose_name="Instructions")

    class Meta:
        verbose_name = "Résumé de décharge"


class EvaluationClinique(models.Model):
    hospitalisation     = models.OneToOneField(
        'Hospitalisation', on_delete=models.CASCADE,
        related_name='evaluation_clinique'
    )
    poids               = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Poids (kg)")
    taille              = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Taille (m)")
    temperature         = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Temp (°C)")
    frequence_respiratoire = models.IntegerField(null=True, blank=True, verbose_name="Fréquence respiratoire")
    tension_systolique  = models.IntegerField(null=True, blank=True, verbose_name="Systolique")
    tension_diastolique = models.IntegerField(null=True, blank=True, verbose_name="Diastolique")
    saturation_o2       = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Saturation O2 (%)")
    glycemie            = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Glycémie aléatoire")
    niveau_douleur      = models.IntegerField(null=True, blank=True, verbose_name="Niveau de douleur (0-10)")
    date_saisie         = models.DateTimeField(auto_now=True)

    @property
    def imc(self):
        if self.poids and self.taille and self.taille > 0:
            return round(float(self.poids) / (float(self.taille) ** 2), 2)
        return None

    @property
    def imc_statut(self):
        v = self.imc
        if v is None: return ''
        if v < 18.5:  return 'Insuffisance pondérale'
        if v < 25:    return 'Normal'
        if v < 30:    return 'Surpoids'
        return 'Obèse'

    class Meta:
        verbose_name = "Évaluation clinique"


class ChecklistAdmission(models.Model):
    hospitalisation = models.ForeignKey(
        'Hospitalisation', on_delete=models.CASCADE,
        related_name='checklist_admission'
    )
    item      = models.CharField(max_length=300, verbose_name="Élément")
    verifie   = models.BooleanField(default=False, verbose_name="O/N")
    remarques = models.TextField(blank=True, verbose_name="Remarques")
    ordre     = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']


class ChecklistVerification(models.Model):
    hospitalisation = models.ForeignKey(
        'Hospitalisation', on_delete=models.CASCADE,
        related_name='checklist_verification'
    )
    item      = models.CharField(max_length=300, verbose_name="Élément")
    termine   = models.BooleanField(default=False, verbose_name="Terminé")
    remarques = models.TextField(blank=True, verbose_name="Remarques")
    ordre     = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']


class LogActiviteHospitalisation(models.Model):
    TYPE = [
        ('note',    'Note'),
        ('statut',  'Changement de statut'),
        ('modif',   'Modification'),
        ('system',  'Système'),
    ]
    hospitalisation = models.ForeignKey('Hospitalisation', on_delete=models.CASCADE,
                                        related_name='logs')
    user    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    type    = models.CharField(max_length=10, choices=TYPE, default='note')
    message = models.TextField()
    date    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Log d'activité"


class ListeVerificationService(models.Model):
    item = models.CharField(max_length=300, verbose_name="Élément de la liste de contrôle de salle")

    def __str__(self): return self.item
    class Meta:
        verbose_name = "Liste de vérification avant le service"
        verbose_name_plural = "Liste de vérification avant le service"
        ordering = ['id']


class ListeControleAdmission(models.Model):
    item      = models.CharField(max_length=300, verbose_name="Vérifier l'élément de la liste")
    remarques = models.TextField(blank=True, verbose_name="Remarques")

    def __str__(self): return self.item
    class Meta:
        verbose_name = "Liste de contrôle d'admission"
        verbose_name_plural = "Liste de contrôle d'admission"
        ordering = ['id']


class RegistreDeces(models.Model):
    STATUT = [('brouillon', 'Brouillon'), ('termine', 'Terminé')]

    code          = models.CharField(max_length=20, unique=True, editable=False)
    patient       = models.ForeignKey('patients.Patient', on_delete=models.PROTECT,
                                      related_name='deces', verbose_name="Patient")
    date_deces    = models.DateField(verbose_name="Date de décès")
    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.SET_NULL,
                                        null=True, blank=True, verbose_name="Hospitalisation")
    medecin       = models.ForeignKey('medecins.Medecin', on_delete=models.SET_NULL,
                                      null=True, blank=True, verbose_name="Docteur")
    raison_deces  = models.TextField(verbose_name="Raison du décès")
    remarques     = models.TextField(blank=True, verbose_name="Remarques")
    statut        = models.CharField(max_length=20, choices=STATUT, default='brouillon',
                                     verbose_name="Statut")
    cree_le       = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            for _ in range(3):
                try:
                    with transaction.atomic():
                        last = RegistreDeces.objects.select_for_update().order_by('id').last()
                        count = (last.id + 1) if last else 1
                        self.code = f"DEC{count:04d}"
                        super().save(*args, **kwargs)
                        return
                except IntegrityError:
                    self.code = ''
                    continue
            raise IntegrityError("Impossible de générer un code de décès unique après 3 tentatives.")
        super().save(*args, **kwargs)

    def __str__(self): return f"Décès {self.code} – {self.patient}"
    class Meta:
        verbose_name = "Registre des décès"
        verbose_name_plural = "Registre des décès"
        ordering = ['-date_deces']
