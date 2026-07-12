from django import forms
from .models import Soin, ProcedureSoin
from patients.models import Patient, RendezVous, Pathologie
from employer.models import Employe
from medecins.models import Departement
from services.models import Articleservice
from facturation.models import Facture


class SoinForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        queryset=Patient.objects.order_by('nom', 'prenoms'),
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
        from hospitalisation.models import Hospitalisation
        self.fields['hospitalisation'].queryset = Hospitalisation.objects.select_related(
            'patient'
        ).order_by('-date_admission')
        self.fields['hospitalisation'].empty_label = "— Aucune hospitalisation liée —"
        self.fields['hospitalisation'].required = False
        self.fields['hospitalisation'].label_from_instance = lambda h: (
            f"{h.numero} — {h.patient.nom} {h.patient.prenoms}"
        )

    class Meta:
        model = Soin
        fields = [
            'nom', 'patient', 'motif',
            'observations', 'statut',
            'statut_maladie', 'severite', 'date_guerison',
            'maladie_infectieuse', 'maladie_allergique', 'lactation', 'avertissement_grossesse',
            'hospitalisation',
        ]
        widgets = {
            'motif': forms.TextInput(),
            'observations': forms.Textarea(attrs={'rows': 4}),
        }


class ProcedureSoinForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        queryset=Patient.objects.order_by('nom', 'prenoms'),
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
        queryset=RendezVous.objects.select_related('patient').order_by('-date_heure'),
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

    class Meta:
        model = ProcedureSoin
        fields = [
            'patient', 'infirmier', 'soin_type', 'prix',
            'departement', 'date', 'maladie', 'rendez_vous', 'facture',
        ]
        widgets = {
            'prix': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
