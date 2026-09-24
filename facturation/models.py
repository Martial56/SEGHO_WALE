from django.db import models
from django.contrib.auth.models import User

from centres.models import ModeleCentre


class Acte(models.Model):
    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=300)
    categorie = models.CharField(max_length=100, blank=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    actif = models.BooleanField(default=True)

    def __str__(self): return f"{self.code} - {self.libelle}"
    class Meta: verbose_name = "Acte médical"


class Facture(ModeleCentre):
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
            # all_objects : le numéro reste unique tous centres confondus. Le
            # compter sur `objects`, cloisonné, redonnerait un numéro déjà pris
            # dans l'autre centre.
            count = Facture.all_objects.count() + 1
            numero = f"VTES/{annee}/{date_part}{count:04d}"
            while Facture.all_objects.filter(numero=numero).exists():
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
    class Meta(ModeleCentre.Meta):
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


class Paiement(ModeleCentre):
    MODE = [('especes','Espèces'),('cheque','Chèque'),('mobile_money','Mobile Money'),('virement','Virement'),('assurance','Assurance'),('bon','Bon')]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODE)
    # Où l'argent est entré. Le champ « Journal » des écrans d'encaissement
    # existait déjà, mais le navigateur ne l'envoyait pas et le serveur ne le
    # lisait pas : le choix du caissier était perdu, et aucun paiement ne savait
    # de quelle caisse il relevait. SET_NULL plutôt que CASCADE — supprimer une
    # caisse ne doit pas effacer les encaissements passés par elle.
    caisse = models.ForeignKey(
        'facturation.Caisse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paiements', verbose_name="Caisse")
    # Ce que le patient a tendu, quand il a payé en espèces. `montant` reste ce
    # qui était dû : compter le billet entier gonflerait la caisse de la monnaie
    # rendue. Nul sur les autres modes, où il n'y a pas de monnaie.
    montant_recu = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name="Montant reçu")
    reference = models.CharField(max_length=100, blank=True)
    date_paiement = models.DateTimeField(auto_now_add=True)
    recu_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            annee = timezone.now().year
            prefix = f"PAI{annee}"
            # all_objects : voir Facture.save — le numéro est unique tous
            # centres confondus.
            last = Paiement.all_objects.filter(numero__startswith=prefix).order_by('-pk').first()
            count = (int(last.numero[len(prefix):]) + 1) if last else 1
            self.numero = f"{prefix}{count:07d}"
        super().save(*args, **kwargs)

    @property
    def monnaie_rendue(self):
        """Différence entre ce qui a été tendu et ce qui était dû.

        None quand rien n'a été saisi — les paiements antérieurs à ce champ, et
        tous ceux qui ne sont pas en espèces. Jamais négatif : un patient qui
        donne moins que le dû ne se voit pas rendre de monnaie, la facture
        reste simplement partiellement réglée.
        """
        if self.montant_recu is None:
            return None
        return max(self.montant_recu - self.montant, 0)

    def __str__(self): return f"Paiement {self.numero} - {self.montant} F"
    class Meta(ModeleCentre.Meta):
        verbose_name = "Paiement"
        ordering = ['-date_paiement']


class Caisse(models.Model):
    """Journal d'encaissement — « où l'argent est entré ».

    Venait de l'application `caisse`, supprimée : elle ne servait plus qu'à
    fournir cette liste, ses deux autres tables (sessions et transactions)
    n'ayant jamais reçu une seule ligne. Le modèle vit désormais là où il est
    lu, à côté de `Facture` et `Paiement`.

    Volontairement pas un `ModeleCentre` : une caisse n'appartient pas à un
    centre, elle en désigne un (« Caisse Toumbokro »).
    """

    nom = models.CharField(max_length=100, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    actif = models.BooleanField(default=True, verbose_name="Active")
    # Codes séparés par des virgules, pris dans `Paiement.MODE`. Une liste
    # plutôt qu'une table de liaison : les modes sont une énumération figée du
    # code, pas une donnée que l'utilisateur ajoute.
    modes_paiement = models.CharField(
        max_length=200, blank=True, default='especes',
        verbose_name="Modes de paiement acceptés")

    def __str__(self): return self.nom

    #: Mode retenu quand une caisse n'en déclare aucun. Une caisse qui
    #: n'accepterait rien ne serait pas une caisse, et l'espèce est le cas
    #: courant au guichet.
    MODE_PAR_DEFAUT = 'especes'

    @property
    def modes(self):
        """Codes des modes acceptés, dans l'ordre de `Paiement.MODE`.

        Seuls les modes cochés sont proposés à l'encaissement. Les codes
        inconnus — un mode retiré du modèle depuis — sont écartés au passage.
        """
        choisis = {m for m in self.modes_paiement.split(',') if m}
        retenus = [code for code, _ in Paiement.MODE if code in choisis]
        return retenus or [self.MODE_PAR_DEFAUT]

    @property
    def modes_libelles(self):
        libelles = dict(Paiement.MODE)
        return [libelles[code] for code in self.modes]

    @property
    def total_encaisse(self):
        """Somme des paiements passés par cette caisse.

        Calculé, et non stocké : le champ `solde_actuel` qu'il remplace n'était
        écrit par aucun code. Ses quatre valeurs totalisaient 1 326 040 F quand
        l'ensemble des paiements jamais enregistrés en pesait 79 701 — seize
        fois moins. Un nombre que personne ne tient finit toujours par mentir.

        « Total encaissé » et non « solde » : une caisse a aussi un fonds de
        départ, des sorties, des versements en banque, dont l'application ne
        sait rien. Promettre un solde serait promettre plus qu'on ne tient.

        La vue de liste pose l'annotation `total` pour éviter une requête par
        ligne ; cette propriété sert les appels isolés.
        """
        from django.db.models import Sum
        # all_objects : `self.paiements` passe par le gestionnaire filtré par
        # centre, qui ne rend rien hors d'une requête HTTP — le total serait 0
        # dans un shell ou une commande. L'annotation de la vue de liste compte
        # elle aussi tous les centres, les deux chiffres doivent concorder.
        return Paiement.all_objects.filter(caisse=self).aggregate(
            s=Sum('montant'))['s'] or 0

    class Meta:
        verbose_name = "Caisse"
        verbose_name_plural = "Caisses"
        ordering = ['nom']
        # Libellés français : l'écran d'attribution des droits aux groupes
        # affiche ces textes tels quels. Même parti pris que sur hospitalisation
        # et soins — `default_permissions = ()` empêche Django d'ajouter en plus
        # ses quatre entrées anglaises.
        default_permissions = ()
        permissions = [
            ('view_caisse', 'Peut consulter les caisses'),
            ('add_caisse', 'Peut créer une caisse'),
            ('change_caisse', 'Peut modifier une caisse'),
            ('delete_caisse', 'Peut supprimer une caisse'),
        ]
