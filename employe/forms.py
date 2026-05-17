from django import forms
from django.forms import inlineformset_factory
from .models import Employe, Specialite, Diplome, Departement, DocteurReferent, Etiquette, ContactAdresse
from services.models import Articleservice


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


class EmployeEducationForm(forms.ModelForm):
    class Meta:
        model = Employe
        fields = ['diplome', 'etablissement']
        widgets = {
            'diplome': forms.Select(attrs={'class': 'field-ul'}),
            'etablissement': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Université, École…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diplome'].queryset = Diplome.objects.all()
        self.fields['diplome'].empty_label = "— Niveau d'éducation —"
        self.fields['diplome'].required = False
        self.fields['etablissement'].required = False

_ul = 'field-ul'
_ul_name = 'field-ul field-ul-name'
_ul_prenom = 'field-ul field-ul-prenom'


class EmployeForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={
            'class': _ul, 'autocomplete': 'off',
            'placeholder': 'Identifiant de connexion',
        }),
        label="Identifiant d'accès"
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': _ul, 'autocomplete': 'new-password',
            'placeholder': '••••••••',
        }),
        label='Mot de passe'
    )
    current_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': _ul, 'autocomplete': 'current-password',
            'placeholder': '••••••••',
        }),
        label='Mot de passe actuel'
    )
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': _ul, 'autocomplete': 'new-password',
            'placeholder': '••••••••',
        }),
        label='Nouveau mot de passe'
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': _ul, 'autocomplete': 'new-password',
            'placeholder': '••••••••',
        }),
        label='Confirmer le mot de passe'
    )

    class Meta:
        model = Employe
        exclude = ['code', 'date_creation', 'taux_honoraire', 'user']
        widgets = {
            'nom': forms.TextInput(attrs={'class': _ul_name, 'placeholder': 'Nom'}),
            'prenoms': forms.TextInput(attrs={'class': _ul_prenom, 'placeholder': 'Prénom(s)'}),
            'matricule': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ex : MAT2025001'}),
            'genre': forms.Select(attrs={'class': _ul}),
            'titre': forms.Select(attrs={'class': _ul}),
            'date_naissance': forms.DateInput(attrs={'class': _ul, 'type': 'date'}),
            'lieu_naissance': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ville, Pays'}),
            'fonction': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ex : Infirmier, Médecin, Aide-soignant…'}),
            'diplome': forms.Select(attrs={'class': _ul}),
            'specialite': forms.Select(attrs={'class': _ul}),
            'service_consultation': forms.Select(attrs={'class': _ul}),
            'service_suivi': forms.Select(attrs={'class': _ul}),
            'ordre_medecin': forms.TextInput(attrs={'class': _ul, 'placeholder': "N° d'ordre"}),
            'duree_consultation': forms.NumberInput(attrs={'class': _ul, 'min': '5', 'step': '5'}),
            'telephone': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'mobile': forms.TextInput(attrs={'class': _ul, 'placeholder': '+225 07 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': _ul, 'placeholder': 'exemple@email.com'}),
            'adresse': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': "Lieu d'habitation…"}),
            'tva_numero_fiscal': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Numéro fiscal / TVA'}),
            'etablissement': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Hôpital / Clinique'}),
            'nationalite': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Ex : Ivoirienne'}),
            'langue': forms.TextInput(attrs={'class': _ul, 'placeholder': 'Français'}),
            'notes_internes': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Notes internes…'}),
            'departements': forms.CheckboxSelectMultiple(),
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.user:
            self.fields['username'].initial = self.instance.user.username
        self.fields['prenoms'].required = False
        self.fields['matricule'].required = False
        self.fields['specialite'].queryset = Specialite.objects.all()
        self.fields['specialite'].empty_label = '— Choisir une spécialité —'
        self.fields['specialite'].required = False
        self.fields['diplome'].queryset = Diplome.objects.all()
        self.fields['diplome'].empty_label = "— Niveau d'éducation —"
        self.fields['diplome'].required = False
        self.fields['departements'].queryset = Departement.objects.filter(actif=True)
        self.fields['departements'].required = False
        self.fields['service_consultation'].queryset = Articleservice.objects.filter(actif=True).order_by('nom')
        self.fields['service_consultation'].empty_label = '— Choisir un service —'
        self.fields['service_consultation'].required = False
        self.fields['service_suivi'].queryset = Articleservice.objects.filter(actif=True).order_by('nom')
        self.fields['service_suivi'].empty_label = '— Choisir un service —'
        self.fields['service_suivi'].required = False
        if not self.instance.pk:
            self.fields['duree_consultation'].initial = 15
            self.fields['actif'].initial = False
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
            'genre': forms.Select(attrs={'class': _ul}),
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
        self.fields['medecin_interne'].queryset = Employe.objects.filter(actif=True)
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
