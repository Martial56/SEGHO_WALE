from django import forms
from .models import Specialite, Service, Medecin


class SpecialiteForm(forms.ModelForm):
    class Meta:
        model = Specialite
        fields = ['nom', 'code', 'description']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Nom de la spécialité…'}),
            'code':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex: CARD, PEDIA…'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }


class ServiceForm(forms.ModelForm):
    chef_service = forms.ModelChoiceField(
        queryset=Medecin.objects.filter(actif=True).order_by('nom', 'prenoms'),
        required=False,
        empty_label='— Aucun chef de service —',
    )

    class Meta:
        model = Service
        fields = ['nom', 'code', 'description', 'chef_service', 'actif']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Nom du service…'}),
            'code':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex: URGENCES, PEDIA…'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }
