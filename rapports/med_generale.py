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

Les 46 libellés de maladies des sections A/B/C sont rapprochés du catalogue
patients.Pathologie (choix cochés dans RegistreCuratif.donnees['cur_diagnostic'])
par correspondance exacte de nom — ce catalogue a justement été constitué à
partir de cette fiche papier (voir patients/migrations/0009_pathologie.py).

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


# ── A : Maladies infectieuses ──
SECTION_A = [
    ('a_palu_suspect', 'Cas suspect de paludisme', ['Cas suspect de Paludisme']),
    ('a_palu_suspect_fe', 'Cas suspect de paludisme FE', ['Cas suspect de Paludisme FE']),
    ('a_palu_simple', 'Cas de paludisme simple', ['Cas de Paludisme simple']),
    ('a_palu_simple_fe', 'Cas de paludisme simple chez FE', ['Cas de Paludisme simple chez FE']),
    ('a_palu_grave_refere', 'Cas suspect de palu grave référés', ['Cas suspect de Paludisme grave référé']),
    ('a_palu_grave_refere_fe', 'Cas suspect de palu grave référés FE', ['Cas suspect de Paludisme grave référée chez FE']),
    ('a_palu_presume', 'Cas présumés de paludisme', ['Cas présumé de paludisme']),
    ('a_palu_presume_fe', 'Cas présumés de paludisme FE', ['Cas présumé de paludisme chez la FE']),
    ('a_diarrhee_sans_deshyd', 'Diarrhée aigüe sans déshydratation', ['Diarrhée aiguë sans déshydratation']),
    ('a_diarrhee_signes_deshyd', 'Diarrhée aigüe avec signes évidents de déshydratation', ['Diarrhée aiguë avec signes évidents de déshydratation']),
    ('a_diarrhee_deshyd_severe', 'Diarrhée aigüe avec déshydratation sévère', ['Diarrhée aiguë avec déshydratation sévère']),
    ('a_diarrhee_sanglante', 'Diarrhée aigüe sanglante', ['Diarrhée aiguë sanglante']),
    ('a_pneumonie_simple', 'Pneumonie Simple (IRA basse)', ['Pneumonie Simple (IRA basse)']),
    ('a_pneumonie_grave', 'Pneumonie grave (IRA basse)', ['Pneumonie grave (IRA basse)']),
    ('a_broncho_pneumonie', 'Broncho-pneumonie (IRA basse)', ['Broncho-pneumonie (IRA basse)']),
    ('a_otite', 'Otite moyenne aigue (IRA haute)', ['Otite moyenne aigue (IRA haute)']),
    ('a_rhinopharyngite', 'Rhinopharyngite (IRA haute)', ['Rhinopharyngite (IRA haute)']),
    ('a_angine', 'Angine (IRA haute)', ['Angine (IRA haute)']),
    ('a_sinusite', 'Sinusite (IRA haute)', ['Sinusite (IRA haute)']),
    ('a_laryngite', 'Laryngite (IRA haute)', ['Laryngite (IRA haute)']),
    ('a_pian', 'Pian', ['Pian']),
    ('a_bilharziose', 'Bilharziose urinaire (CS)', ['Bilharziose urinaire (CS)']),
    ('a_trichiasis', 'Trichiasis trachomateux (CS)', ['Trichiasis trachomateux (CS)']),
    ('a_hydrocele', "Cas suspects d'hydrocèle", ["Cas suspect d'hydrocèle"]),
    ('a_lymphoedeme', 'Cas suspects de lymphœdème', ['Cas suspects de lymphodoedème']),
    ('a_onchocercose', 'Onchocercose', ['Onchocercose']),
    ('a_tetanos', 'Tétanos', ['Tétanos']),
    ('a_coqueluche', 'Coqueluche', ['Coqueluche']),
    ('a_conjonctivite', 'Conjonctivite', ['Conjonctivite']),
    ('a_fievre_typhoide', 'Fièvre Typhoïde', ['Fièvre Typhoïde / Salmonellose']),
    ('a_fievre_jaune', 'Fièvre Jaune', ['Fièvre Jaune']),
    ('a_cholera', 'Choléra', ['Choléra']),
    ('a_meningite', 'Méningite', ['Méningite']),
    ('a_tuberculose', 'Tuberculose (CS)', ['Tuberculose (cas suspecte)']),
    ('a_ulcere_burili', 'Ulcère de burili (CS)', ['Ulcère de burili (cas suspect)']),
    ('a_varicelle', 'Varicelle', ['Varicelle']),
    ('a_dermatose', 'Dermatose', ['Dermatose']),
    ('a_zona', 'Zona', ['Zona']),
    ('a_hepatite_b', 'Hépatite viral B', ['Hépatite virale B']),
    ('a_hepatite_c', 'Hépatite viral C', ['Hépatite virale C']),
    ('a_autres_infectieuses', 'Autres Maladies infectieuses', ['Autres maladies infectieuses']),
    ('a_palu_simple_cta', 'Cas de Paludisme simple avec prescription de CTA (y compris femme enceinte)',
        ['Cas de paludisme simple avec prescription de CTA (y compris femmes enceintes)']),
    ('a_palu_simple_fe_cta', 'Cas de Paludisme simple chez la femme enceinte avec prescription de CTA',
        ['Cas de paludisme simple chez FE avec prescription de CTA']),
    ('a_palu_simple_fe_quinine', 'Cas de Paludisme simple chez la femme enceinte avec prescription de quinine comprimé',
        ['Cas de paludisme simple chez FE avec prescription de quinine']),
    ('a_palu_suspect_cta', 'Cas suspect de paludisme avec prescription de CTA (présumé), y compris femme enceinte',
        ['Cas suspect de paludisme avec prescription de CTA (présumé), y compris femme enceinte']),
    ('a_palu_suspect_fe_cta', 'Cas suspect de paludisme chez la femme enceinte avec prescription de CTA (présumé)',
        ['Cas suspect de paludisme chez la femme enceinte avec prescription de CTA (présumé)']),
    ('a_pneumonie_antibio', "Nombre d'enfants de moins de 5 ans atteints de la pneumonie et ayant reçu une prescription d'antibiotique",
        ["Nombre d'enfants atteints de la pneumonie et ayant reçu une prescription d'antibiotique"]),
    ('a_diarrhee_sro_zinc', "Nombre d'enfants de moins de 5 ans atteints de la diarrhée et ayant reçu une prescription de SRO + Zinc",
        ["Nombre d'enfants atteint de la diarrhée et ayant réçu une prescription de SRO + ZINC"]),
]

# ── B : Autres maladies non infectieuses et facteurs de risque cardiovasculaire ──
SECTION_B = [
    ('b_evaluation_nutritionnelle', 'Evaluation nutritionnelle', []),
    ('b_malnutrition_moderee', 'Malnutrition modérée', ['Malnutrition modérée']),
    ('b_malnutrition_severe', 'Malnutrition Aigüe sévère référé', ['Malnutrition aiguë sévère référé']),
    ('b_hta_sans_atcd', 'HTA sans antécédent de HTA connu chez les adultes, y compris FE',
        ["HTA sans antécédent de HTA connu chez l'adulte, y compris FE"]),
    ('b_hta_sans_atcd_fe', 'HTA sans antécédent de HTA connu chez les FE (adultes)',
        ['HTA sans antécédent de HTA connu chez les FE (adulte)']),
    ('b_hta_avec_atcd', 'HTA avec antécédent de HTA connu chez les adultes, y compris FE',
        ["HTA avec antécédent de HTA connu chez l'adulte, y compris FE"]),
    ('b_hta_avec_atcd_fe', 'HTA avec antécédent de HTA connu chez les femmes enceintes (adultes)',
        ['HTA avec antécédent de HTA connu chez les FE (adulte)']),
    ('b_hyperglycemie', 'Hyperglycémie sans antécédents de diabète connu',
        ['Hyperglycémie sans antécédent de diabète connu']),
    ('b_diabete_gestationnel', 'Diabète Gestationnel', ['Diabète gestationnel']),
    ('b_asthme', 'Asthme', ['Asthme']),
    ('b_drepanocytose', 'Drépanocytose', ['Drépanocytose']),
    ('b_insuffisance_renale', 'Insuffisance rénale aigüe', ['Insuffisance rénale aiguë']),
    ('b_accident_voie_publique', 'Accidenté de la voie publique', ['Accidenté de la voie publique']),
    ('b_troubles_psychiatriques', 'Troubles psychiatriques', ['Troubles psychiatriques']),
    ('b_retard_psychomoteur', 'Retard psychomoteurs', ['Retard psychomoteur']),
    ('b_anemie_moderee', 'Anémie modérée', ['Anémie modérée']),
    ('b_anemie_grave', 'Anémie grave', ['Anémie grave']),
    ('b_geu', 'GEU', ['GEU']),
    ('b_fibrome', 'Fibrome utérin', ['Fibrome utérin']),
    ('b_appendicite', 'Appendicite', ['Appendicite']),
    ('b_occlusion', 'Occlusion intestinale', ['Occlusion intestinale']),
    ('b_hernie', 'Hernie', ['Hernie']),
    ('b_peritonite', 'Péritonite', ['Péritonite']),
    ('b_goitre', 'Goitre', ['Goitre']),
    ('b_brulure', 'Brûlure', ['Brûlure']),
    ('b_avc', 'Accident vasculaire cérébral (AVC)', ['Accident vasculaire cérébral (AVC)']),
    ('b_morsure_serpent', 'Morsure de serpent', ['Morsure de serpent']),
    ('b_tentative_suicide', 'Tentative de suicide', ['Tentative de suicide']),
    ('b_autres_traumatismes', 'Autres traumatismes', ['Autres traumatismes']),
    ('b_maladie_indeterminee', 'Maladie indéterminée', ['Maladies indéterminées']),
    ('b_autres_non_infectieuses', 'Autres Maladies non infectieuses', ['Autres maladies non infectieuses']),
]

# ── C : Infections sexuellement transmissibles ──
SECTION_C = [
    ('c_ecoulement_uretral', "Écoulement urétral masculin et/ou douleur et/ou prurit et/ou gêne intra urétral",
        ['Écoulement urétral masculin et/ou douleur et/ou prurit et/ou gêne intra urétral']),
    ('c_ecoulement_vaginal', "Écoulement vaginal et /ou brûlure ou prurit et/ou mal odeur vaginale",
        ['Écoulement vaginal et/ou brûlure ou prurit et/ou malodeur vaginale']),
    ('c_ulceration_genitale', 'Ulcération génitale et/ou bubon',
        ['Ulcération génitale et/ou bubon masculin', 'Ulcération génitale et/ou bubon féminin']),
    ('c_douleur_testiculaire', 'Douleur testiculaire', ['Douleur testiculaire']),
    ('c_douleur_pelvienne', 'Douleurs abdominale basse (pelviennes) chez la femme',
        ['Douleurs abdominales basses (pelviennes) chez la femme']),
    ('c_conjonctivite_nne', 'Conjonctivite du nouveau-né', ['Conjonctivite du nouveau-né']),
    ('c_condylome', 'Condylome (végétation vénériennes ou crêtes de cop)',
        ['Condylome (végétation vénériennes ou crêtes de coq) masculin',
         'Condylome (végétation vénériennes ou crêtes de coq) féminin']),
]


def calculer_rapport_med_generale(annee, mois):
    from patients.models import Patient, Pathologie, RegistreCuratif

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])
    periode = [premier_jour, dernier_jour]

    toutes_lignes = SECTION_A + SECTION_B + SECTION_C
    tous_noms = {nom for _, _, noms in toutes_lignes for nom in noms}

    nom_vers_pk = dict(Pathologie.objects.filter(nom__in=tous_noms).values_list('nom', 'pk'))
    pk_vers_cles = {}
    for row_key, _, noms in toutes_lignes:
        for nom in noms:
            pk = nom_vers_pk.get(nom)
            if pk is not None:
                pk_vers_cles.setdefault(pk, []).append(row_key)

    maladies = {row_key: _nouvelle_grille() for row_key, _, _ in toutes_lignes}
    maladies_referes = {row_key: {'F': 0, 'M': 0} for row_key, _, _ in toutes_lignes}

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
        for v in raw:
            try:
                pk = int(v)
            except (TypeError, ValueError):
                continue
            for row_key in pk_vers_cles.get(pk, ()):
                maladies[row_key][bracket][sexe] += 1
                if refere:
                    maladies_referes[row_key][sexe] += 1

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

    def _lignes(section):
        return [
            {
                'key': row_key, 'label': label, 'data': maladies[row_key], 'total': _total(maladies[row_key]),
                'refere': maladies_referes[row_key],
            }
            for row_key, label, _ in section
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
        'maladies_infectieuses': _lignes(SECTION_A),
        'maladies_non_infectieuses': _lignes(SECTION_B),
        'ist': _lignes(SECTION_C),
        'milda': milda,
    }
