from django import forms
from django.db.models import Q
from .models import Soin, ProcedureSoin
from patients.models import Patient, RendezVous, Pathologie
from employer.models import Employe
from medecins.models import Departement
from services.models import Articleservice
from facturation.models import Facture


def _patients_du_centre(instance=None):
    """Patients visibles, recalculés à chaque requête.

    Un `queryset=` écrit dans le corps d'une classe de formulaire est évalué à
    l'import du module, donc hors requête : le manager de `Patient` n'y voit
    aucun centre actif et fige la liste sur « centre_id IS NULL ». Les deux
    sélecteurs de patient du module étaient donc toujours vides. Appelée depuis
    `__init__`, cette fonction voit le centre actif.

    En modification, le patient déjà enregistré reste dans la liste même s'il
    relève d'un autre centre : sans cela, réenregistrer la fiche l'effacerait.
    """
    qs = Patient.objects.all()
    patient_id = instance.patient_id if instance is not None and instance.pk else None
    if patient_id:
        qs = Patient.all_objects.filter(Q(pk__in=qs.values('pk')) | Q(pk=patient_id))
    return qs.order_by('nom', 'prenoms')


class SoinForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        # Liste réelle posée dans __init__ (voir _patients_du_centre).
        queryset=Patient.objects.none(),
        empty_label="— Sélectionner un patient —",
        error_messages={'required': 'Le patient est obligatoire.'},
    )
    date_guerison = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = _patients_du_centre(self.instance)

    class Meta:
        model = Soin
        # `nom` et `hospitalisation` ne sont volontairement plus là : aucun des
        # deux n'a de champ dans le gabarit, donc le navigateur ne les postait
        # pas et Django les vidait à chaque enregistrement. `nom` n'est lu nulle
        # part dans l'application ; `hospitalisation` est un lien technique posé
        # par le module d'hospitalisation, qu'un enregistrement depuis cet écran
        # effaçait silencieusement. Les retirer préserve les deux valeurs.
        fields = [
            'patient', 'motif',
            'observations', 'statut',
            'statut_maladie', 'severite', 'date_guerison',
            'maladie_infectieuse', 'maladie_allergique', 'lactation', 'avertissement_grossesse',
        ]
        widgets = {
            'motif': forms.TextInput(),
            'observations': forms.Textarea(attrs={'rows': 4}),
        }


class ProcedureSoinForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        # Liste réelle posée dans __init__ (voir _patients_du_centre).
        queryset=Patient.objects.none(),
        empty_label="— Sélectionner un patient —",
        error_messages={'required': 'Le patient est obligatoire.'},
    )
    infirmier = forms.ModelChoiceField(
        queryset=Employe.objects.order_by('nom', 'prenoms'),
        required=False,
        empty_label="— Sélectionner un infirmier —",
    )
    soin_type = forms.ModelChoiceField(
        queryset=Articleservice.objects.filter(
            type_article__in=['service', 'prestation']
        ).order_by('nom'),
        required=False,
        empty_label="— Sélectionner un soin —",
        label="Soin",
    )
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.filter(actif=True).order_by('nom'),
        required=False,
        empty_label="— Sélectionner un département —",
    )
    maladie = forms.ModelChoiceField(
        queryset=Pathologie.objects.filter(actif=True),
        required=False,
        empty_label="— Sélectionner une maladie —",
    )
    rendez_vous = forms.ModelChoiceField(
        # Liste réelle posée dans __init__ : RendezVous est cloisonné, un
        # queryset écrit ici serait évalué à l'import, hors requête, et resterait
        # vide (voir _patients_du_centre).
        queryset=RendezVous.objects.none(),
        required=False,
        empty_label="— Aucun rendez-vous lié —",
    )
    facture = forms.ModelChoiceField(
        queryset=Facture.objects.order_by('-date_emission'),
        required=False,
        empty_label="— Aucune facture liée —",
    )
    date = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        error_messages={'required': "La date est obligatoire."},
    )

    #: Le patient ne se change jamais après création, pas même pour un
    #: administrateur : rattacher l'acte à quelqu'un d'autre reviendrait à
    #: réécrire le dossier médical de deux personnes d'un coup. Pour corriger
    #: une erreur de saisie, on annule la procédure et on en refait une.
    FIGE_TOUJOURS = ('patient',)

    #: Verrous levables par qui en a le droit. La date est un fait constaté ;
    #: la facture est créée par le système au passage « en cours » et la
    #: rattacher à la main désynchroniserait la comptabilité.
    FIGES_APRES_CREATION = ('date', 'facture')

    #: Ce qui a été facturé ne bouge plus : changer le type de soin laisserait
    #: la facture sur l'ancien montant.
    FIGES_SI_FACTURE = ('soin_type', 'prix')

    #: Une procédure close ne se modifie plus — sauf par l'administration.
    STATUTS_CLOS = ('termine', 'annule')

    def __init__(self, *args, **kwargs):
        #: Lève tous les verrous sauf FIGE_TOUJOURS. Les vues y passent
        #: `request.user.is_superuser`, comme le fait déjà soins_edit pour un
        #: soin hors brouillon.
        self.peut_tout_modifier = kwargs.pop('peut_tout_modifier', False)
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = _patients_du_centre(self.instance)
        self._restreindre_rendez_vous()
        self._restreindre_factures()
        self._figer_champs()

    def _restreindre_rendez_vous(self):
        """Rendez-vous proposés : ceux du patient de la fiche, sinon ceux du
        centre actif.

        Même raison que pour les factures : le gabarit rend le queryset entier
        dans le HTML, et un acte se rattache au rendez-vous de son patient, pas
        à n'importe lequel. Le rendez-vous déjà lié est conservé même s'il
        relève d'un autre dossier, sinon réenregistrer la fiche l'effacerait.
        """
        proc = self.instance
        if proc and proc.pk and proc.patient_id:
            condition = Q(patient_id=proc.patient_id)
            if proc.rendez_vous_id:
                condition |= Q(pk=proc.rendez_vous_id)
            qs = RendezVous.all_objects.filter(condition)
        else:
            qs = RendezVous.objects.all()
        self.fields['rendez_vous'].queryset = (
            qs.select_related('patient').order_by('-date_heure'))

    def _restreindre_factures(self):
        """Limite la liste des factures à celles du patient de la fiche.

        Le gabarit rend le queryset en entier dans le HTML : les 536 factures du
        système pesaient 94 Ko par ouverture de page, pour un champ que le
        JavaScript réduisait ensuite aux seules factures du patient. Autant le
        faire côté serveur, où l'on connaît déjà le patient. La facture déjà
        rattachée est conservée même si elle relève d'un autre dossier, sinon
        réenregistrer la fiche l'effacerait.
        """
        proc = self.instance
        if not (proc and proc.pk and proc.patient_id):
            return
        qs = Facture.objects.filter(patient_id=proc.patient_id)
        if proc.facture_id:
            qs = Facture.objects.filter(Q(patient_id=proc.patient_id) | Q(pk=proc.facture_id))
        self.fields['facture'].queryset = qs.order_by('-date_emission')

    def _figer_champs(self):
        """Verrouille les champs non modifiables, côté serveur.

        `disabled` plutôt qu'un simple `readonly` dans le gabarit : Django
        ignore alors purement et simplement la valeur reçue et reprend celle de
        l'enregistrement. Un formulaire trafiqué ne peut donc rien changer, et
        le gabarit n'a plus qu'à refléter la règle — il la lit sur
        `form.<champ>.field.disabled` au lieu de la redéfinir de son côté.
        """
        proc = self.instance
        if not (proc and proc.pk):
            return                      # en création, tout est ouvert

        figes = set(self.FIGE_TOUJOURS)

        if not self.peut_tout_modifier:
            if proc.statut in self.STATUTS_CLOS:
                figes = set(self.fields)
            else:
                figes |= set(self.FIGES_APRES_CREATION)
                if proc.facture_id:
                    figes |= set(self.FIGES_SI_FACTURE)

        for nom in figes:
            if nom in self.fields:
                self.fields[nom].disabled = True

    class Meta:
        model = ProcedureSoin
        fields = [
            'patient', 'infirmier', 'soin_type', 'prix',
            # `rendez_vous` n'est volontairement pas listé : son bloc est en
            # {% comment %} dans le gabarit, le navigateur ne le poste donc pas
            # et Django effaçait le lien à chaque enregistrement. À remettre ici
            # en même temps qu'on réactivera le bloc du formulaire — le champ et
            # son queryset (voir _restreindre_rendez_vous) restent prêts.
            'departement', 'date', 'maladie', 'facture',
        ]
        widgets = {
            'prix': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
