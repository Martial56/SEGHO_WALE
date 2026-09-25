import re
from datetime import date

from django import forms
from .models import Patient, Assurance, RendezVous, Pathologie, TypeVisiteCurative
from gynecologie.models import TypeVisite

_ul = 'field-ul'          # underline (bottom border only)
_ul_name = 'field-ul field-ul-name'
_ul_prenom = 'field-ul field-ul-prenom'


class DepartementFiltreSelect(forms.Select):
    """Select dont chaque <option> porte data-departement-id, utilisé côté JS
    pour ne montrer que les prestations liées au département choisi.

    Exclu de TomSelect (`data-no-tomselect`) : la bibliothèque recopie les
    options à l'initialisation, elle ne verrait pas le masquage que ce JS
    applique ensuite sur les <option>."""

    def __init__(self, *args, departement_map=None, **kwargs):
        self.departement_map = departement_map or {}
        super().__init__(*args, **kwargs)
        self.attrs.setdefault('data-no-tomselect', '')

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        departement_id = self.departement_map.get(str(value))
        if departement_id:
            option['attrs']['data-departement-id'] = departement_id
        return option


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
            'photo': forms.ClearableFileInput(attrs={
                'data-photo-input': 'patient',
                'style': 'display:none',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assurance'].queryset = Assurance.objects.filter(actif=True)
        self.fields['assurance'].empty_label = '— Aucune assurance —'
        self.fields['nationalite'].initial = 'Ivoirienne'
        self.fields['ville'].initial = 'Yamoussoukro'
        self.fields['adresse'].required = True
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'invalid': 'Valeur invalide.',
            }

    def clean_date_naissance(self):
        date_naissance = self.cleaned_data.get('date_naissance')
        if date_naissance and date_naissance > date.today():
            raise forms.ValidationError('La date de naissance ne peut pas être postérieure à aujourd\'hui.')
        return date_naissance

    @staticmethod
    def _valider_numero_ivoirien(value):
        """Le JS convertit déjà le numéro en E.164 (+225xxxxxxxxxx) avant la
        soumission, mais reste contournable : on revalide ici les numéros
        ivoiriens (sans indicatif d'un autre pays), qui comptent 10 chiffres
        depuis la renumérotation de 2021."""
        value = (value or '').strip()
        if not value or value.startswith('+') and not value.startswith('+225'):
            return value
        digits = re.sub(r'\D', '', value)
        if digits.startswith('225'):
            digits = digits[3:]
        if len(digits) != 10:
            raise forms.ValidationError(
                'Un numéro ivoirien doit contenir 10 chiffres.'
            )
        return value

    def clean_telephone(self):
        return self._valider_numero_ivoirien(self.cleaned_data.get('telephone'))

    def clean_telephone2(self):
        return self._valider_numero_ivoirien(self.cleaned_data.get('telephone2'))

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
        fields = ['patient', 'departement', 'medecin', 'type_consultation', 'date_heure', 'motif', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': _ul, 'id': 'id_patient'}),
            'departement': forms.Select(attrs={'class': _ul}),
            'medecin': DepartementFiltreSelect(attrs={'class': _ul}),
            'type_consultation': DepartementFiltreSelect(attrs={'class': _ul}),
            # `step=1` ouvre les secondes : sans lui le sélecteur du
            # navigateur s'arrête à la minute et enregistre toujours « :00 ».
            # La lecture n'a pas besoin d'être élargie — forms.DateTimeField
            # passe d'abord par parse_datetime, qui lit l'ISO 8601 complet.
            'date_heure': forms.DateTimeInput(
                attrs={'class': _ul, 'type': 'datetime-local', 'step': '1'},
                format='%Y-%m-%dT%H:%M:%S',
            ),
            'motif': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Motif de la visite...',
            }),
            'notes': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Notes internes...',
            }),
        }

    def __init__(self, *args, locked_billing=False, **kwargs):
        from services.models import Articleservice
        from medecins.models import Departement, Medecin
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = Patient.objects.all().order_by('nom', 'prenoms')
        self.fields['patient'].empty_label = '— Sélectionner un patient —'
        self.fields['departement'].queryset = Departement.objects.filter(actif=True).order_by('nom')
        self.fields['departement'].empty_label = '— Choisir un département —'
        self.fields['departement'].required = True
        if locked_billing:
            # Une fois le rendez-vous confirmé et facturé, le département et le
            # type de consultation ne doivent plus changer : la facture a déjà
            # été émise sur cette base.
            self.fields['departement'].disabled = True
            self.fields['type_consultation'].disabled = True

        medecin_qs = Medecin.objects.filter(actif=True).select_related('employe').order_by('employe__nom', 'employe__prenoms')
        self.fields['medecin'].queryset = medecin_qs
        self.fields['medecin'].empty_label = '— Aucun médecin —'
        self.fields['medecin'].required = False
        self.fields['medecin'].widget.departement_map = {
            str(pk): departement_id
            for pk, departement_id in medecin_qs.values_list('pk', 'departement_id')
        }

        type_consultation_qs = Articleservice.objects.filter(
            actif=True, categorie__code='CS'
        ).select_related('departement').order_by('nom')
        self.fields['type_consultation'].queryset = type_consultation_qs
        self.fields['type_consultation'].empty_label = '— Choisir un type de consultation —'
        self.fields['type_consultation'].required = False
        self.fields['type_consultation'].widget.departement_map = {
            str(pk): departement_id
            for pk, departement_id in type_consultation_qs.values_list('pk', 'departement_id')
        }


class PathologieForm(forms.ModelForm):
    class Meta:
        model = Pathologie
        fields = ['nom', 'categorie', 'departement', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom de la pathologie',
            }),
            'categorie': forms.Select(attrs={'class': _ul}),
            'departement': forms.Select(attrs={'class': _ul}),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departement'].queryset = self.fields['departement'].queryset.order_by('nom')
        self.fields['departement'].empty_label = '— Aucun —'


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


class TypeVisiteCurativeForm(forms.ModelForm):
    """Types de visite des consultations curatives, pendant de TypeVisiteForm
    (gynécologie). Le code est repris tel quel dans le registre curatif et lu
    par les rapports : le modifier sur un type déjà utilisé casserait leur
    comptage."""

    class Meta:
        model = TypeVisiteCurative
        fields = ['nom', 'code', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom du type de visite',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex: consultant',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 2,
                'placeholder': 'Description (optionnel)',
            }),
        }
