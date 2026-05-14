from django import forms
from django.forms import inlineformset_factory
from .models import (Medecin, Specialite, Diplome, Departement, Service,
                     DocteurReferent, Etiquette, ContactAdresse)


class SpecialiteForm(forms.ModelForm):
    class Meta:
        model = Specialite
        fields = ['nom', 'code', 'description']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Médecine générale'}),
            'code': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : MG'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }


class DepartementForm(forms.ModelForm):
    class Meta:
        model = Departement
        fields = ['nom', 'code', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : MEDECINE GENERALE'}),
            'code': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : MG'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }


class DiplomeForm(forms.ModelForm):
    class Meta:
        model = Diplome
        fields = ['titre', 'description']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Doctorat en médecine'}),
            'description': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Description optionnelle…'}),
        }

_ul = 'field-ul'
_ul_name = 'field-ul field-ul-name'
_ul_prenom = 'field-ul field-ul-prenom'


class MedecinForm(forms.ModelForm):
    class Meta:
        model = Medecin
        exclude = ['code', 'date_creation', 'matricule', 'taux_honoraire']
        widgets = {
            'nom': forms.TextInput(attrs={'class': _ul_name, 'placeholder': 'Nom'}),
            'prenoms': forms.TextInput(attrs={'class': _ul_prenom, 'placeholder': 'Prénom(s)'}),
            'fonction': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ex : Directeur Médical'}),
            'diplome': forms.Select(attrs={'class': _ul}),
            'specialite': forms.Select(attrs={'class': _ul}),
            'service_consultation': forms.Select(attrs={'class': _ul}),
            'service_suivi': forms.Select(attrs={'class': _ul}),
            'ordre_medecin': forms.TextInput(attrs={'class': _ul, 'placeholder': 'N° d\'ordre'}),
            'duree_consultation': forms.NumberInput(attrs={
                'class': _ul, 'min': '5', 'step': '5',
            }),
            'telephone': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'mobile': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': _ul, 'placeholder': 'exemple@email.com'}),
            'adresse': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Adresse complète...'}),
            'tva_numero_fiscal': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Numéro fiscal / TVA'}),
            'user': forms.Select(attrs={'class': _ul}),
            'departements': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prenoms'].required = False
        self.fields['specialite'].queryset = Specialite.objects.all()
        self.fields['specialite'].empty_label = '— Choisir une spécialité —'
        self.fields['specialite'].required = False
        self.fields['diplome'].queryset = Diplome.objects.all()
        self.fields['diplome'].empty_label = '— Niveau d\'éducation —'
        self.fields['diplome'].required = False
        self.fields['departements'].queryset = Departement.objects.filter(actif=True)
        self.fields['departements'].required = False
        self.fields['service_consultation'].queryset = Service.objects.filter(actif=True)
        self.fields['service_consultation'].empty_label = '— Choisir un service —'
        self.fields['service_consultation'].required = False
        self.fields['service_suivi'].queryset = Service.objects.filter(actif=True)
        self.fields['service_suivi'].empty_label = '— Choisir un service —'
        self.fields['service_suivi'].required = False
        self.fields['user'].required = False
        self.fields['user'].empty_label = '— Aucun compte —'
        if not self.instance.pk:
            self.fields['duree_consultation'].initial = 15
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'invalid': 'Valeur invalide.',
            }


class DocteurReferentForm(forms.ModelForm):
    class Meta:
        model = DocteurReferent
        exclude = ['code', 'date_creation']
        widgets = {
            'type_contact': forms.RadioSelect(),
            'titre': forms.Select(attrs={'class': _ul}),
            'nom': forms.TextInput(attrs={'class': _ul_name, 'placeholder': 'Nom / Raison sociale'}),
            'prenoms': forms.TextInput(attrs={'class': _ul_prenom, 'placeholder': 'Prénom(s)'}),
            'poste_occupe': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ex : Directeur Médical'}),
            'specialite': forms.Select(attrs={'class': _ul}),
            'etablissement': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Hôpital / Clinique'}),
            'telephone': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'mobile': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': _ul, 'placeholder': 'exemple@email.com'}),
            'site_web': forms.URLInput(attrs={'class': _ul, 'placeholder': 'https://...'}),
            'langue': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Français'}),
            'etiquettes': forms.CheckboxSelectMultiple(),
            'adresse': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Adresse complète...'}),
            'tva': forms.TextInput(attrs={'class': _ul, 'placeholder': 'N° TVA / Fiscal'}),
            'notes': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Notes internes…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['specialite'].queryset = Specialite.objects.all()
        self.fields['specialite'].empty_label = '— Choisir une spécialité —'
        self.fields['specialite'].required = False
        self.fields['prenoms'].required = False
        self.fields['etiquettes'].queryset = Etiquette.objects.all()
        self.fields['etiquettes'].required = False
        self.fields['medecin_interne'].queryset = Medecin.objects.filter(actif=True)
        self.fields['medecin_interne'].empty_label = '— Aucun —'
        self.fields['medecin_interne'].required = False
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'invalid': 'Valeur invalide.',
            }


class ContactAdresseForm(forms.ModelForm):
    class Meta:
        model = ContactAdresse
        fields = ['type_adresse', 'nom', 'telephone', 'email', 'adresse']
        widgets = {
            'type_adresse': forms.Select(attrs={'class': _ul}),
            'nom': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Nom du contact'}),
            'telephone': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': _ul, 'placeholder': 'email@exemple.com'}),
            'adresse': forms.Textarea(attrs={'class': _ul, 'rows': 2, 'placeholder': 'Adresse…'}),
        }


ContactAdresseFormSet = inlineformset_factory(
    DocteurReferent, ContactAdresse,
    form=ContactAdresseForm,
    extra=0, can_delete=True,
)
