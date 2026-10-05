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

Disposition : le rapport reproduit à l'identique la fiche papier « Fiche de
rapport mensuel de consultations » (6 pages, voir FICHE_A / FICHE_B / FICHE_C
ci-dessous) — mêmes lignes, même ordre, mêmes coupures de page, mêmes cases
grisées. Chaque ligne de la fiche est rapprochée des pathologies du catalogue
patients.Pathologie (`departement__code='medg'`, `categorie` 'infectieuse' /
'non_infectieuse' / 'ist') par nom normalisé (sans accents, casse, espaces ni
ponctuation) ou par l'un de ses alias : plusieurs entrées du catalogue peuvent
alimenter la même ligne (doublons de saisie, variantes masculin/féminin), et une
ligne de la fiche reste affichée (à 0) même sans pathologie correspondante.
Une pathologie de la catégorie absente de la fiche (ajoutée plus tard au
catalogue) est ajoutée juste après la dernière ligne de sa catégorie, dans
l'ordre de création. La catégorie 'epidemiologie', absente de la fiche, est
rendue en annexe après la page des signatures.
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

from .fiche import ranger_selon_fiche
from .periode import nom_du_mois

DEPARTEMENT_CODE = 'medg'

BRACKETS = [
    ('b0_11m', '0-11 mois'), ('b1_4', '1-4 ans'), ('b5_9', '5-9 ans'),
    ('b10_14', '10-14 ans'), ('b15_19', '15-19 ans'), ('b20_24', '20-24 ans'),
    ('b25_49', '25-49 ans'), ('b50p', '50 ans et plus'),
]

#: Tranches des sections C (IST) et D (dépistage VIH) de la fiche : pas de
#: colonne entre 29 jours et 9 ans.
BRACKETS_IST = [
    ('j0_28', '0-28 jours'), ('b10_14', '10-14 ans'), ('b15_19', '15-19 ans'),
    ('b20_24', '20-24 ans'), ('b25_49', '25-49 ans'), ('b50p', '50 ans et plus'),
]

_FE = {('b0_11m', 'F'), ('b0_11m', 'M'), ('b1_4', 'F'), ('b1_4', 'M')}
_SRO = {(b, s) for b in ('b5_9', 'b10_14', 'b15_19', 'b20_24', 'b25_49') for s in 'FM'}
_IST_TOUS = [cle for cle, _ in BRACKETS_IST]
_NN = {('j0_28', 'F'), ('j0_28', 'M')}

# Lignes de la fiche papier, dans l'ordre et par page. Chaque ligne :
# (libellé imprimé, alias du catalogue, options). Options : 'grises' = cases
# (tranche, sexe) grisées sur la fiche ; 'refere_noir' = colonne « Cas
# référés » noircie ; 'separateur' = trait épais au-dessus de la ligne.
# Ne pas réordonner : l'ordre et les coupures de page sont ceux de la fiche.
FICHE_A = [
    [  # page 1
        ('Cas suspect de paludisme', [], {}),
        ('Cas suspect de paludisme FE', [], {'grises': _FE}),
        ('Cas de paludisme simple', [], {}),
        ('Cas de paludisme simple chez FE', [], {'grises': _FE}),
        ('Cas suspect de palu grave référés', ['Cas suspect de Paludisme grave référé'], {}),
        ('Cas suspect de palu grave référés FE', ['Cas suspect de Paludisme grave référée chez FE'], {'grises': _FE}),
        ('Cas présumés de paludisme', ['Cas présumé de paludisme'], {}),
        ('Cas présumés de paludisme FE', ['Cas présumé de paludisme chez la FE'], {}),
        ('Diarrhée aigüe sans déshydratation', [], {}),
        ('Diarrhée aigüe avec signes évidents de déshydratation', [], {}),
        ('Diarrhée aigüe avec déshydratation sévère', [], {}),
        ('Diarrhée aigüe sanglante', [], {}),
        ('Pneumonie Simple (IRA basse)', [], {}),
        ('Pneumonie grave (IRA basse)', [], {}),
    ],
    [  # page 2
        ('Broncho-pneumonie (IRA basse)', [], {}),
        ('Otite moyenne aigue (IRA haute)', [], {}),
        ('Rhinopharyngite (IRA haute)', [], {}),
        ('Angine (IRA haute)', [], {}),
        ('Sinusite (IRA haute)', [], {}),
        ('Laryngite (IRA haute)', [], {}),
        ('Pian', [], {}),
        ('Bilharziose urinaire (CS)', [], {}),
        ('Trichiasis trachomateux (CS)', [], {}),
        ("Cas suspects d'hydrocèle", ["Cas suspect d'hydrocèle"], {}),
        ('Cas suspects de lymphœdème', ['Cas suspects de lymphodoedème'], {}),
        ('Onchocercose', [], {}),
        ('Tétanos', [], {}),
        ('Coqueluche', [], {}),
        ('Conjonctivite', [], {}),
        ('Fièvre Typhoïde', ['Fièvre Typhoïde / Salmonellose'], {}),
        ('Fièvre Jaune', [], {}),
        ('Choléra', [], {}),
        ('Méningite', [], {}),
        ('Tuberculose (CS)', ['Tuberculose (cas suspecte)', 'Tuberculose (cas suspect)'], {}),
        ('Ulcère de burili (CS)', ['Ulcère de burili (cas suspect)'], {}),
        ('Varicelle', [], {}),
        ('Dermatose', [], {}),
        ('Zona', [], {}),
        ('Hépatite viral B', ['Hépatite virale B'], {}),
        ('Hépatite viral C', ['Hépatite virale C'], {}),
        ('Autres Maladies infectieuses', [], {}),
        ('Cas de Paludisme simple avec prescription de CTA (y compris femme enceinte)',
         ['Cas de paludisme simple avec prescription de CTA (y compris femmes enceintes)'],
         {'separateur': True, 'refere_noir': True}),
    ],
    [  # page 3
        ('Cas de Paludisme simple chez la femme enceinte avec prescription de CTA',
         ['Cas de paludisme simple chez FE avec prescription de CTA'], {}),
        ('Cas de Paludisme simple chez la femme enceinte avec prescription de quinine comprimé',
         ['Cas de paludisme simple chez FE avec prescription de quinine'], {}),
        ('Cas suspect de paludisme avec prescription de CTA (présumé), y compris femme enceinte', [], {}),
        ('Cas suspect de paludisme chez la femme enceinte avec prescription de CTA (présumé)', [], {}),
        ("Nombre d'enfants de moins de 5 ans atteints de la pneumonie et ayant reçu une prescription d'antibiotique",
         ["Nombre d'enfants atteints de la pneumonie et ayant reçu une prescription d'antibiotique"], {}),
        ("Nombre d'enfants de moins de 5 ans atteints de la diarrhée et ayant reçu une prescription de SRO + Zinc",
         ["Nombre d'enfants atteint de la diarrhée et ayant réçu une prescription de SRO + ZINC",
          "Nombre d'enfants atteints de la diarrhée et ayant reçu une prescription de SRO + Zinc"],
         {'grises': _SRO}),
    ],
]

FICHE_B = [
    [  # page 3
        ('Evaluation nutritionnelle', [], {}),
        ('Malnutrition modérée', [], {}),
        ('Malnutrition Aigüe sévère référé', [], {}),
        ('HTA sans antécédent de HTA connu chez les adultes, y compris FE',
         ["HTA sans antécédent de HTA connu chez l'adulte, y compris FE"], {}),
        ('HTA sans antécédent de HTA connu chez les FE (adultes)',
         ['HTA sans antécédent de HTA connu chez les FE (adulte)'], {}),
        ('HTA avec antécédent de HTA connu chez les adultes, y compris FE',
         ["HTA avec antécédent de HTA connu chez l'adulte, y compris FE"], {}),
        ('HTA avec antécédent de HTA connu chez les femmes enceintes (adultes)',
         ['HTA avec antécédent de HTA connu chez les FE (adulte)'], {}),
    ],
    [  # page 4
        ('Hyperglycémie sans antécédents de diabète connu',
         ['Hyperglycémie sans antécédent de diabète connu', 'Hyperglicémie sans antecedent de diabète connu'], {}),
        ('Diabète Gestationnel', [], {}),
        ('Asthme', [], {}),
        ('Drépanocytose', [], {}),
        ('Insuffisance rénale aigüe', [], {}),
        ('Accidenté de la voie publique', [], {}),
        ('Troubles psychiatriques', [], {}),
        ('Retard psychomoteurs', ['Retard psychomoteur'], {}),
        ('Anémie modérée', [], {}),
        ('Anémie grave', [], {}),
        ('GEU', [], {}),
        ('Fibrome utérin', [], {}),
        ('Appendicite', [], {}),
        ('Occlusion intestinale', [], {}),
        ('Hernie', [], {}),
        ('Péritonite', [], {}),
        ('Goitre', [], {}),
        ('Brûlure', [], {}),
        ('Accident vasculaire cérébral (AVC)', [], {}),
        ('Morsure de serpent', [], {}),
        ('Tentative de suicide', [], {}),
        ('Autres traumatismes', ['Autres traumatisme'], {}),
        ('Maladie indéterminée', ['Maladies indéterminées'], {}),
        ('Autres Maladies non infectieuses', [], {}),
    ],
]

FICHE_C = [
    ('Écoulement urétral masculin et/ou douleur et/ou prurit et/ou gêne intra urétral', [],
     {'grises': {(b, 'F') for b in _IST_TOUS} | {('j0_28', 'M')}}),
    ('Écoulement vaginal et /ou brûlure ou prurit et/ou mal odeur vaginale', [],
     {'grises': {(b, 'M') for b in _IST_TOUS} | {('j0_28', 'F')}}),
    ('Ulcération génitale et/ou bubon',
     ['Ulcération génitale et/ou bubon masculin', 'Ulcération génitale et/ou bubon féminin'],
     {'grises': _NN}),
    ('Douleur testiculaire', [], {'grises': {(b, 'F') for b in _IST_TOUS} | _NN}),
    ('Douleurs abdominale basse (pelviennes) chez la femme',
     ['Douleurs abdominales basses (pelviennes) chez la femme'],
     {'grises': {(b, 'M') for b in _IST_TOUS} | _NN}),
    ('Conjonctivite du nouveau-né', [],
     {'grises': {(b, s) for b in _IST_TOUS if b != 'j0_28' for s in 'FM'}}),
    ('Condylome (végétation vénériennes ou crêtes de cop)',
     ['Condylome (végétation vénériennes ou crêtes de coq) masculin',
      'Condylome (végétation vénériennes ou crêtes de coq) féminin'],
     {'grises': _NN}),
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


def _bracket_ist(date_naissance, date_ref):
    if not date_naissance or not date_ref:
        return None
    jours = (date_ref - date_naissance).days
    if jours < 0:
        return None
    if jours <= 28:
        return 'j0_28'
    bracket = _bracket(date_naissance, date_ref)
    return bracket if bracket in dict(BRACKETS_IST) else None


def _nouvelle_grille(brackets=BRACKETS):
    return {cle: {'F': 0, 'M': 0} for cle, _ in brackets}


def calculer_rapport_med_generale(annee, mois):
    from patients.models import Patient, Pathologie, RegistreCuratif

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])
    periode = [premier_jour, dernier_jour]

    # Tri par pk = ordre de création : les pathologies hors fiche s'ajoutent
    # dans l'ordre où elles ont été créées.
    pathos = {
        cat: list(Pathologie.objects.filter(departement__code=DEPARTEMENT_CODE, categorie=cat).order_by('pk'))
        for cat in ('infectieuse', 'non_infectieuse', 'ist', 'epidemiologie')
    }

    patho_grilles = {
        p.pk: {'grille': _nouvelle_grille(), 'grille_ist': _nouvelle_grille(BRACKETS_IST),
               'referes': {'F': 0, 'M': 0}}
        for liste in pathos.values() for p in liste
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
        date_visite = rdv.date_heure.date()
        bracket = _bracket(patient.date_naissance, date_visite)
        if not bracket:
            continue
        bracket_ist = _bracket_ist(patient.date_naissance, date_visite)
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
            if bracket_ist:
                entry['grille_ist'][bracket_ist][sexe] += 1
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

    def _ligne(label, pks, brackets, cle_grille, grises=frozenset(), refere_noir=False, separateur=False):
        """Ligne prête à rendre : une cellule par (tranche, sexe), les deux
        cellules « Total », puis les deux cellules « Cas référés », en sommant
        toutes les pathologies `pks`."""
        cellules = []
        totaux = {'F': 0, 'M': 0}
        for cle, _ in brackets:
            for sexe in ('F', 'M'):
                val = sum(patho_grilles[pk][cle_grille][cle][sexe] for pk in pks)
                totaux[sexe] += val
                cellules.append({'val': val, 'grise': (cle, sexe) in grises})
        for sexe in ('F', 'M'):
            cellules.append({'val': totaux[sexe], 'total': True})
        for sexe in ('F', 'M'):
            val = sum(patho_grilles[pk]['referes'][sexe] for pk in pks)
            cellules.append({'val': val, 'refere': True, 'noir': refere_noir})
        return {'label': label, 'cellules': cellules, 'separateur': separateur}

    def _section(pages_fiche, pathos_cat, brackets, cle_grille='grille'):
        return ranger_selon_fiche(pages_fiche, pathos_cat, lambda label, pks, opts: _ligne(
            label, pks, brackets, cle_grille,
            grises=opts.get('grises', frozenset()),
            refere_noir=opts.get('refere_noir', False),
            separateur=opts.get('separateur', False)))

    a_pages = _section(FICHE_A, pathos['infectieuse'], BRACKETS)
    b_pages = _section(FICHE_B, pathos['non_infectieuse'], BRACKETS)
    (ist_lignes,) = _section([FICHE_C], pathos['ist'], BRACKETS_IST, 'grille_ist')
    (epidemiologie,) = _section([[]], pathos['epidemiologie'], BRACKETS)

    activites_lignes = [
        {'label': 'Nombre de Nouveaux clients', 'data': activites['nouveaux_clients'], 'total': _total(activites['nouveaux_clients'])},
        {'label': 'Nombre de consultant', 'data': activites['consultants'], 'total': _total(activites['consultants'])},
        {'label': 'Nombre de consultations', 'data': activites['consultations'], 'total': _total(activites['consultations'])},
        {'label': 'Nombre de cas référés', 'data': activites['referes'], 'total': _total(activites['referes'])},
        {'label': 'Nombre de cas contre référés', 'data': None, 'total': None},
        {'label': 'Assurés', 'data': activites['assures'], 'total': _total(activites['assures'])},
    ]

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': nom_du_mois(annee, mois),
        'brackets': BRACKETS,
        'brackets_ist': BRACKETS_IST,
        'activites_lignes': activites_lignes,
        'a_page1': a_pages[0],
        'a_page2': a_pages[1],
        'a_page3': a_pages[2],
        'b_page3': b_pages[0],
        'b_page4': b_pages[1],
        'ist': ist_lignes,
        'epidemiologie': epidemiologie,
        'milda': milda,
        # Sections D et E : pas de champ dans le registre curatif, cases vides à remplir à la main.
        'vih_lignes': [
            "Nombre de personnes atteintes d'une IST dépisté au VIH",
            "Nombre de personnes atteintes d'une IST dépisté positives au VIH",
        ],
        'vbg_lignes': [
            'Nombre de survivants aux violences sexuelles ayant consulté dans les 72 heures',
            "Nombre de survivants aux violences sexuelles pris en charge dans l'établissement",
            'Nombre de survivants aux violences sexuelles référés vers une autre structure',
        ],
    }
