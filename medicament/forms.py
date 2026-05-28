from django import forms
from .models import (
    Medicament, GroupeMedicament, LigneMedicamentGroupe,
    CompagniePharma, EffetTherapeutique, DosageMedicament,
    RouteMedicament, FormulaireType,
)
from pharmacie.models import MouvementStock, LotMedicament


class MedicamentForm(forms.ModelForm):
    class Meta:
        model  = Medicament
        fields = [
            'code', 'designation', 'dci', 'forme', 'dosage', 'categorie',
            'peut_etre_vendu', 'peut_etre_achete', 'actif',
            'voie_administration', 'frequence', 'composant_actif',
            'effet_therapeutique', 'effets_indesirables',
            'quantite_prescription_manuelle', 'indications', 'remarques',
            'avertissement_grossesse', 'avertissement_lactation',
            'compagnie_pharma', 'nom_produit_fabricant',
            'code_produit_fabricant', 'url_produit',
            'prix_vente', 'prix_achat',
            'stock_alerte', 'stock_minimum',
            'reference_interne', 'code_barres',
        ]
        widgets = {
            'effets_indesirables': forms.Textarea(attrs={'rows': 3}),
            'indications':         forms.Textarea(attrs={'rows': 3}),
            'remarques':           forms.Textarea(attrs={'rows': 3}),
        }


class MouvementStockForm(forms.ModelForm):
    class Meta:
        model  = MouvementStock
        fields = ['type_mouvement', 'motif', 'quantite', 'lot', 'reference', 'notes']

    def __init__(self, *args, medicament=None, **kwargs):
        super().__init__(*args, **kwargs)
        if medicament:
            self.fields['lot'].queryset = LotMedicament.objects.filter(medicament=medicament)
        self.fields['lot'].required       = False
        self.fields['reference'].required = False
        self.fields['notes'].required     = False


class GroupeMedicamentForm(forms.ModelForm):
    class Meta:
        model   = GroupeMedicament
        fields  = ['nom', 'medecin', 'limite', 'maladies']
        widgets = {'maladies': forms.Textarea(attrs={'rows': 2})}


class CompagniePharmaForm(forms.ModelForm):
    class Meta:
        model  = CompagniePharma
        fields = ['nom', 'code', 'partenaire']


class EffetTherapeutiqueForm(forms.ModelForm):
    class Meta:
        model  = EffetTherapeutique
        fields = ['nom', 'code']


class DosageMedicamentForm(forms.ModelForm):
    class Meta:
        model  = DosageMedicament
        fields = ['nom', 'code', 'frequence', 'qte_totale_par_jour', 'jours']


class RouteMedicamentForm(forms.ModelForm):
    class Meta:
        model  = RouteMedicament
        fields = ['nom', 'code']


class FormulaireTypeForm(forms.ModelForm):
    class Meta:
        model  = FormulaireType
        fields = ['nom', 'code']
