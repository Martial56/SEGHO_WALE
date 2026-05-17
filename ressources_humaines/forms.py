from django import forms
from .models import Employe, Poste, Conge


class PosteForm(forms.ModelForm):
    class Meta:
        model = Poste
        fields = ['nom', 'code', 'service']
        widgets = {
            'nom':     forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Nom du poste…'}),
            'code':    forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'ex : INF01'}),
            'service': forms.Select(attrs={'class': 'field-ul'}),
        }


class EmployeForm(forms.ModelForm):
    class Meta:
        model = Employe
        fields = [
            'matricule', 'nom', 'prenoms', 'poste',
            'telephone', 'email',
            'date_embauche', 'date_fin_contrat',
            'salaire_base', 'statut',
        ]
        widgets = {
            'matricule':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'ex : EMP001'}),
            'nom':              forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Nom de famille'}),
            'prenoms':          forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Prénoms'}),
            'poste':            forms.Select(attrs={'class': 'field-ul'}),
            'telephone':        forms.TextInput(attrs={'class': 'field-ul', 'placeholder': '+225 …'}),
            'email':            forms.EmailInput(attrs={'class': 'field-ul', 'placeholder': 'email@exemple.com'}),
            'date_embauche':    forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'date_fin_contrat': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'salaire_base':     forms.NumberInput(attrs={'class': 'field-ul', 'min': '0', 'step': '1'}),
            'statut':           forms.Select(attrs={'class': 'field-ul'}),
        }


class CongeForm(forms.ModelForm):
    class Meta:
        model = Conge
        fields = ['employe', 'type_conge', 'date_debut', 'date_fin', 'motif', 'statut', 'approuve_par']
        widgets = {
            'employe':      forms.Select(attrs={'class': 'field-ul'}),
            'type_conge':   forms.Select(attrs={'class': 'field-ul'}),
            'date_debut':   forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'date_fin':     forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'motif':        forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Motif…'}),
            'statut':       forms.Select(attrs={'class': 'field-ul'}),
            'approuve_par': forms.Select(attrs={'class': 'field-ul'}),
        }
