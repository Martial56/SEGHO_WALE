from django import forms
from .models import CategorieArticle, CategorieUniteMesure, UniteMesure, Consommable, Typeservice

_ul = 'field-ul'


class TypeserviceForm(forms.ModelForm):
    class Meta:
        model = Typeservice
        fields = ['nom', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Consultation, Suivi, Urgence, Tous…',
                'autofocus': True,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Ce type existe déjà.',
            }


class CategorieArticleForm(forms.ModelForm):
    class Meta:
        model = CategorieArticle
        fields = [
            'nom', 'parent', 'description',
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


class CategorieUniteMesureForm(forms.ModelForm):
    class Meta:
        model = CategorieUniteMesure
        fields = ['nom']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Poids, Volume, Forme pharmaceutique…',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }


class UniteMesureForm(forms.ModelForm):
    class Meta:
        model = UniteMesure
        fields = ['nom', 'code', 'categorie', 'type_unite', 'ratio', 'precision_arrondi', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Millilitre',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : ml',
            }),
            'categorie': forms.Select(attrs={'class': _ul}),
            'type_unite': forms.Select(attrs={'class': _ul}),
            'ratio': forms.NumberInput(attrs={
                'class': _ul,
                'placeholder': '1.000000',
                'step': '0.000001',
                'min': '0',
            }),
            'precision_arrondi': forms.NumberInput(attrs={
                'class': _ul,
                'placeholder': '0.01000',
                'step': '0.00001',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categorie'].empty_label = '— Sélectionner une catégorie —'
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }


class ConsommableForm(forms.ModelForm):
    class Meta:
        model = Consommable
        fields = ['code', 'nom', 'description', 'categorie', 'unite_mesure',
                  'prix_achat', 'prix_vente', 'quantite_stock', 'quantite_alerte', 'actif']
        widgets = {
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Auto-généré si vide',
                'style': 'text-transform:uppercase',
            }),
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom du consommable',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle…',
            }),
            'categorie': forms.Select(attrs={'class': _ul}),
            'unite_mesure': forms.Select(attrs={'class': _ul}),
            'prix_achat': forms.NumberInput(attrs={'class': _ul, 'placeholder': '0', 'min': '0'}),
            'prix_vente': forms.NumberInput(attrs={'class': _ul, 'placeholder': '0', 'min': '0'}),
            'quantite_stock': forms.NumberInput(attrs={'class': _ul, 'placeholder': '0', 'min': '0'}),
            'quantite_alerte': forms.NumberInput(attrs={'class': _ul, 'placeholder': '0', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nom'].required = True
        for f in ['code', 'description', 'categorie', 'unite_mesure',
                  'prix_achat', 'prix_vente', 'quantite_stock', 'quantite_alerte']:
            self.fields[f].required = False
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }
