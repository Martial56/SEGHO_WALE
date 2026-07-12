from django import forms
from .models import CategorieArticle

_ul = 'field-ul'


class CategorieArticleForm(forms.ModelForm):
    class Meta:
        model = CategorieArticle
        fields = [
            'nom', 'code', 'parent', 'description',
            'sequence_code_barres', 'bloquer_serie_lot',
            'routes', 'strategie_enlevement', 'reservation_conditionnement',
            'methode_cout', 'valorisation_inventaire',
            'compte_revenus', 'compte_charges',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Médicaments',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Généré automatiquement si laissé vide',
                'style': 'font-family: var(--font-mono); text-transform: uppercase;',
            }),
            'parent': forms.Select(attrs={'class': _ul}),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 2,
                'placeholder': 'Description optionnelle…',
            }),
            'sequence_code_barres': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Séquence de code-barres',
            }),
            'routes': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Achats, Fabrication…',
            }),
            'strategie_enlevement': forms.Select(attrs={'class': _ul}),
            'reservation_conditionnement': forms.RadioSelect(),
            'methode_cout': forms.Select(attrs={'class': _ul}),
            'valorisation_inventaire': forms.Select(attrs={'class': _ul}),
            'compte_revenus': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : 70110000 Ventes de march. dans l\'UEMOA',
            }),
            'compte_charges': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : 60110000 Ach. autres produits',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].empty_label = '— Aucune (catégorie racine) —'
        self.fields['parent'].required = False
        for f in ['reservation_conditionnement', 'methode_cout', 'valorisation_inventaire']:
            self.fields[f].required = False
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }
