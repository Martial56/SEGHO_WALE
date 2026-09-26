from django import forms
from .models import CategorieArticle

_ul = 'field-ul'


class CategorieArticleForm(forms.ModelForm):
    class Meta:
        model = CategorieArticle
        fields = ['nom', 'code', 'parent', 'description']
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].empty_label = '— Aucune (catégorie racine) —'
        self.fields['parent'].required = False
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'unique': 'Cette valeur existe déjà.',
            }
