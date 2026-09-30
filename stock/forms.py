from django import forms
from .models import UniteMesure

_ul = 'field-ul'


class UniteMesureForm(forms.ModelForm):
    class Meta:
        model = UniteMesure
        fields = ['nom', 'code', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : Millilitre',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex : ml',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }
