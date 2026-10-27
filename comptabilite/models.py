"""
Sessions de caisse — lot 1 du module Comptabilité.

Plusieurs caissières, sur plusieurs ordinateurs, peuvent encaisser **en même
temps sur la même caisse**. Deux niveaux le permettent :

- `JourneeCaisse` : une par caisse et par jour. Elle s'ouvre avec la première
  session du jour et se clôture quand toutes les sessions sont closes, par un
  superviseur ou par une caissière qui y a travaillé.
- `SessionCaissiere` : une par caissière dans la journée. Chaque `Paiement`
  porte la session de celle qui l'a encaissé : c'est ce qui dit, pour une même
  caisse, ce que chacune a encaissé.

Organisation retenue (« option A ») : la caisse est partagée, mais chaque
caissière garde ses espèces dans **sa pochette**. Elle reçoit son propre fonds
de caisse, compte sa pochette à la clôture de sa session, et l'écart est le
sien. Un écart sur un tiroir commun ne serait imputable à personne.

La session appartient à la caissière, pas à l'ordinateur : elle la retrouve en
se reconnectant, sur n'importe quel poste. Une caissière n'a jamais qu'une
session ouverte à la fois — sinon on ne saurait plus dans quelle pochette est
l'argent.
"""
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone

from centres.models import ModeleCentre

# Coupures du franc CFA (BCEAO) proposées au comptage. Le 500 F existe en
# billet et en pièce : les deux se comptent séparément.
BILLETS = [10000, 5000, 2000, 1000, 500]
PIECES = [500, 250, 200, 100, 50, 25, 10, 5]


def coupures():
    """[(clé, valeur, libellé)] des billets puis des pièces, pour le comptage."""
    return ([(f'b{v}', v, f'Billet de {v:,} F'.replace(',', ' ')) for v in BILLETS]
            + [(f'p{v}', v, f'Pièce de {v:,} F'.replace(',', ' ')) for v in PIECES])


class JourneeCaisse(ModeleCentre):
    STATUT = [('ouverte', 'Ouverte'), ('cloturee', 'Clôturée')]

    caisse = models.ForeignKey('facturation.Caisse', on_delete=models.PROTECT,
                               related_name='journees', verbose_name="Caisse")
    date_journee = models.DateField(verbose_name="Date")
    statut = models.CharField(max_length=10, choices=STATUT, default='ouverte')
    date_ouverture = models.DateTimeField(auto_now_add=True)
    ouverte_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='journees_caisse_ouvertes')
    date_cloture = models.DateTimeField(null=True, blank=True)
    cloturee_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='journees_caisse_cloturees')
    observations = models.TextField(blank=True)

    def __str__(self):
        return f"{self.caisse} — {self.date_journee:%d/%m/%Y}"

    @property
    def est_ouverte(self):
        return self.statut == 'ouverte'

    def sessions_ouvertes(self):
        return self.sessions.filter(statut='ouverte')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Journée de caisse"
        verbose_name_plural = "Journées de caisse"
        ordering = ['-date_journee', 'caisse__nom']
        constraints = [
            models.UniqueConstraint(fields=['caisse', 'date_journee'],
                                    name='une_journee_par_caisse_et_par_jour'),
        ]


class SessionCaissiere(ModeleCentre):
    STATUT = [('ouverte', 'Ouverte'), ('cloturee', 'Clôturée'), ('validee', 'Validée')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    journee = models.ForeignKey(JourneeCaisse, on_delete=models.PROTECT,
                                related_name='sessions', verbose_name="Journée de caisse")
    caissiere = models.ForeignKey(User, on_delete=models.PROTECT,
                                  related_name='sessions_caisse', verbose_name="Caissière")
    statut = models.CharField(max_length=10, choices=STATUT, default='ouverte')

    date_ouverture = models.DateTimeField(auto_now_add=True)
    fonds_initial = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                        verbose_name="Fonds de caisse remis")

    # Clôture — figée au moment du comptage : les montants ne bougent plus,
    # même si une facture de la session est annulée ensuite.
    date_cloture = models.DateTimeField(null=True, blank=True)
    cloturee_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='sessions_caisse_cloturees')
    cloture_d_office = models.BooleanField(
        default=False, verbose_name="Clôturée d'office",
        help_text="Clôturée par un superviseur à la place de la caissière.")
    motif_cloture_d_office = models.TextField(blank=True)
    billetage = models.JSONField(default=dict, blank=True,
                                 help_text="Nombre de billets et de pièces comptés, par coupure.")
    montant_theorique = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                            verbose_name="Espèces attendues")
    montant_compte = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
                                         verbose_name="Espèces comptées")
    ecart = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    justification_ecart = models.TextField(blank=True, verbose_name="Justification de l'écart")

    validee_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='sessions_caisse_validees')
    date_validation = models.DateTimeField(null=True, blank=True)
    observation_validation = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(SessionCaissiere.all_objects, 'numero',
                                        f'SES{timezone.now().year}', 5)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.caissiere.get_full_name() or self.caissiere.username}"

    @property
    def caisse(self):
        return self.journee.caisse

    @property
    def est_ouverte(self):
        return self.statut == 'ouverte'

    @property
    def est_du_jour(self):
        return self.journee.date_journee == timezone.localdate()

    @property
    def nom_caissiere(self):
        return self.caissiere.get_full_name() or self.caissiere.username

    class Meta(ModeleCentre.Meta):
        verbose_name = "Session de caissière"
        verbose_name_plural = "Sessions de caissière"
        ordering = ['-date_ouverture']
        constraints = [
            # Une seule pochette en cours par caissière.
            models.UniqueConstraint(fields=['caissiere'], condition=Q(statut='ouverte'),
                                    name='une_session_ouverte_par_caissiere'),
        ]
        permissions = [
            ('superviser_caisse',
             "Peut superviser les caisses (voir toutes les sessions, clôturer "
             "d'office, valider, rouvrir une journée)"),
        ]


# ─── Lot 2 : sorties de caisse, avoirs, motifs de gratuité ─────────────────────

class MotifSortie(models.Model):
    """Pourquoi de l'argent sort d'une pochette : achat de fournitures,
    course, petit entretien… Le compte de charge viendra s'y attacher avec
    le plan comptable."""
    libelle = models.CharField(max_length=120, unique=True, verbose_name="Libellé")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    compte = models.ForeignKey('Compte', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='motifs_sortie', verbose_name="Compte de charge",
                               help_text="Vide : le compte « Sorties de caisse (défaut) » des correspondances.")

    def __str__(self):
        return self.libelle

    class Meta:
        verbose_name = "Motif de sortie de caisse"
        verbose_name_plural = "Motifs de sortie de caisse"
        ordering = ['libelle']


class MotifGratuite(models.Model):
    """Pourquoi un patient paie moins que le tarif : indigent, personnel,
    programme… La facture garde le prix plein ; la remise et son motif disent
    l'effort social consenti."""
    libelle = models.CharField(max_length=120, unique=True, verbose_name="Libellé")
    remise_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=100, verbose_name="Remise maximale (%)",
        help_text="Au-delà, seule une personne autorisée peut accorder la remise.")
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True, verbose_name="Actif")

    def __str__(self):
        return self.libelle

    class Meta:
        verbose_name = "Motif de gratuité"
        verbose_name_plural = "Motifs de gratuité"
        ordering = ['libelle']
        permissions = [
            ('accorder_remise_hors_plafond',
             "Peut accorder une remise au-delà du plafond de son motif"),
        ]


class SortieCaisse(ModeleCentre):
    """Argent remis depuis la pochette d'une caissière contre un justificatif.

    Sous le seuil de la caisse, la sortie est payée sur-le-champ. Au-dessus,
    elle attend la décision du superviseur : tant qu'elle n'est pas acceptée,
    l'argent reste dans la pochette.
    """
    STATUT = [('en_attente', 'En attente de validation'), ('payee', 'Payée'),
              ('refusee', 'Refusée'), ('annulee', 'Annulée')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    session = models.ForeignKey(SessionCaissiere, on_delete=models.PROTECT,
                                related_name='sorties', verbose_name="Session de caisse")
    motif = models.ForeignKey(MotifSortie, on_delete=models.PROTECT, related_name='sorties')
    libelle = models.CharField(max_length=255, verbose_name="Détail")
    beneficiaire = models.CharField(max_length=150, blank=True, verbose_name="Bénéficiaire")
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    justificatif = models.FileField(upload_to='caisse/justificatifs/%Y/%m/', blank=True,
                                    verbose_name="Justificatif")
    convention = models.ForeignKey('Convention', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='sorties_caisse',
                                   verbose_name="Financée par la convention")
    statut = models.CharField(max_length=12, choices=STATUT, default='en_attente')
    demandee_par = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sorties_demandees')
    date_demande = models.DateTimeField(auto_now_add=True)
    decidee_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='sorties_decidees')
    date_decision = models.DateTimeField(null=True, blank=True)
    observation = models.TextField(blank=True)
    date_paiement = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(SortieCaisse.all_objects, 'numero',
                                        f'SOR{timezone.now().year}', 5)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.montant:,.0f} F".replace(',', ' ')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Sortie de caisse"
        verbose_name_plural = "Sorties de caisse"
        ordering = ['-date_demande']


class Avoir(ModeleCentre):
    """Annulation comptable d'une facture émise ou payée.

    On ne supprime pas une vente : on l'annule par un avoir du même montant.
    Si le patient avait payé, l'avoir porte aussi le remboursement — combien,
    comment, et de quelle pochette l'argent est sorti (la session de la
    personne qui a rendu l'argent, pas celle qui l'avait encaissé).
    """
    numero = models.CharField(max_length=20, unique=True, editable=False)
    facture = models.ForeignKey('facturation.Facture', on_delete=models.PROTECT,
                                related_name='avoirs')
    montant = models.DecimalField(max_digits=15, decimal_places=2,
                                  verbose_name="Montant de l'avoir")
    motif = models.TextField(verbose_name="Cause de l'annulation")
    montant_rembourse = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                            verbose_name="Montant remboursé")
    mode_remboursement = models.CharField(max_length=20, blank=True,
                                          verbose_name="Mode de remboursement")
    reference = models.CharField(max_length=100, blank=True)
    session = models.ForeignKey(SessionCaissiere, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='avoirs', verbose_name="Session de caisse")
    cree_par = models.ForeignKey(User, on_delete=models.PROTECT, related_name='avoirs_crees')
    date_creation = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(Avoir.all_objects, 'numero',
                                        f'AV{timezone.now().year}', 5)
        super().save(*args, **kwargs)

    @property
    def mode_remboursement_libelle(self):
        from facturation.models import Paiement
        return dict(Paiement.MODE).get(self.mode_remboursement, self.mode_remboursement)

    def __str__(self):
        return f"Avoir {self.numero} — facture {self.facture.numero}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Avoir"
        verbose_name_plural = "Avoirs"
        ordering = ['-date_creation']



# ─── Lot 3 : plan comptable SYCEBNL, journaux, écritures ───────────────────────

class Compte(models.Model):
    """Compte du plan comptable (SYCEBNL, structure OHADA).

    Le plan est semé par migration et se complète à l'écran. `a_valider`
    signale les comptes dont l'intitulé ou le numéro propre au SYCEBNL doit
    être confirmé par l'expert-comptable avant la première clôture.
    """
    numero = models.CharField(max_length=12, unique=True, verbose_name="Numéro")
    intitule = models.CharField(max_length=200, verbose_name="Intitulé")
    actif = models.BooleanField(default=True)
    a_valider = models.BooleanField(default=False, verbose_name="À confirmer par l'expert-comptable")

    @property
    def classe(self):
        return self.numero[:1]

    def __str__(self):
        return f"{self.numero} — {self.intitule}"

    class Meta:
        verbose_name = "Compte"
        verbose_name_plural = "Plan comptable"
        ordering = ['numero']
        permissions = [
            ('passer_ecritures', "Peut valider (passer) et contre-passer les écritures comptables"),
        ]


class Journal(models.Model):
    TYPE = [('ventes', 'Ventes'), ('caisse', 'Caisse'), ('tresorerie', 'Trésorerie'),
            ('achats', 'Achats'), ('od', 'Opérations diverses'), ('an', 'À-nouveaux')]

    code = models.CharField(max_length=12, unique=True)
    libelle = models.CharField(max_length=120, verbose_name="Libellé")
    type = models.CharField(max_length=12, choices=TYPE)
    # Journal d'une caisse : un par caisse, son compte 571 en contrepartie.
    caisse = models.OneToOneField('facturation.Caisse', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='journal_comptable')
    actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} — {self.libelle}"

    class Meta:
        verbose_name = "Journal comptable"
        verbose_name_plural = "Journaux comptables"
        ordering = ['code']


class Correspondance(models.Model):
    """Quel compte pour quel événement : nature de prestation, mode de
    paiement, caisse, remise, écart… Les écritures automatiques ne
    connaissent aucun numéro de compte : elles lisent cette table."""
    cle = models.CharField(max_length=60, unique=True)
    libelle = models.CharField(max_length=150)
    compte = models.ForeignKey(Compte, on_delete=models.PROTECT, related_name='correspondances')

    def __str__(self):
        return f"{self.libelle} → {self.compte.numero}"

    class Meta:
        verbose_name = "Correspondance comptable"
        verbose_name_plural = "Correspondances comptables"
        ordering = ['cle']


class Exercice(models.Model):
    STATUT = [('ouvert', 'Ouvert'), ('cloture', 'Clôturé')]
    libelle = models.CharField(max_length=40, unique=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    statut = models.CharField(max_length=10, choices=STATUT, default='ouvert')

    def __str__(self):
        return self.libelle

    class Meta:
        verbose_name = "Exercice comptable"
        ordering = ['-date_debut']


class Ecriture(ModeleCentre):
    """Écriture comptable : un en-tête, des lignes équilibrées.

    Née en brouillon (générée depuis la facturation et la caisse, ou saisie en
    opération diverse), elle reçoit son numéro **à la validation** — numérotation
    continue et sans trou par journal et par exercice — et ne se modifie plus.
    Une erreur se corrige par contre-passation.
    """
    STATUT = [('brouillon', 'Brouillon'), ('validee', 'Validée')]

    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='ecritures')
    exercice = models.ForeignKey(Exercice, on_delete=models.PROTECT, related_name='ecritures')
    numero = models.PositiveIntegerField(null=True, blank=True,
                                         help_text="Attribué à la validation, sans trou.")
    date = models.DateField()
    libelle = models.CharField(max_length=255)
    piece = models.CharField(max_length=60, blank=True, verbose_name="Pièce")
    statut = models.CharField(max_length=10, choices=STATUT, default='brouillon')
    # Clé de l'événement d'origine (« paiement:12 », « facture:7 »…) : une
    # génération relancée ne crée jamais deux fois la même écriture.
    origine = models.CharField(max_length=60, null=True, blank=True, unique=True)
    contre_passation_de = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='contre_passee_par')
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='ecritures_creees')
    date_creation = models.DateTimeField(auto_now_add=True)
    validee_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='ecritures_validees')
    date_validation = models.DateTimeField(null=True, blank=True)

    @property
    def reference(self):
        if self.numero is None:
            return 'Brouillon'
        return f"{self.journal.code}-{self.exercice.libelle}-{self.numero:05d}"

    def totaux(self):
        from django.db.models import Sum
        t = self.lignes.aggregate(d=Sum('debit'), c=Sum('credit'))
        return t['d'] or 0, t['c'] or 0

    def __str__(self):
        return f"{self.reference} — {self.libelle}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Écriture comptable"
        verbose_name_plural = "Écritures comptables"
        ordering = ['-date', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['journal', 'exercice', 'numero'],
                                    name='numero_unique_par_journal_et_exercice'),
        ]


class LigneEcriture(models.Model):
    ecriture = models.ForeignKey(Ecriture, on_delete=models.CASCADE, related_name='lignes')
    compte = models.ForeignKey(Compte, on_delete=models.PROTECT, related_name='lignes')
    libelle = models.CharField(max_length=255, blank=True)
    tiers = models.CharField(max_length=150, blank=True, help_text="Patient, assureur, fournisseur…")
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    # Axe « financement » : la convention qui porte cette charge ou cette
    # ressource. Vide = fonds propres du centre.
    convention = models.ForeignKey('Convention', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='lignes_ecriture')

    class Meta:
        verbose_name = "Ligne d'écriture"
        ordering = ['pk']



# ─── Lot 5 : bailleurs, conventions, dons, budget ──────────────────────────────

class Bailleur(models.Model):
    """Partenaire financier : bailleur, État, ONG, fondation, entreprise,
    particulier donateur."""
    TYPE = [('bailleur', 'Bailleur de fonds'), ('etat', 'État / collectivité'), ('ong', 'ONG / association'),
            ('fondation', 'Fondation'), ('entreprise', 'Entreprise'), ('particulier', 'Particulier')]
    nom = models.CharField(max_length=200, unique=True)
    sigle = models.CharField(max_length=30, blank=True)
    type = models.CharField(max_length=12, choices=TYPE, default='bailleur')
    contact = models.CharField(max_length=150, blank=True, verbose_name="Personne de contact")
    telephone = models.CharField(max_length=30, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.sigle} — {self.nom}" if self.sigle else self.nom

    class Meta:
        verbose_name = "Bailleur / partenaire"
        verbose_name_plural = "Bailleurs et partenaires"
        ordering = ['nom']


class Convention(ModeleCentre):
    """Financement accordé par un bailleur pour un projet, sur une période.

    Les versements reçus sont des ressources de la convention ; les dépenses
    lui sont imputées par l'axe « financement » des lignes d'écriture. Le reste
    non utilisé en fin d'exercice devient un fonds dédié.
    """
    STATUT = [('active', 'Active'), ('suspendue', 'Suspendue'), ('terminee', 'Terminée')]

    code = models.CharField(max_length=20, unique=True, editable=False)
    bailleur = models.ForeignKey(Bailleur, on_delete=models.PROTECT, related_name='conventions')
    intitule = models.CharField(max_length=255, verbose_name="Projet / objet")
    reference = models.CharField(max_length=80, blank=True, verbose_name="Référence du bailleur")
    date_debut = models.DateField(verbose_name="Début")
    date_fin = models.DateField(verbose_name="Fin")
    montant_accorde = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Montant accordé")
    compte_ressource = models.ForeignKey(
        'Compte', on_delete=models.PROTECT, related_name='conventions',
        verbose_name="Compte de ressource",
        help_text="Compte crédité à chaque versement (subvention d'exploitation, d'équipement…).")
    statut = models.CharField(max_length=10, choices=STATUT, default='active')
    description = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            from core.numerotation import prochain_code
            self.code = prochain_code(Convention.all_objects, 'code', f'CONV{timezone.now().year}', 3)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.intitule}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Convention de financement"
        verbose_name_plural = "Conventions de financement"
        ordering = ['-date_debut']


class LigneBudgetaire(models.Model):
    """Ligne du budget d'une convention : ce que le bailleur autorise à dépenser."""
    convention = models.ForeignKey(Convention, on_delete=models.CASCADE, related_name='lignes_budget')
    libelle = models.CharField(max_length=200, verbose_name="Ligne budgétaire")
    compte = models.ForeignKey('Compte', on_delete=models.PROTECT, related_name='lignes_budgetaires',
                               help_text="Les dépenses imputées sur ce compte (et ses sous-comptes) s'y rattachent.")
    montant_prevu = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Montant prévu")

    class Meta:
        verbose_name = "Ligne budgétaire de convention"
        ordering = ['compte__numero']


class Versement(ModeleCentre):
    """Argent reçu d'un bailleur au titre d'une convention."""
    MODE = [('virement', 'Virement'), ('cheque', 'Chèque'), ('mobile_money', 'Mobile Money'),
            ('especes', 'Espèces')]
    numero = models.CharField(max_length=20, unique=True, editable=False)
    convention = models.ForeignKey(Convention, on_delete=models.PROTECT, related_name='versements')
    date = models.DateField()
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode = models.CharField(max_length=15, choices=MODE, default='virement')
    reference = models.CharField(max_length=100, blank=True, verbose_name="Référence (n° de virement…)")
    observation = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(Versement.all_objects, 'numero', f'VER{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.montant:,.0f} F".replace(',', ' ')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Versement de bailleur"
        ordering = ['-date', '-pk']


class Don(ModeleCentre):
    """Don reçu, en argent ou en nature (médicaments, matériel…).

    Un don en nature est valorisé : il entre dans les comptes comme un
    actif (stock, matériel) en contrepartie d'une ressource. Un don peut être
    affecté à une convention.
    """
    NATURE = [('especes', 'Espèces'), ('cheque', 'Chèque'), ('virement', 'Virement'),
              ('mobile_money', 'Mobile Money'), ('nature', 'En nature')]
    numero = models.CharField(max_length=20, unique=True, editable=False)
    donateur = models.ForeignKey(Bailleur, on_delete=models.PROTECT, null=True, blank=True, related_name='dons',
                                 help_text="Vide : donateur anonyme ou ponctuel (nom ci-dessous).")
    donateur_nom = models.CharField(max_length=200, blank=True, verbose_name="Nom du donateur")
    date = models.DateField()
    nature = models.CharField(max_length=15, choices=NATURE, default='especes')
    montant = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Montant ou valeur estimée")
    description = models.TextField(blank=True, help_text="Pour un don en nature : ce qui a été reçu, quantités.")
    compte_actif = models.ForeignKey(
        'Compte', on_delete=models.PROTECT, null=True, blank=True, related_name='dons_en_nature',
        verbose_name="Compte de l'actif reçu", help_text="Don en nature : stock de médicaments, matériel…")
    convention = models.ForeignKey(Convention, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='dons', verbose_name="Affecté à la convention")
    reference = models.CharField(max_length=100, blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(Don.all_objects, 'numero', f'DON{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    @property
    def nom_donateur(self):
        return str(self.donateur) if self.donateur_id else (self.donateur_nom or 'Donateur anonyme')

    def __str__(self):
        return f"{self.numero} — {self.nom_donateur}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Don"
        ordering = ['-date', '-pk']


class LigneBudget(models.Model):
    """Budget annuel du centre, par compte (charges et ressources)."""
    exercice = models.ForeignKey('Exercice', on_delete=models.CASCADE, related_name='budget')
    compte = models.ForeignKey('Compte', on_delete=models.PROTECT, related_name='lignes_budget')
    montant = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Montant annuel prévu")

    class Meta:
        verbose_name = "Ligne du budget annuel"
        ordering = ['compte__numero']
        constraints = [models.UniqueConstraint(fields=['exercice', 'compte'], name='une_ligne_de_budget_par_compte')]



# ─── Lot 6 : tiers payants (assurances, mutuelles) ─────────────────────────────

class BordereauAssurance(ModeleCentre):
    """Envoi groupé à un assureur des factures d'une période, pour qu'il règle
    sa part. Une facture ne figure que sur un seul bordereau."""
    STATUT = [('prepare', 'Préparé'), ('envoye', 'Envoyé'), ('regle_partiel', 'Réglé en partie'),
              ('regle', 'Réglé')]
    numero = models.CharField(max_length=20, unique=True, editable=False)
    assurance = models.ForeignKey('patients.Assurance', on_delete=models.PROTECT, related_name='bordereaux')
    date_debut = models.DateField(verbose_name="Factures du")
    date_fin = models.DateField(verbose_name="au")
    statut = models.CharField(max_length=15, choices=STATUT, default='prepare')
    date_envoi = models.DateField(null=True, blank=True, verbose_name="Envoyé le")
    observation = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(BordereauAssurance.all_objects, 'numero', f'BOR{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.assurance}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Bordereau d'assurance"
        verbose_name_plural = "Bordereaux d'assurance"
        ordering = ['-cree_le']


class ReglementAssurance(ModeleCentre):
    """Argent reçu d'un assureur. Il est réparti sur les factures (celles d'un
    bordereau, ou les plus anciennes) sous forme de paiements « Assurance »."""
    MODE = [('virement', 'Virement'), ('cheque', 'Chèque'), ('mobile_money', 'Mobile Money'),
            ('especes', 'Espèces')]
    numero = models.CharField(max_length=20, unique=True, editable=False)
    assurance = models.ForeignKey('patients.Assurance', on_delete=models.PROTECT, related_name='reglements')
    bordereau = models.ForeignKey(BordereauAssurance, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='reglements')
    date = models.DateField()
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode = models.CharField(max_length=15, choices=MODE, default='virement')
    reference = models.CharField(max_length=100, blank=True, verbose_name="Référence (n° de virement, de chèque…)")
    observation = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(ReglementAssurance.all_objects, 'numero', f'REG{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.assurance} — {self.montant:,.0f} F".replace(',', ' ')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Règlement d'assurance"
        verbose_name_plural = "Règlements d'assurance"
        ordering = ['-date', '-pk']



# ─── Lot 7 : trésorerie, rapprochements, refus des assureurs ───────────────────

class CompteTresorerie(models.Model):
    """Compte bancaire ou porte-monnaie Mobile Money du centre, rattaché à son
    compte comptable (classe 5). C'est sur lui qu'on rapproche le relevé."""
    TYPE = [('banque', 'Banque'), ('mobile_money', 'Mobile Money')]
    libelle = models.CharField(max_length=120, unique=True, verbose_name="Libellé")
    type = models.CharField(max_length=15, choices=TYPE, default='banque')
    compte = models.OneToOneField('Compte', on_delete=models.PROTECT, related_name='compte_tresorerie',
                                  verbose_name="Compte comptable")
    etablissement = models.CharField(max_length=120, blank=True, verbose_name="Banque / opérateur")
    numero = models.CharField(max_length=60, blank=True, verbose_name="N° de compte (RIB) ou de téléphone")
    solde_initial = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                        verbose_name="Solde du relevé au départ")
    date_solde_initial = models.DateField(null=True, blank=True, verbose_name="à la date du")
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.libelle

    class Meta:
        verbose_name = "Compte de trésorerie"
        verbose_name_plural = "Comptes de trésorerie"
        ordering = ['libelle']


class RemiseBanque(ModeleCentre):
    """Espèces d'une caisse déposées en banque. Passe par le compte de
    virements internes (585) : sortie de la caisse, puis entrée en banque."""
    numero = models.CharField(max_length=20, unique=True, editable=False)
    date = models.DateField()
    caisse = models.ForeignKey('facturation.Caisse', on_delete=models.PROTECT, related_name='remises_banque')
    compte_tresorerie = models.ForeignKey(CompteTresorerie, on_delete=models.PROTECT, related_name='remises',
                                          verbose_name="Déposé sur")
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, verbose_name="N° du bordereau de versement")
    observation = models.TextField(blank=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(RemiseBanque.all_objects, 'numero', f'REM{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.montant:,.0f} F".replace(',', ' ')

    class Meta(ModeleCentre.Meta):
        verbose_name = "Remise d'espèces en banque"
        verbose_name_plural = "Remises d'espèces en banque"
        ordering = ['-date', '-pk']


class LigneReleve(models.Model):
    """Une ligne du relevé de la banque ou de l'opérateur Mobile Money.

    Montant positif : argent entré sur le compte ; négatif : argent sorti.
    Rapprochée, elle pointe la ligne d'écriture qui lui correspond.
    """
    compte_tresorerie = models.ForeignKey(CompteTresorerie, on_delete=models.CASCADE, related_name='releve')
    date = models.DateField()
    libelle = models.CharField(max_length=255, verbose_name="Libellé")
    reference = models.CharField(max_length=100, blank=True)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    ligne_ecriture = models.OneToOneField('LigneEcriture', on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name='ligne_releve', verbose_name="Rapprochée avec")
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    @property
    def rapprochee(self):
        return self.ligne_ecriture_id is not None

    class Meta:
        verbose_name = "Ligne de relevé"
        verbose_name_plural = "Lignes de relevé"
        ordering = ['date', 'pk']


class RejetAssurance(ModeleCentre):
    """Refus par un assureur de tout ou partie de sa part sur une facture.

    Deux suites possibles : la somme passe à la charge du patient (sa part
    augmente), ou elle est abandonnée et passée en perte.
    """
    DECISION = [('patient', 'Reportée sur le patient'), ('perte', 'Passée en perte')]
    numero = models.CharField(max_length=20, unique=True, editable=False)
    facture = models.ForeignKey('facturation.Facture', on_delete=models.PROTECT, related_name='rejets_assurance')
    assurance = models.ForeignKey('patients.Assurance', on_delete=models.PROTECT, related_name='rejets')
    date = models.DateField()
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    decision = models.CharField(max_length=10, choices=DECISION)
    motif = models.TextField(verbose_name="Motif du refus")
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from core.numerotation import prochain_code
            self.numero = prochain_code(RejetAssurance.all_objects, 'numero', f'REJ{timezone.now().year}', 4)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — facture {self.facture.numero}"

    class Meta(ModeleCentre.Meta):
        verbose_name = "Refus d'assurance"
        verbose_name_plural = "Refus d'assurance"
        ordering = ['-date', '-pk']
