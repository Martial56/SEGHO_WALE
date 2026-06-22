from django import forms
from django.db.models import Q
from .models import Chambre, RegistreDeces, ListeControleAdmission, ListeVerificationService, Hospitalisation

_ul = 'field-ul'


class HospitalisationForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from patients.models import Patient as PatientModel
        from medecins.models import Medecin
        from services.models import Articleservice
        # Noms uniquement (sans code patient)
        self.fields['patient'].queryset = PatientModel.objects.filter(actif=True).order_by('nom')
        self.fields['patient'].label_from_instance = lambda p: f"{p.nom} {p.prenoms}"
        self.fields['medecin_traitant'].queryset = Medecin.objects.filter(actif=True).order_by('nom')
        self.fields['medecin_traitant'].label_from_instance = lambda m: f"{m.nom} {m.prenoms}"
        self.fields['medecin_referent'].queryset = Medecin.objects.filter(actif=True).order_by('nom')
        self.fields['medecin_referent'].label_from_instance = lambda m: f"{m.nom} {m.prenoms}"
        self.fields['patient'].empty_label              = 'Rechercher un patient…'
        self.fields['medecin_traitant'].empty_label     = 'Sélectionner un docteur…'
        self.fields['maladie'].empty_label              = 'Sélectionner une maladie…'
        self.fields['chambre'].empty_label              = 'Sélectionner une salle/chambre…'
        self.fields['medecin_referent'].empty_label     = 'Sélectionner un médecin…'
        # Chambres disponibles + toujours inclure la chambre déjà attribuée
        # (quelle que soit sa disponibilité, pour qu'elle reste visible dans le select)
        current_chambre_id = self.instance.chambre_id if self.instance and self.instance.pk else None
        if current_chambre_id:
            chambre_qs = Chambre.objects.filter(
                Q(statut=True) | Q(pk=current_chambre_id)
            ).distinct().order_by('salle_no')
        else:
            chambre_qs = Chambre.objects.filter(statut=True).order_by('salle_no')
        self.fields['chambre'].queryset = chambre_qs


    class Meta:
        model  = Hospitalisation
        fields = [
            'patient', 'medecin_traitant', 'maladie',
            'date_admission',
            'nom_parent_gardien', 'phone_parent_gardien',
            'medecin_referent', 'chambre',
            'cas_legal', 'signale_police',
            'motif_admission', 'notes',
            'etablissement_destination', 'motif_reference',
        ]
        widgets = {
            'patient':                    forms.Select(attrs={'class': _ul}),
            'medecin_traitant':           forms.Select(attrs={'class': _ul}),
            'maladie':                    forms.Select(attrs={'class': _ul}),
            'date_admission':             forms.DateTimeInput(attrs={'class': _ul, 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'nom_parent_gardien':         forms.TextInput(attrs={'class': _ul, 'placeholder': 'Nom du parent / gardien…'}),
            'phone_parent_gardien':       forms.TextInput(attrs={'class': _ul, 'placeholder': 'Numéro de téléphone…'}),
            'medecin_referent':           forms.Select(attrs={'class': _ul}),
            'chambre':                    forms.Select(attrs={'class': _ul}),
            'cas_legal':                  forms.CheckboxInput(),
            'signale_police':             forms.RadioSelect(),
            'motif_admission':            forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': "Motif d'admission…"}),
            'notes':                      forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Notes internes…'}),
            'etablissement_destination':  forms.TextInput(attrs={'class': _ul, 'placeholder': 'Établissement de destination…'}),
            'motif_reference':            forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Motif du transfert…'}),
        }


class ChambreForm(forms.ModelForm):
    class Meta:
        model = Chambre
        exclude = ['salle_no']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'field-ul field-ul-name',
                'placeholder': 'Nom de la chambre',
            }),
            'type_chambre':        forms.Select(attrs={'class': _ul}),
            'statut':              forms.Select(attrs={'class': _ul},
                                                choices=[(True, 'Disponible'), (False, 'Occupée')]),
            'prive':               forms.CheckboxInput(attrs={'class': 'field-check'}),
            'genre':               forms.Select(attrs={'class': _ul}),
            'description':         forms.Textarea(attrs={'class': _ul, 'rows': 3,
                                                          'placeholder': 'Remarques…'}),
            'acces_internet':      forms.CheckboxInput(attrs={'class': 'field-check'}),
            'climatisation':       forms.CheckboxInput(attrs={'class': 'field-check'}),
            'salle_bains_privee':  forms.CheckboxInput(attrs={'class': 'field-check'}),
            'television':          forms.CheckboxInput(attrs={'class': 'field-check'}),
            'telephone_chambre':   forms.CheckboxInput(attrs={'class': 'field-check'}),
            'lit_visiteur':        forms.CheckboxInput(attrs={'class': 'field-check'}),
            'four_micro_onde':     forms.CheckboxInput(attrs={'class': 'field-check'}),
            'danger_biologique':   forms.CheckboxInput(attrs={'class': 'field-check'}),
            'refrigerateur':       forms.CheckboxInput(attrs={'class': 'field-check'}),
        }


class ListeVerificationServiceForm(forms.ModelForm):
    class Meta:
        model  = ListeVerificationService
        fields = ['item']
        widgets = {
            'item': forms.TextInput(attrs={'class': _ul, 'placeholder': "Élément de la liste de contrôle de salle…"}),
        }


class ListeControleAdmissionForm(forms.ModelForm):
    class Meta:
        model  = ListeControleAdmission
        fields = ['item', 'remarques']
        widgets = {
            'item':      forms.TextInput(attrs={'class': _ul, 'placeholder': "Vérifier l'élément de la liste…"}),
            'remarques': forms.Textarea(attrs={'class': _ul, 'rows': 3, 'placeholder': 'Remarques…'}),
        }




class RegistreDecesForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['patient'].empty_label        = 'Rechercher un patient…'
        self.fields['hospitalisation'].empty_label = 'Rechercher une hospitalisation…'
        self.fields['medecin'].empty_label         = 'Rechercher un médecin…'

    class Meta:
        model = RegistreDeces
        exclude = ['code', 'statut', 'cree_le']
        widgets = {
            'patient':          forms.Select(attrs={'class': _ul}),
            'date_deces':       forms.DateInput(attrs={'class': _ul, 'type': 'date'}),
            'hospitalisation':  forms.Select(attrs={'class': _ul}),
            'medecin':          forms.Select(attrs={'class': _ul}),
            'raison_deces':     forms.Textarea(attrs={'class': _ul, 'rows': 3,
                                                      'placeholder': 'Décrire la cause du décès…'}),
            'remarques':        forms.Textarea(attrs={'class': _ul, 'rows': 3,
                                                      'placeholder': 'Informations complémentaires…'}),
        }
