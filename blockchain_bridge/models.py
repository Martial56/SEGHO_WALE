from django.db import models


class AncrageBlockchain(models.Model):
    """Preuve d'ancrage blockchain d'un enregistrement Django : le hash placé
    sur le registre partagé (voir blockchain/README.md), jamais les données
    elles-mêmes. Une ligne par événement soumis à IntegriteContract.

    Versionnement : chaque modification d'un enregistrement déjà ancré donne
    lieu à une nouvelle version (1, 2, 3…), ancrée sous un nouvel identifiant
    d'événement ; les versions antérieures restent sur le registre et
    constituent l'historique des modifications."""

    TYPE_ENTITE = [
        ('patient', 'Patient'),
        ('consultation', 'Consultation'),
        ('ordonnance', 'Ordonnance'),
        ('facture', 'Facture'),
        ('paiement', 'Paiement'),
        ('echange_hprim', 'Échange HPRIM (laboratoire)'),
        ('analyse_laboratoire', 'Analyse laboratoire'),
    ]
    STATUT = [
        ('en_attente', 'En attente'),
        ('confirme', 'Confirmé'),
        ('erreur', 'Erreur'),
    ]

    id_evenement = models.CharField(max_length=64, unique=True, editable=False)
    type_entite = models.CharField(max_length=20, choices=TYPE_ENTITE)
    id_entite = models.CharField(max_length=50, verbose_name="Code de l'entité")
    version = models.PositiveIntegerField(default=1, verbose_name='Version')
    code_patient = models.CharField(max_length=20, blank=True)
    code_centre = models.CharField(max_length=20, blank=True)
    empreinte_hash = models.CharField(max_length=64, editable=False, verbose_name='Empreinte (SHA-256)')
    tx_id = models.CharField(max_length=100, blank=True, editable=False, verbose_name='ID transaction')
    statut = models.CharField(max_length=20, choices=STATUT, default='en_attente')
    erreur_message = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_confirmation = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_type_entite_display()} {self.id_entite} v{self.version} — {self.get_statut_display()}"

    class Meta:
        verbose_name = 'Ancrage blockchain'
        ordering = ['-date_creation']
        constraints = [
            models.UniqueConstraint(fields=['type_entite', 'id_entite', 'version'], name='ancrage_version_unique'),
        ]
