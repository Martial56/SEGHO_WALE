"""
Calculs pour le Rapport mensuel d'activité : Médecine Générale, à partir des
données saisies dans le registre de consultation curative (voir
templates/patients/rendez_vous_form.html, onglet « Curatif »).

Comme pour la maternité (voir maternite.py), il n'existe pas de modèle dédié
au rapport papier : chaque consultation est une ligne RendezVous filtrée sur
departement__code='medg', et le détail clinique (mode d'entrée, type de
visite, diagnostics retenus, MILDA...) est stocké en JSON libre dans
RegistreCuratif.donnees (préfixe cur_). Les indicateurs sans champ
correspondant (cas référés, dépistage VIH des IST, violences basées sur le
genre, tétanos néonatal, ver de Guinée) sont retournés à None — le template
les affiche en case vide, à remplir à la main comme sur le formulaire papier
d'origine.

Les sections A/B/C/D (maladies infectieuses / autres maladies non infectieuses /
IST / maladies à déclaration obligatoire) sont pilotées par le catalogue
patients.Pathologie, filtré sur `departement__code='medg'` et `categorie`
('infectieuse' / 'non_infectieuse' / 'ist' / 'epidemiologie') — même principe
que rapports/gynecologie.py pour ses propres tableaux. Une ligne du tableau
existe si et seulement si une Pathologie du catalogue porte cette catégorie ;
ajouter/retirer une maladie du formulaire papier se fait donc en retaguant le
catalogue (écran de gestion des pathologies, patients/views.py:pathologie_list/
edit), pas en éditant ce module.
La recatégorisation initiale (depuis l'ancien matching par nom exact) est
faite par patients/migrations/0031_pathologie_med_generale_categories.py
(infectieuse/non_infectieuse/ist) et 0033_pathologie_epidemiologie_categorie.py
(epidemiologie).

Note sur le code département : la migration medecins/0015_replace_departements_
defaut.py vise à nommer ce département 'MEDGEN', mais elle n'est PAS appliquée
sur cette base (voir `manage.py showmigrations medecins`) — le département
réellement présent en base s'appelle 'medg' (créé par un chemin antérieur/
manuel). Si cette migration est un jour appliquée telle quelle, elle créera un
second département 'MEDGEN' en doublon (get_or_create ne trouvera pas 'medg'),
sans mettre à jour ce module — vérifier `Departement.objects.values('code',
'nom')` avant de modifier DEPARTEMENT_CODE ci-dessous.
"""
import calendar
from datetime import date

DEPARTEMENT_CODE = 'medg'

BRACKETS = [
    ('b0_11m', '0-11 mois'), ('b1_4', '1-4 ans'), ('b5_9', '5-9 ans'),
    ('b10_14', '10-14 ans'), ('b15_19', '15-19 ans'), ('b20_24', '20-24 ans'),
    ('b25_49', '25-49 ans'), ('b50p', '50 ans et plus'),
]


def _bracket(date_naissance, date_ref):
    if not date_naissance or not date_ref:
        return None
    jours = (date_ref - date_naissance).days
    if jours < 0:
        return None
    mois = jours / 30.4368
    ans = jours / 365.25
    if mois < 12:
        return 'b0_11m'
    if ans < 5:
        return 'b1_4'
    if ans < 10:
        return 'b5_9'
    if ans < 15:
        return 'b10_14'
    if ans < 20:
        return 'b15_19'
    if ans < 25:
        return 'b20_24'
    if ans < 50:
        return 'b25_49'
    return 'b50p'


def _nouvelle_grille():
    return {cle: {'F': 0, 'M': 0} for cle, _ in BRACKETS}


def calculer_rapport_med_generale(annee, mois):
    from patients.models import Patient, Pathologie, RegistreCuratif

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])
    periode = [premier_jour, dernier_jour]

    pathos_infectieuses = list(
        Pathologie.objects.filter(departement__code=DEPARTEMENT_CODE, categorie='infectieuse').order_by('nom')
    )
    pathos_non_infectieuses = list(
        Pathologie.objects.filter(departement__code=DEPARTEMENT_CODE, categorie='non_infectieuse').order_by('nom')
    )
    pathos_ist = list(
        Pathologie.objects.filter(departement__code=DEPARTEMENT_CODE, categorie='ist').order_by('nom')
    )
    pathos_epidemiologie = list(
        Pathologie.objects.filter(departement__code=DEPARTEMENT_CODE, categorie='epidemiologie').order_by('nom')
    )

    patho_grilles = {
        p.pk: {'grille': _nouvelle_grille(), 'referes': {'F': 0, 'M': 0}}
        for p in pathos_infectieuses + pathos_non_infectieuses + pathos_ist + pathos_epidemiologie
    }

    activites = {
        'nouveaux_clients': _nouvelle_grille(),
        'consultants': _nouvelle_grille(),
        'consultations': _nouvelle_grille(),
        'referes': _nouvelle_grille(),
        'assures': _nouvelle_grille(),
    }
    milda = {'eligibles': {'F': 0, 'M': 0}, 'recus': {'F': 0, 'M': 0}}

    registres = RegistreCuratif.objects.filter(
        rdv__departement__code=DEPARTEMENT_CODE, rdv__date_heure__date__range=periode,
    ).select_related('rdv', 'rdv__patient')

    for reg in registres:
        rdv = reg.rdv
        patient = rdv.patient
        sexe = patient.sexe
        if sexe not in ('F', 'M'):
            continue
        bracket = _bracket(patient.date_naissance, rdv.date_heure.date())
        if not bracket:
            continue
        d = reg.donnees

        type_visite = d.get('cur_type_visite')
        if type_visite == 'consultant':
            activites['consultants'][bracket][sexe] += 1
        if type_visite in ('consultant', 'controle'):
            activites['consultations'][bracket][sexe] += 1

        refere = d.get('cur_issue_consultation') == 'refere_externe'
        if refere:
            activites['referes'][bracket][sexe] += 1

        if patient.assurance_id:
            activites['assures'][bracket][sexe] += 1

        if bracket == 'b1_4':
            if d.get('cur_milda_eligible') == 'oui':
                milda['eligibles'][sexe] += 1
            if d.get('cur_remise_milda') == 'oui':
                milda['recus'][sexe] += 1

        raw = d.get('cur_diagnostic') or []
        if isinstance(raw, str):
            raw = [raw] if raw else []
        pks = {int(v) for v in raw if str(v).strip().isdigit()}
        for pk in pks:
            entry = patho_grilles.get(pk)
            if entry is None:
                continue
            entry['grille'][bracket][sexe] += 1
            if refere:
                entry['referes'][sexe] += 1

    # ── Nouveaux clients : patients dont la date de création est dans le mois de rapportage ──
    for patient in Patient.objects.filter(date_creation__date__range=periode):
        if patient.sexe not in ('F', 'M'):
            continue
        bracket = _bracket(patient.date_naissance, patient.date_creation.date())
        if bracket:
            activites['nouveaux_clients'][bracket][patient.sexe] += 1

    def _total(grille):
        f = sum(v['F'] for v in grille.values())
        m = sum(v['M'] for v in grille.values())
        return {'F': f, 'M': m, 'total': f + m}

    def _lignes(pathos):
        return [
            {
                'label': p.nom,
                'data': patho_grilles[p.pk]['grille'],
                'total': _total(patho_grilles[p.pk]['grille']),
                'refere': patho_grilles[p.pk]['referes'],
            }
            for p in pathos
        ]

    activites_lignes = [
        {'label': 'Nombre de Nouveaux clients', 'data': activites['nouveaux_clients'], 'total': _total(activites['nouveaux_clients'])},
        {'label': 'Nombre de consultants', 'data': activites['consultants'], 'total': _total(activites['consultants'])},
        {'label': 'Nombre de consultations', 'data': activites['consultations'], 'total': _total(activites['consultations'])},
        {'label': 'Nombre de cas référés', 'data': activites['referes'], 'total': _total(activites['referes'])},
        {'label': 'Nombre de cas contre référés', 'data': None, 'total': None},
        {'label': 'Assurés', 'data': activites['assures'], 'total': _total(activites['assures'])},
    ]

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': calendar.month_name[mois].capitalize(),
        'brackets': BRACKETS,
        'activites_lignes': activites_lignes,
        'maladies_infectieuses': _lignes(pathos_infectieuses),
        'maladies_non_infectieuses': _lignes(pathos_non_infectieuses),
        'ist': _lignes(pathos_ist),
        'epidemiologie': _lignes(pathos_epidemiologie),
        'milda': milda,
    }
