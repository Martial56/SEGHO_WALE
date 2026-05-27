from django import forms
from django.forms import inlineformset_factory
from employer.models import Employe, Specialite, Diplome, Departement, DocteurReferent, Etiquette, ContactAdresse, DiplomePersonnel
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


class DiplomePersonnelForm(forms.ModelForm):
    class Meta:
        model = DiplomePersonnel
        fields = ['titre', 'etablissement', 'annee']
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Doctorat en médecine'}),
            'etablissement': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Université, École…'}),
            'annee': forms.NumberInput(attrs={'class': 'field-ul', 'min': '1950'}),
        }

    def __init__(self, *args, **kwargs):
        from django.utils import timezone
        super().__init__(*args, **kwargs)
        self.fields['etablissement'].required = False
        current_year = timezone.now().year
        self.fields['annee'].required = False
        self.fields['annee'].widget.attrs['max'] = current_year
        self.fields['annee'].widget.attrs['placeholder'] = f'Ex : {current_year - 2}'
        for field in self.fields.values():
            field.error_messages = {'required': 'Ce champ est obligatoire.', 'invalid': 'Valeur invalide.'}

    def clean_annee(self):
        from django.utils import timezone
        annee = self.cleaned_data.get('annee')
        current_year = timezone.now().year
        if annee and annee > current_year:
            raise forms.ValidationError(f"L'année d'obtention ne peut pas être supérieure à {current_year}.")
        return annee


class EmployeEducationForm(forms.ModelForm):
    class Meta:
        model = Employe
        fields = ['etablissement']
        widgets = {
            'etablissement': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Université, École…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        self.fields['medecin_interne'].queryset = Employe.objects.filter(statut='actif')
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


# ── Profil self-service (employer.Employe) ───────────────────────────────────

class EmployeProfilForm(forms.ModelForm):
    """Formulaire de modification du profil par l'employé lui-même."""
    class Meta:
        from employer.models import Employe as _EmpRH
        model = _EmpRH
        fields = [
            'nom', 'prenoms', 'sexe', 'date_naissance', 'lieu_naissance',
            'nationalite', 'situation_matrimoniale', 'nombre_enfants',
            'photo', 'telephone', 'telephone2', 'email', 'adresse',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Nom de famille'}),
            'prenoms': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Prénom(s)'}),
            'sexe': forms.Select(attrs={'class': 'field-ul'}),
            'date_naissance': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'lieu_naissance': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ville, Pays'}),
            'nationalite': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Ivoirienne'}),
            'situation_matrimoniale': forms.Select(attrs={'class': 'field-ul'}),
            'nombre_enfants': forms.NumberInput(attrs={'class': 'field-ul', 'min': '0'}),
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
            'telephone': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': '+225 07 00 00 00 00'}),
            'telephone2': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': '+225 07 00 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': 'field-ul', 'placeholder': 'exemple@email.com'}),
            'adresse': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': "Lieu d'habitation…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prenoms'].required = False
        self.fields['sexe'].required = False
        self.fields['date_naissance'].required = False
        self.fields['lieu_naissance'].required = False
        self.fields['nationalite'].required = False
        self.fields['situation_matrimoniale'].required = False
        self.fields['telephone'].required = False
        self.fields['telephone2'].required = False
        self.fields['email'].required = False
        self.fields['adresse'].required = False
        self.fields['photo'].required = False
        for field in self.fields.values():
            field.error_messages = {'required': 'Ce champ est obligatoire.', 'invalid': 'Valeur invalide.'}


class EmployeProfilAdminForm(EmployeProfilForm):
    """Formulaire admin : mêmes champs personnels + champs RH éditables."""
    class Meta(EmployeProfilForm.Meta):
        from employer.models import Employe as _EmpRH
        model = _EmpRH
        fields = [
            'nom', 'prenoms', 'sexe', 'date_naissance', 'lieu_naissance',
            'nationalite', 'situation_matrimoniale', 'nombre_enfants',
            'photo', 'telephone', 'telephone2', 'email', 'adresse',
            'matricule', 'fonction', 'grade', 'type_contrat',
            'statut', 'date_embauche', 'date_fin_contrat', 'notes',
        ]
        widgets = {
            **EmployeProfilForm.Meta.widgets,
            'matricule': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Généré automatiquement si vide'}),
            'fonction': forms.Select(attrs={'class': 'field-ul'}),
            'grade': forms.Select(attrs={'class': 'field-ul'}),
            'type_contrat': forms.Select(attrs={'class': 'field-ul'}),
            'statut': forms.Select(attrs={'class': 'field-ul'}),
            'date_embauche': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'date_fin_contrat': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Notes RH internes…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from employer.models import Fonction, Grade, TypeContrat
        self.fields['matricule'].required = False
        self.fields['fonction'].queryset = Fonction.objects.all()
        self.fields['fonction'].empty_label = '— Choisir une fonction —'
        self.fields['fonction'].required = False
        self.fields['grade'].queryset = Grade.objects.all()
        self.fields['grade'].empty_label = '— Choisir un grade —'
        self.fields['grade'].required = False
        self.fields['type_contrat'].queryset = TypeContrat.objects.all()
        self.fields['type_contrat'].empty_label = '— Choisir un type —'
        self.fields['type_contrat'].required = False
        self.fields['date_fin_contrat'].required = False
        self.fields['notes'].required = False


class PasswordChangeFormCustom(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'field-ul', 'autocomplete': 'current-password', 'placeholder': '••••••••'}),
        label='Mot de passe actuel',
        required=False,
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'field-ul', 'autocomplete': 'new-password', 'placeholder': '••••••••'}),
        label='Nouveau mot de passe',
        min_length=6,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'field-ul', 'autocomplete': 'new-password', 'placeholder': '••••••••'}),
        label='Confirmer le nouveau mot de passe',
    )

    def __init__(self, *args, admin_mode=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.admin_mode = admin_mode
        if not admin_mode:
            self.fields['current_password'].required = True

    def clean(self):
        data = super().clean()
        if data.get('new_password') and data.get('new_password') != data.get('confirm_password'):
            self.add_error('confirm_password', 'Les mots de passe ne correspondent pas.')
        return data


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        from employer.models import DocumentEmploye as _Doc
        model = _Doc
        fields = ['type_document', 'titre', 'fichier', 'date_expiration', 'notes']
        widgets = {
            'type_document': forms.Select(attrs={'class': 'field-ul'}),
            'titre': forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : CNI — Jean DUPONT'}),
            'fichier': forms.FileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'}),
            'date_expiration': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'field-ul', 'rows': 2, 'placeholder': 'Notes…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_expiration'].required = False
        self.fields['notes'].required = False
