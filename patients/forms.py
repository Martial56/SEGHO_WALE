import re
from datetime import date

from django import forms
from .doublons_acces import CHOISIR
from .models import Patient, Assurance, RendezVous, Pathologie, TypeVisiteCurative
from gynecologie.models import TypeVisite

_ul = 'field-ul'          # underline (bottom border only)
_ul_name = 'field-ul field-ul-name'
_ul_prenom = 'field-ul field-ul-prenom'


class DepartementFiltreSelect(forms.Select):
    """Select dont chaque <option> porte data-departement-id, utilisé côté JS
    pour ne montrer que les prestations liées au département choisi.

    Exclu de TomSelect (`data-no-tomselect`) : la bibliothèque recopie les
    options à l'initialisation, elle ne verrait pas le masquage que ce JS
    applique ensuite sur les <option>."""

    def __init__(self, *args, departement_map=None, **kwargs):
        self.departement_map = departement_map or {}
        super().__init__(*args, **kwargs)
        self.attrs.setdefault('data-no-tomselect', '')

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        departement_id = self.departement_map.get(str(value))
        if departement_id:
            option['attrs']['data-departement-id'] = departement_id
        return option


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        exclude = ['code_patient', 'date_creation', 'date_modification']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul_name,
                'placeholder': 'Nom',
            }),
            'prenoms': forms.TextInput(attrs={
                'class': _ul_prenom,
                'placeholder': 'Prénom(s)',
            }),
            'sexe': forms.Select(attrs={'class': _ul}),
            'date_naissance': forms.DateInput(attrs={
                'class': _ul,
                'type': 'date',
            }, format='%Y-%m-%d'),
            'lieu_naissance': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ville, pays',
            }),
            'nationalite': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ivoirienne',
            }),
            'profession': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Emploi actuel',
            }),
            'telephone': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
            'telephone2': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
            'email': forms.EmailInput(attrs={
                'class': _ul,
                'placeholder': 'exemple@email.com',
            }),
            'adresse': forms.Textarea(attrs={
                'class': _ul,
                'rows': 2,
                'placeholder': 'Quartier, rue, numéro...',
            }),
            'ville': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Yamoussoukro',
            }),
            'groupe_sanguin': forms.Select(attrs={'class': _ul}),
            'allergies': forms.Textarea(attrs={
                'class': _ul,
                'rows': 4,
                'placeholder': 'Médicaments, aliments, substances...',
            }),
            'antecedents': forms.Textarea(attrs={
                'class': _ul,
                'rows': 4,
                'placeholder': 'Maladies, chirurgies, hospitalisations...',
            }),
            'assurance': forms.Select(attrs={'class': _ul}),
            'numero_assurance': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'N° de la carte / police',
            }),
            'date_expiration_assurance': forms.DateInput(attrs={
                'class': _ul,
                'type': 'date',
            }, format='%Y-%m-%d'),
            'contact_urgence_nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom et lien de parenté',
            }),
            'contact_urgence_telephone': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': '+225 07 00 00 00 00',
            }),
            'photo': forms.ClearableFileInput(attrs={
                'data-photo-input': 'patient',
                'style': 'display:none',
            }),
            'date_naissance_approx': forms.CheckboxInput(attrs={
                'class': 'o-check', 'id': 'id_date_naissance_approx',
            }),
        }
        labels = {
            'date_naissance_approx': 'Date approximative (seule l\'année est connue)',
        }

    # ── Garde-fou contre les doublons ──────────────────────────────────────
    # Ces trois champs ne sont pas dans le modèle : ils ne servent qu'à
    # recueillir ce que la personne affirme au moment d'enregistrer.
    doublon_confirme = forms.BooleanField(
        required=False, label="J'ai vérifié, c'est une autre personne",
        widget=forms.CheckboxInput(attrs={'class': 'o-check'}))
    forcer_doublon = forms.BooleanField(
        required=False, label='Créer malgré le dossier existant',
        widget=forms.CheckboxInput(attrs={'class': 'o-check'}))
    raison_forcage = forms.CharField(
        required=False, label='Raison',
        widget=forms.TextInput(attrs={
            'class': _ul, 'placeholder': 'Ex. : deux sœurs, même téléphone'}))

    def __init__(self, *args, utilisateur=None, centre=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur
        self.centre = centre
        #: Rempli par `clean` : ce que l'écran doit montrer après coup.
        self.doublons = []
        self.meme_telephone = 0
        #: (raison, fiche) quand un administrateur est passé outre — la vue le
        #: porte au journal, le formulaire n'écrit pas dans LogActivite.
        self.forcage = None
        self.fields['assurance'].queryset = Assurance.objects.filter(actif=True)
        self.fields['assurance'].empty_label = '— Aucune assurance —'
        self.fields['nationalite'].initial = 'Ivoirienne'
        self.fields['ville'].initial = 'Yamoussoukro'
        self.fields['adresse'].required = True
        # La date de naissance n'est obligatoire qu'à la création. C'est elle
        # qui sépare deux homonymes ; sans elle la recherche de doublons ne
        # tient plus qu'au téléphone, souvent partagé en famille. En
        # modification on ne l'exige pas : des dizaines de milliers de fiches
        # importées n'en portent pas, et exiger ici une information que
        # personne n'a interdirait de corriger leur adresse ou leur téléphone.
        # L'import ne passe pas par ce formulaire : elle y reste facultative.
        self.fields['date_naissance'].required = not (self.instance and self.instance.pk)
        for field in self.fields.values():
            field.error_messages = {
                'required': 'Ce champ est obligatoire.',
                'invalid': 'Valeur invalide.',
            }

    def clean_date_naissance(self):
        date_naissance = self.cleaned_data.get('date_naissance')
        if date_naissance and date_naissance > date.today():
            raise forms.ValidationError('La date de naissance ne peut pas être postérieure à aujourd\'hui.')
        return date_naissance

    @staticmethod
    def _valider_numero_ivoirien(value):
        """Le JS convertit déjà le numéro en E.164 (+225xxxxxxxxxx) avant la
        soumission, mais reste contournable : on revalide ici les numéros
        ivoiriens (sans indicatif d'un autre pays), qui comptent 10 chiffres
        depuis la renumérotation de 2021."""
        value = (value or '').strip()
        if not value or value.startswith('+') and not value.startswith('+225'):
            return value
        digits = re.sub(r'\D', '', value)
        if digits.startswith('225'):
            digits = digits[3:]
        if len(digits) != 10:
            raise forms.ValidationError(
                'Un numéro ivoirien doit contenir 10 chiffres.'
            )
        return value

    @staticmethod
    def _sans_chiffre(valeur):
        """Le texte débarrassé de ses chiffres, sans rien reprocher.

        Un chiffre n'a pas sa place dans un nom, mais le refuser au moment
        d'enregistrer ferait perdre la saisie pour une faute de frappe. À
        l'écran la touche ne fait déjà rien ; ici on fait la même chose pour ce
        qui arrive par un autre chemin — un collage, un import, une requête
        forgée. Les apostrophes et les traits d'union restent : les N'Guessan
        et les Marie-Claire sont des noms comme les autres.
        """
        return re.sub(r'[0-9]', '', valeur or '').strip()

    def clean_nom(self):
        return self._sans_chiffre(self.cleaned_data.get('nom'))

    def clean_prenoms(self):
        return self._sans_chiffre(self.cleaned_data.get('prenoms'))

    def clean_telephone(self):
        return self._valider_numero_ivoirien(self.cleaned_data.get('telephone'))

    def clean_telephone2(self):
        return self._valider_numero_ivoirien(self.cleaned_data.get('telephone2'))

    def clean(self):
        cleaned = super().clean()
        # Sans centre connu, on ne sait ni où ranger la fiche ni à quoi la
        # comparer : le garde-fou des doublons tournerait à vide et le
        # dossier atterrirait nulle part. Un super-utilisateur ne fait pas
        # exception — il choisit son centre comme tout le monde.
        if self._centre_connu() is None:
            raise forms.ValidationError(CHOISIR)
        nom            = (cleaned.get('nom') or '').strip()
        prenoms        = (cleaned.get('prenoms') or '').strip()
        date_naissance = cleaned.get('date_naissance')
        telephone      = (cleaned.get('telephone') or '').strip()

        # Le contrôle ne cherchait qu'une fiche strictement identique sur les
        # quatre champs : une lettre de différence dans le prénom suffisait à
        # passer, et c'est précisément ainsi que naissent les doublons. Il
        # passe désormais par `patients.doublons`, qui mesure la ressemblance.
        self.doublons = self._chercher_doublons(nom, prenoms, date_naissance, telephone)
        self.meme_telephone = self._compter_meme_telephone(telephone)
        self._appliquer_garde_fou(cleaned)
        return cleaned

    # ── Doublons ───────────────────────────────────────────────────────────

    def _centre_connu(self):
        """Le centre de ce formulaire : celui qu'on lui a passé, ou celui de
        la fiche qu'il modifie. Jamais deviné."""
        if self.centre is not None:
            return self.centre.pk if hasattr(self.centre, 'pk') else self.centre
        if self.instance and self.instance.centre_id:
            return self.instance.centre_id
        return None

    def _perimetre(self):
        """Toujours un périmètre explicite, et jamais « tous les centres ».

        `Patient.objects` s'appuie sur le centre actif, qui n'existe pas hors
        requête (commande, tâche de fond) : ceux-là passent le leur. Sans
        centre du tout, le périmètre est vide — et `clean` a déjà refusé le
        formulaire, pour que ce vide ne passe jamais pour « aucun doublon ».
        """
        centre_id = self._centre_connu()
        if centre_id is None:
            return Patient.all_objects.none()
        return Patient.all_objects.filter(centre_id=centre_id)

    def _chercher_doublons(self, nom, prenoms, date_naissance, telephone):
        if not (nom or prenoms):
            return []
        from .doublons import chercher_doublons
        saisie = {
            'nom': nom, 'prenoms': prenoms, 'date_naissance': date_naissance,
            'sexe': self.cleaned_data.get('sexe'),
            'telephone': telephone,
            'telephone2': (self.cleaned_data.get('telephone2') or '').strip(),
            'date_precise': not self.cleaned_data.get('date_naissance_approx'),
        }
        return chercher_doublons(saisie, exclure_pk=self.instance.pk if self.instance else None,
                                 queryset=self._perimetre())

    def _compter_meme_telephone(self, telephone):
        """Pour information seulement : un numéro partagé est courant dans une
        famille, il ne prouve rien et ne doit donc jamais bloquer."""
        from .doublons import normaliser_telephone
        tel = normaliser_telephone(telephone)
        if not tel:
            return 0
        qs = self._perimetre().filter(telephone__endswith=tel[-8:])
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs.count()

    def peut_forcer(self):
        return bool(self.utilisateur
                    and self.utilisateur.has_perm('patients.forcer_creation_doublon'))

    def _appliquer_garde_fou(self, cleaned):
        """Refuse, demande confirmation, ou laisse passer.

        En modification, jamais de refus : deux fiches déjà en double doivent
        rester modifiables, sans quoi on ne pourrait même plus corriger celle
        qu'on s'apprête à fusionner.
        """
        from .doublons import SEUIL_BLOCAGE

        if not self.doublons:
            return
        edition = bool(self.instance and self.instance.pk)
        bloquants = [c for c in self.doublons if c.score >= SEUIL_BLOCAGE]

        if bloquants and not edition:
            if not self.peut_forcer():
                raise forms.ValidationError(self._message_blocage(bloquants[0]))
            if not cleaned.get('forcer_doublon'):
                raise forms.ValidationError(self._message_blocage(bloquants[0]))
            raison = (cleaned.get('raison_forcage') or '').strip()
            if not raison:
                self.add_error('raison_forcage',
                               'Indiquez pourquoi ce dossier doit être créé malgré tout.')
                return
            self.forcage = (raison, bloquants[0])
            return

        if not cleaned.get('doublon_confirme'):
            proche = self.doublons[0]
            raise forms.ValidationError(
                f'Un dossier ressemblant existe déjà : {self._decrire(proche)}. '
                "Cochez « J'ai vérifié, c'est une autre personne » pour continuer.")

    def _message_blocage(self, correspondance):
        return (f'Ce dossier existe déjà : {self._decrire(correspondance)}. '
                'Ouvrez la fiche existante plutôt que d\'en créer une seconde.')

    @staticmethod
    def _decrire(correspondance):
        p = correspondance.patient
        ne_le = (f', né(e) le {p.date_naissance.strftime("%d/%m/%Y")}'
                 if p.date_naissance else '')
        raisons = ', '.join(correspondance.raisons)
        return (f'{p.code_patient} — {p.nom} {p.prenoms}{ne_le}, tél. {p.telephone} '
                f'({correspondance.score} % : {raisons})')

    def save(self, commit=True):
        """La case « date approximative » fait foi quand elle est affichée.

        Elle l'est depuis l'étape 2 : la personne qui ouvre le dossier voit
        l'état et le corrige. Le formulaire rendu la renvoie cochée, modifier
        le téléphone ne l'efface donc pas.

        La règle automatique de l'étape 1 ne sert plus que de filet pour les
        appels où la case n'est pas rendue : une date saisie à la main est une
        date certaine, mais seulement si le champ a réellement changé.
        """
        if ('date_naissance_approx' not in self.fields
                and 'date_naissance' in self.changed_data):
            self.instance.date_naissance_approx = False
        return super().save(commit=commit)


class RendezVousForm(forms.ModelForm):
    class Meta:
        model = RendezVous
        fields = ['patient', 'departement', 'medecin', 'type_consultation', 'date_heure', 'motif', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': _ul, 'id': 'id_patient'}),
            'departement': forms.Select(attrs={'class': _ul}),
            'medecin': DepartementFiltreSelect(attrs={'class': _ul}),
            'type_consultation': DepartementFiltreSelect(attrs={'class': _ul}),
            # `step=1` ouvre les secondes : sans lui le sélecteur du
            # navigateur s'arrête à la minute et enregistre toujours « :00 ».
            # La lecture n'a pas besoin d'être élargie — forms.DateTimeField
            # passe d'abord par parse_datetime, qui lit l'ISO 8601 complet.
            'date_heure': forms.DateTimeInput(
                attrs={'class': _ul, 'type': 'datetime-local', 'step': '1'},
                format='%Y-%m-%dT%H:%M:%S',
            ),
            'motif': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Motif de la visite...',
            }),
            'notes': forms.Textarea(attrs={
                'class': _ul, 'rows': 3, 'placeholder': 'Notes internes...',
            }),
        }

    def __init__(self, *args, locked_billing=False, **kwargs):
        from services.models import Articleservice
        from medecins.models import Departement, Medecin
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = Patient.objects.all().order_by('nom', 'prenoms')
        self.fields['patient'].empty_label = '— Sélectionner un patient —'
        self.fields['departement'].queryset = Departement.objects.filter(actif=True).order_by('nom')
        self.fields['departement'].empty_label = '— Choisir un département —'
        self.fields['departement'].required = True
        if locked_billing:
            # Une fois le rendez-vous confirmé et facturé, le département et le
            # type de consultation ne doivent plus changer : la facture a déjà
            # été émise sur cette base.
            self.fields['departement'].disabled = True
            self.fields['type_consultation'].disabled = True

        medecin_qs = Medecin.objects.filter(actif=True).select_related('employe').order_by('employe__nom', 'employe__prenoms')
        self.fields['medecin'].queryset = medecin_qs
        self.fields['medecin'].empty_label = '— Aucun médecin —'
        self.fields['medecin'].required = False
        self.fields['medecin'].widget.departement_map = {
            str(pk): departement_id
            for pk, departement_id in medecin_qs.values_list('pk', 'departement_id')
        }

        type_consultation_qs = Articleservice.objects.filter(
            actif=True, categorie__code='CS'
        ).select_related('departement').order_by('nom')
        self.fields['type_consultation'].queryset = type_consultation_qs
        self.fields['type_consultation'].empty_label = '— Choisir un type de consultation —'
        self.fields['type_consultation'].required = False
        self.fields['type_consultation'].widget.departement_map = {
            str(pk): departement_id
            for pk, departement_id in type_consultation_qs.values_list('pk', 'departement_id')
        }

    MESSAGE_TYPE_REQUIS = 'Choisissez un type de consultation avant de facturer.'

    def exiger_type_consultation(self):
        """« Sauvegarder et facturer » part sur la facture, dont la désignation
        est le type de consultation : sans lui, il n'y a rien à facturer.
        Sert aux deux créations (patients et gynécologie)."""
        champ = self.fields['type_consultation']
        champ.required = True
        champ.error_messages['required'] = self.MESSAGE_TYPE_REQUIS


class PathologieForm(forms.ModelForm):
    class Meta:
        model = Pathologie
        fields = ['nom', 'categorie', 'departement', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom de la pathologie',
            }),
            'categorie': forms.Select(attrs={'class': _ul}),
            'departement': forms.Select(attrs={'class': _ul}),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['departement'].queryset = self.fields['departement'].queryset.order_by('nom')
        self.fields['departement'].empty_label = '— Aucun —'


class TypeVisiteForm(forms.ModelForm):
    class Meta:
        model = TypeVisite
        fields = ['nom', 'code', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom du type de visite',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex: CPN01',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 3,
                'placeholder': 'Description optionnelle...',
            }),
        }


class TypeVisiteCurativeForm(forms.ModelForm):
    """Types de visite des consultations curatives, pendant de TypeVisiteForm
    (gynécologie). Le code est repris tel quel dans le registre curatif et lu
    par les rapports : le modifier sur un type déjà utilisé casserait leur
    comptage."""

    class Meta:
        model = TypeVisiteCurative
        fields = ['nom', 'code', 'description', 'actif']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Nom du type de visite',
            }),
            'code': forms.TextInput(attrs={
                'class': _ul,
                'placeholder': 'Ex: consultant',
            }),
            'description': forms.Textarea(attrs={
                'class': _ul,
                'rows': 2,
                'placeholder': 'Description (optionnel)',
            }),
        }
