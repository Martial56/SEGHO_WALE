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
    convention = forms.ModelChoiceField(
        queryset=None, required=False, label="Financée par la convention",
        empty_label="— Fonds propres du centre —",
        help_text="Si la dépense relève d'un projet financé, elle sera imputée à sa convention.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Convention
        self.fields['convention'].queryset = Convention.objects.filter(statut='active')


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


# ─── Lot 5 : financements ──────────────────────────────────────────────────────

from .models import Bailleur, Compte, Convention, Don, LigneBudgetaire, Versement  # noqa: E402

_DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class BailleurForm(_Champs, forms.ModelForm):
    class Meta:
        model = Bailleur
        fields = ['nom', 'sigle', 'type', 'contact', 'telephone', 'email', 'adresse', 'actif']
        widgets = {'adresse': forms.Textarea(attrs={'rows': 2})}


class ConventionForm(_Champs, forms.ModelForm):
    class Meta:
        model = Convention
        fields = ['bailleur', 'intitule', 'reference', 'date_debut', 'date_fin', 'montant_accorde',
                  'compte_ressource', 'statut', 'description']
        widgets = {'date_debut': _DATE, 'date_fin': _DATE, 'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bailleur'].queryset = Bailleur.objects.filter(actif=True) | Bailleur.objects.filter(
            pk=self.instance.bailleur_id or 0)
        self.fields['compte_ressource'].queryset = Compte.objects.filter(actif=True, numero__regex=r'^[17]')
        if not self.instance.pk:
            from .models import Correspondance
            defaut = Correspondance.objects.filter(cle='subvention_defaut').first()
            if defaut:
                self.initial.setdefault('compte_ressource', defaut.compte_id)

    def clean(self):
        donnees = super().clean()
        if donnees.get('date_debut') and donnees.get('date_fin') and donnees['date_fin'] < donnees['date_debut']:
            raise forms.ValidationError("La fin de la convention précède son début.")
        return donnees


class LigneBudgetaireForm(_Champs, forms.ModelForm):
    class Meta:
        model = LigneBudgetaire
        fields = ['libelle', 'compte', 'montant_prevu']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['compte'].queryset = Compte.objects.filter(actif=True, numero__regex=r'^[26]')


LigneBudgetaireFormSet = forms.inlineformset_factory(
    Convention, LigneBudgetaire, form=LigneBudgetaireForm, extra=3, can_delete=True)


class VersementForm(_Champs, forms.ModelForm):
    class Meta:
        model = Versement
        fields = ['date', 'montant', 'mode', 'reference', 'observation']
        widgets = {'date': _DATE, 'observation': forms.Textarea(attrs={'rows': 2})}

    def clean_montant(self):
        if self.cleaned_data['montant'] <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return self.cleaned_data['montant']


class DonForm(_Champs, forms.ModelForm):
    class Meta:
        model = Don
        fields = ['date', 'donateur', 'donateur_nom', 'nature', 'montant', 'description',
                  'compte_actif', 'convention', 'reference']
        widgets = {'date': _DATE, 'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['convention'].queryset = Convention.objects.filter(statut='active')
        self.fields['compte_actif'].queryset = Compte.objects.filter(actif=True, numero__regex=r'^[23]')

    def clean(self):
        donnees = super().clean()
        if donnees.get('montant') is not None and donnees['montant'] <= 0:
            self.add_error('montant', "Le montant doit être positif.")
        if not donnees.get('donateur') and not (donnees.get('donateur_nom') or '').strip():
            donnees['donateur_nom'] = ''
        if donnees.get('nature') == 'nature' and not (donnees.get('description') or '').strip():
            self.add_error('description', "Décrivez ce qui a été reçu (nature, quantités).")
        return donnees
