from django import forms
from .models import Facture


class FactureForm(forms.ModelForm):
    class Meta:
        model = Facture
        fields = ['type_facture', 'statut', 'date_echeance', 'montant_assurance', 'ticket_moderateur', 'notes']
        widgets = {
            'type_facture': forms.Select(attrs={'class': 'field-ul'}),
            'statut': forms.Select(attrs={'class': 'field-ul'}),
            'date_echeance': forms.DateInput(attrs={'class': 'field-ul', 'type': 'date'}),
            'montant_assurance': forms.NumberInput(attrs={'class': 'field-ul', 'step': '1', 'min': '0', 'placeholder': '0'}),
            'ticket_moderateur': forms.NumberInput(attrs={'class': 'field-ul', 'step': '1', 'min': '0', 'placeholder': '0'}),
            'notes': forms.Textarea(attrs={'class': 'field-ul', 'rows': 3, 'placeholder': 'Remarques ou informations complémentaires…'}),
        }
