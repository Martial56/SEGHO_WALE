from django import forms
from .models import Soin, ProcedureSoin, Maladie
from patients.models import Patient, RendezVous
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
    infirmier = forms.ModelChoiceField(
        queryset=Employe.objects.order_by('nom', 'prenoms'),
        required=False,
        empty_label="— Sélectionner un agent —",
    )
    rendez_vous = forms.ModelChoiceField(
        queryset=RendezVous.objects.select_related('patient').order_by('-date_heure'),
        required=False,
        empty_label="— Aucun rendez-vous lié —",
    )
    departement = forms.ModelChoiceField(
        queryset=Departement.objects.order_by('nom'),
        required=True,
        empty_label="— Département —",
        error_messages={'required': 'Le département est obligatoire.'},
    )
    service_inscription = forms.ModelChoiceField(
        queryset=Articleservice.objects.filter(
            type_article__in=['service', 'prestation']
        ).order_by('nom'),
        required=False,
        empty_label="— Sélectionner un service —",
    )
    date_heure = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        error_messages={'required': "La date et l'heure sont obligatoires."},
    )
    date_guerison = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = Soin
        fields = [
            'nom', 'patient', 'infirmier', 'rendez_vous', 'date_heure', 'motif',
            'observations', 'statut', 'departement', 'service_inscription',
            'statut_maladie', 'severite', 'date_guerison',
            'maladie_infectieuse', 'maladie_allergique', 'lactation', 'avertissement_grossesse',
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
        queryset=Departement.objects.order_by('nom'),
        required=False,
        empty_label="— Sélectionner un département —",
    )
    maladie = forms.ModelChoiceField(
        queryset=Maladie.objects.all(),
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


class MaladieForm(forms.ModelForm):
    class Meta:
        model = Maladie
        fields = ['nom', 'code_cim', 'description']
        widgets = {
            'nom': forms.TextInput(attrs={'placeholder': 'Nom de la maladie…'}),
            'code_cim': forms.TextInput(attrs={'placeholder': 'Ex: J06.9'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }
