from django import forms
from django.forms import inlineformset_factory
from .models import GroupeMedicaments, LigneGroupeMedicaments, Maladie, Ordonnance, LigneOrdonnance


class MaladieForm(forms.ModelForm):
    class Meta:
        model = Maladie
        fields = ['nom', 'code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-input')


class GroupeMedicamentsForm(forms.ModelForm):
    class Meta:
        model = GroupeMedicaments
        fields = ['nom', 'medecin', 'maladie', 'limite']
        widgets = {
            'limite': forms.NumberInput(attrs={'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-input')


LigneGroupeMedicamentsFormSet = inlineformset_factory(
    GroupeMedicaments,
    LigneGroupeMedicaments,
    fields=['medicament', 'medicament_libre', 'autorise', 'frequence_posologique',
            'dosage', 'unite_dosage', 'qte_par_jour', 'jours', 'commentaire'],
    extra=1,
    can_delete=True,
    widgets={
        'medicament_libre': forms.TextInput(attrs={'placeholder': 'Saisie libre', 'class': 'form-input'}),
        'frequence_posologique': forms.TextInput(attrs={'placeholder': 'ex: 3×/jour', 'class': 'form-input'}),
        'dosage': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5'}),
        'unite_dosage': forms.TextInput(attrs={'placeholder': 'ex: mg, ml', 'class': 'form-input'}),
        'qte_par_jour': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5'}),
        'jours': forms.NumberInput(attrs={'class': 'form-input'}),
        'commentaire': forms.TextInput(attrs={'placeholder': 'Instructions...', 'class': 'form-input'}),
    },
)


class OrdonnanceForm(forms.ModelForm):
    date_ordonnance = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'],
        label="Date d'ordonnance",
    )

    class Meta:
        model = Ordonnance
        fields = [
            'patient', 'medecin', 'consultation', 'groupe_medicaments',
            'ancienne_ordonnance', 'maladie', 'date_ordonnance',
            'avertissement_grossesse', 'type_ordonnance', 'notes',
            'rendez_vous', 'facture', 'cueillettes', 'livre',
            'hospitalisation', 'police_assurance', 'compagnie_assurance',
            'reclamation',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'cueillettes': forms.TextInput(),
            'compagnie_assurance': forms.TextInput(),
            'reclamation': forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.date_ordonnance:
            self.initial['date_ordonnance'] = self.instance.date_ordonnance.strftime('%Y-%m-%dT%H:%M')
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.setdefault('class', 'form-input')


class LigneOrdonnanceForm(forms.ModelForm):
    class Meta:
        model = LigneOrdonnance
        fields = ['medicament', 'medicament_libre', 'quantite', 'unite_dosage', 'qte_par_jour', 'jours', 'commentaire']
        widgets = {
            'medicament_libre': forms.TextInput(attrs={'placeholder': 'Nom libre du médicament', 'class': 'form-input'}),
            'quantite': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5', 'value': '1'}),
            'unite_dosage': forms.TextInput(attrs={'placeholder': 'ex: comprimé, mg, ml', 'class': 'form-input'}),
            'qte_par_jour': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5'}),
            'jours': forms.NumberInput(attrs={'class': 'form-input'}),
            'commentaire': forms.TextInput(attrs={'placeholder': 'Instructions de prise...', 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['quantite'].initial = 1


LigneOrdonnanceFormSet = inlineformset_factory(
    Ordonnance,
    LigneOrdonnance,
    form=LigneOrdonnanceForm,
    extra=1,
    can_delete=True,
)
