from django import forms
from .models import Patient, Assurance, RendezVous, Pathologie, TypeVisite

_ul = 'field-ul'          # underline (bottom border only)
_ul_name = 'field-ul field-ul-name'
_ul_prenom = 'field-ul field-ul-prenom'


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        exclude = ['code_patient', 'date_creation', 'date_modification']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul_name,
                'placeholder': 'Nom',
            }),
            'prenoms': forms.TextInput(attrs={
                'class': _ul_prenom,
                'placeholder': 'Prénom(s)',
            }),
            'sexe': forms.Select(attrs={'class': _ul}),
            'date_naissance': forms.DateInput(attrs={
                'class': _ul,
                'type': 'date',
            }, format='%Y-%m-%d'),
            'lieu_naissance': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ville, pays',
            }),
            'nationalite': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ivoirienne',
            }),
            'profession': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Emploi actuel',
            }),
            'telephone': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
            'telephone2': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
            'email': forms.EmailInput(attrs={
                'class': _ul,
                'placeholder': 'exemple@email.com',
            }),
            'adresse': forms.Textarea(attrs={
                'class': _ul,
                'rows': 2,
                'placeholder': 'Quartier, rue, numéro...',
            }),
            'ville': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Yamoussoukro',
            }),
            'groupe_sanguin': forms.Select(attrs={'class': _ul}),
            'allergies': forms.Textarea(attrs={
                'class': _ul,
                'rows': 4,
                'placeholder': 'Médicaments, aliments, substances...',
            }),
            'antecedents': forms.Textarea(attrs={
                'class': _ul,
                'rows': 4,
                'placeholder': 'Maladies, chirurgies, hospitalisations...',
            }),
            'assurance': forms.Select(attrs={'class': _ul}),
            'numero_assurance': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'N° de la carte / police',
            }),
            'date_expiration_assurance': forms.DateInput(attrs={
                'class': _ul,
                'type': 'date',
            }, format='%Y-%m-%d'),
            'contact_urgence_nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom et lien de parenté',
            }),
            'contact_urgence_telephone': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assurance'].queryset = Assurance.objects.filter(actif=True)
        self.fields['assurance'].empty_label = '— Aucune assurance —'
        self.fields['nationalite'].initial = 'Ivoirienne'
        self.fields['ville'].initial = 'Yamoussoukro'
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'invalid': 'Valeur invalide.',
            }

    def clean(self):
        cleaned = super().clean()
        nom            = (cleaned.get('nom') or '').strip()
        prenoms        = (cleaned.get('prenoms') or '').strip()
        date_naissance = cleaned.get('date_naissance')
        telephone      = (cleaned.get('telephone') or '').strip()

        if nom and prenoms and date_naissance and telephone:
            qs = Patient.objects.filter(
                nom__iexact=nom,
                prenoms__iexact=prenoms,
                date_naissance=date_naissance,
                telephone=telephone,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            doublon = qs.first()
            if doublon:
                raise forms.ValidationError(
                    f'Un dossier patient identique existe déjà : {doublon.code_patient} — '
                    f'{doublon.nom} {doublon.prenoms}, né(e) le {doublon.date_naissance.strftime("%d/%m/%Y")}, '
                    f'tél. {doublon.telephone}.'
                )
        return cleaned


class RendezVousForm(forms.ModelForm):
    class Meta:
        model = RendezVous
        fields = ['patient', 'departement', 'medecin', 'type_consultation', 'date_heure', 'duree_minutes', 'motif', 'statut', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': _ul, 'id': 'id_patient'}),
            'departement': forms.Select(attrs={'class': _ul}),
            'medecin': forms.Select(attrs={'class': _ul}),
            'type_consultation': forms.Select(attrs={'class': _ul}),
            'date_heure': forms.DateTimeInput(
                attrs={'class': _ul, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'duree_minutes': forms.NumberInput(attrs={
                'class': _ul, 'min': '5', 'step': '5', 'placeholder': '30',
            }),
            'statut': forms.Select(attrs={'class': _ul}),
            'motif': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Motif de la visite...',
            }),
            'notes': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Notes internes...',
            }),
        }

    def __init__(self, *args, **kwargs):
        from services.models import Articleservice
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = Patient.objects.all().order_by('nom', 'prenoms')
        self.fields['medecin'].empty_label = '— Aucun médecin —'
        self.fields['medecin'].required = False
        self.fields['departement'].empty_label = '— Choisir un département —'
        self.fields['departement'].required = False
        self.fields['type_consultation'].queryset = Articleservice.objects.filter(actif=True, categorie__code__iexact='cs').order_by('nom')
        self.fields['type_consultation'].empty_label = '— Choisir un type de consultation —'
        self.fields['type_consultation'].required = False


class PathologieForm(forms.ModelForm):
    class Meta:
        model = Pathologie
        fields = ['nom', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom de la pathologie',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle...',
            }),
        }


class TypeVisiteForm(forms.ModelForm):
    class Meta:
        model = TypeVisite
        fields = ['nom', 'code', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom du type de visite',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex: CPN01',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle...',
            }),
        }
