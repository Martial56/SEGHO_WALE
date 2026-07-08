from django import forms
from .models import CategorieUniteMesure, UniteMesure

_ul = 'field-ul'


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
