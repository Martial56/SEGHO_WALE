from django import forms
from .models import Facture


class FactureForm(forms.ModelForm):
    class Meta:
        model = Facture
        fields = ['type_facture', 'date_echeance', 'montant_assurance',
                  'ticket_moderateur', 'notes', 'statut']
        widgets = {
            'date_echeance': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d',
            ),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field-ul')
