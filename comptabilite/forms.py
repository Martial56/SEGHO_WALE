from django import forms

from .models import MotifGratuite, MotifSortie


class _Champs:
    """Classe CSS commune des écrans de caisse sur les champs de saisie."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            if not isinstance(champ.widget, (forms.CheckboxInput, forms.ClearableFileInput)):
                champ.widget.attrs.setdefault('class', 'cpt-input')


class SortieForm(_Champs, forms.Form):
    motif = forms.ModelChoiceField(queryset=MotifSortie.objects.filter(actif=True),
                                   label="Motif", empty_label="— Choisir —")
    libelle = forms.CharField(max_length=255, label="Objet de la dépense")
    beneficiaire = forms.CharField(max_length=150, required=False, label="Bénéficiaire")
    montant = forms.DecimalField(min_value=1, max_digits=15, decimal_places=0, label="Montant (F CFA)")
    justificatif = forms.FileField(required=False, label="Justificatif (reçu, facture…)")


class MotifSortieForm(_Champs, forms.ModelForm):
    class Meta:
        model = MotifSortie
        fields = ['libelle', 'compte', 'actif']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Compte
        self.fields['compte'].queryset = Compte.objects.filter(actif=True)
        self.fields['compte'].empty_label = '— Compte par défaut —'


class MotifGratuiteForm(_Champs, forms.ModelForm):
    class Meta:
        model = MotifGratuite
        fields = ['libelle', 'remise_max', 'description', 'actif']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def clean_remise_max(self):
        valeur = self.cleaned_data['remise_max']
        if not 0 < valeur <= 100:
            raise forms.ValidationError("La remise maximale est un pourcentage entre 0 et 100.")
        return valeur
