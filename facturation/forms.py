from django import forms
from .models import Facture, Caisse, Paiement


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
        # Le type se déduit des lignes (Facture.appliquer_type_deduit) : le
        # champ reste affiché, pour information, mais ce que poste le navigateur
        # est ignoré. `disabled` est fait pour ça — Django reprend la valeur de
        # l'instance et ne regarde pas le POST.
        if 'type_facture' in self.fields:
            self.fields['type_facture'].disabled = True
        if 'type_facture' in self.fields:
            self.fields['type_facture'].widget.attrs['autocomplete'] = 'off'
        if not is_admin:
            self.fields.pop('type_facture', None)


class CaisseForm(forms.ModelForm):
    """Formulaire de configuration d'une caisse (journal d'encaissement)."""

    # Stocké en une chaîne de codes séparés par des virgules, présenté en cases
    # à cocher. Seuls les modes cochés sont proposés à l'encaissement.
    modes_paiement = forms.MultipleChoiceField(
        choices=Paiement.MODE,
        required=False,
        initial=[Caisse.MODE_PAR_DEFAUT],
        widget=forms.CheckboxSelectMultiple,
        label="Modes de paiement acceptés",
    )

    class Meta:
        model = Caisse
        fields = ['nom', 'code', 'actif', 'modes_paiement']
        labels = {
            'nom':   "Nom de la caisse",
            'code':  "Code",
            'actif': "Caisse active",
        }
        help_texts = {
            'code':  "Identifiant court et unique, par exemple CTB1.",
            'actif': "Une caisse inactive n'est plus proposée à l'encaissement, "
                     "mais les paiements déjà enregistrés la gardent.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom, champ in self.fields.items():
            if nom not in ('actif', 'modes_paiement'):
                champ.widget.attrs.setdefault('class', 'field-ul')
        if self.instance.pk and self.instance.modes_paiement:
            self.initial['modes_paiement'] = self.instance.modes_paiement.split(',')

    def clean_modes_paiement(self):
        codes = self.cleaned_data.get('modes_paiement') or []
        # Une caisse qui n'accepterait rien ne serait pas une caisse : tout
        # décocher revient à ne garder que l'espèce, le cas du guichet.
        if not codes:
            return Caisse.MODE_PAR_DEFAUT
        ordre = [code for code, _ in Paiement.MODE]
        return ','.join(sorted(codes, key=ordre.index))

    def clean_code(self):
        # Saisi en minuscules ici et en majuscules là, le même code créerait
        # deux caisses que `unique=True` ne verrait pas comme des doublons.
        code = (self.cleaned_data.get('code') or '').strip().upper()
        doublon = Caisse.objects.filter(code=code)
        if self.instance.pk:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError("Ce code est déjà pris par une autre caisse.")
        return code

    def clean_nom(self):
        return (self.cleaned_data.get('nom') or '').strip()
