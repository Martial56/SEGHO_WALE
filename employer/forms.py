from django import forms
from .models import Fonction, Grade, TypeContrat


class FonctionForm(forms.ModelForm):
    class Meta:
        model = Fonction
        fields = ['nom', 'code', 'description']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex. Médecin généraliste'}),
            'code':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex. MED'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ['nom', 'code', 'description']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex. Médecin chef'}),
            'code':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex. MC'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }


class TypeContratForm(forms.ModelForm):
    class Meta:
        model = TypeContrat
        fields = ['nom', 'description', 'droit_au_conge']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex. CDI'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }
