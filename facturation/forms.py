from django import forms
from .models import Facture


class FactureForm(forms.ModelForm):
    class Meta:
        model = Facture
        fields = ['type_facture', 'date_echeance', 'montant_assurance',
                  'ticket_moderateur', 'notes']
        widgets = {
            'date_echeance': forms.DateInput(
                attrs={'type': 'date'},
                format='%Y-%m-%d',
            ),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', True)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field-ul')
        self.fields['date_echeance'].widget.format = '%Y-%m-%d'
        if 'type_facture' in self.fields:
            self.fields['type_facture'].widget.attrs['autocomplete'] = 'off'
        if not is_admin:
            self.fields.pop('type_facture', None)
