from django import forms
from django.db.models import Q
from .models import Chambre, RegistreDeces, ListeControleAdmission, ListeVerificationService, Hospitalisation

_ul = 'field-ul'

STATUTS_ACTIFS = ['brouillon', 'confirme', 'hospitalise']


def _build_chambre_lit_choices(instance=None):
    """Retourne les choix (valeur, libellé) pour le select chambre/lit.

    - Chambre à 1 lit  → "Chambre X"            si disponible
    - Chambre à N lits → "Chambre X - Lit Y"     pour chaque lit non occupé

    La valeur encodée est "{chambre_pk}_{lit_no}" :
      lit_no = 0 pour les chambres mono-lit (pas de numérotation visible).
    """
    current_chambre_id = instance.chambre_id if instance and instance.pk else None
    current_lit_no     = instance.numero_lit  if instance and instance.pk else None
    current_pk         = instance.pk          if instance and instance.pk else None

    occupied = set(
        Hospitalisation.objects.filter(statut__in=STATUTS_ACTIFS)
        .exclude(pk=current_pk)
        .values_list('chambre_id', 'numero_lit')
    )

    choices = [('', 'Sélectionner une salle/chambre…')]
    for chambre in Chambre.objects.order_by('salle_no'):
        if chambre.nombre_lits == 1:
            is_current = current_chambre_id == chambre.pk
            if chambre.statut or is_current:
                choices.append((f"{chambre.pk}_0", str(chambre)))
        else:
            for lit_no in range(1, chambre.nombre_lits + 1):
                is_current = current_chambre_id == chambre.pk and current_lit_no == lit_no
                if (chambre.pk, lit_no) not in occupied or is_current:
                    choices.append((f"{chambre.pk}_{lit_no}", f"{chambre} - Lit {lit_no}"))
    return choices


class HospitalisationForm(forms.ModelForm):

    chambre_lit = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': _ul}),
        label="Salle/Chambre",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from patients.models import Patient as PatientModel
        from medecins.models import Medecin
        self.fields['patient'].queryset = PatientModel.objects.all().order_by('nom')
        self.fields['patient'].label_from_instance = lambda p: f"{p.nom} {p.prenoms}"
        self.fields['medecin_traitant'].queryset = Medecin.objects.filter(actif=True).order_by('nom')
        self.fields['medecin_traitant'].label_from_instance = lambda m: f"{m.nom} {m.prenoms}"
        self.fields['medecin_referent'].queryset = Medecin.objects.filter(actif=True).order_by('nom')
        self.fields['medecin_referent'].label_from_instance = lambda m: f"{m.nom} {m.prenoms}"
        self.fields['patient'].empty_label          = 'Rechercher un patient…'
        self.fields['medecin_traitant'].empty_label = 'Sélectionner un docteur…'
        self.fields['maladie'].empty_label          = 'Sélectionner une maladie…'
        self.fields['medecin_referent'].empty_label = 'Sélectionner un médecin…'

        self.fields['chambre_lit'].choices = _build_chambre_lit_choices(self.instance)

        # Valeur initiale depuis l'instance existante
        if self.instance and self.instance.pk and self.instance.chambre_id:
            lit = self.instance.numero_lit or 0
            self.fields['chambre_lit'].initial = f"{self.instance.chambre_id}_{lit}"

    def save(self, commit=True):
        instance = super().save(commit=False)
        val = self.cleaned_data.get('chambre_lit', '')
        if val:
            chambre_pk, lit_no = val.split('_', 1)
            instance.chambre_id = int(chambre_pk)
            instance.numero_lit = int(lit_no) if int(lit_no) > 0 else None
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model  = Hospitalisation
        fields = [
            'patient', 'medecin_traitant', 'maladie',
            'date_admission',
            'nom_parent_gardien', 'phone_parent_gardien',
            'medecin_referent',
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
            'nombre_lits':         forms.NumberInput(attrs={'class': _ul, 'min': 1}),
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
