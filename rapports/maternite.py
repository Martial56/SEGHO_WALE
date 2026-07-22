"""
Calculs pour le Rapport mensuel d'activité : Maternité (CPN / Accouchement /
Consultations postnatales), à partir des données saisies dans le workflow
gynécologie (voir templates/gynecologie/rdv_form.html).

Il n'existe pas de modèle « grossesse » reliant CPN1→CPN5→Accouchement→
Postnatal : chaque visite est une ligne RendezVous indépendante, et le détail
clinique (VAT, VIH/PMTCT, syphilis, AgHBs, SP1-5, MILDA, fer/folate...) est
stocké en JSON libre dans RegistreCPN/RegistreAccouchement/RegistrePostnatale
(un préfixe par formulaire : cpn_, acc_, cposo_). Les indicateurs sans champ
correspondant sont retournés à None — le template les affiche en case vide,
à remplir à la main (comme le formulaire papier d'origine).
"""
import calendar
from datetime import date

from django.db.models import Min

# Clés sans tiret (les templates Django ne peuvent pas faire de lookup
# "dict.8-14" — le tiret n'est pas un caractère de variable valide).
TRANCHES_AGE = [
    ('t8_14', '8-14 ans'), ('t15_19', '15-19 ans'), ('t20_24', '20-24 ans'),
    ('t25_49', '25-49 ans'), ('t50_plus', '50 ans et plus'),
]


def _tranche_age(age):
    if age is None:
        return None
    if age <= 14:
        return 't8_14'
    if age <= 19:
        return 't15_19'
    if age <= 24:
        return 't20_24'
    if age <= 49:
        return 't25_49'
    return 't50_plus'


def _age_a(date_naissance, date_ref):
    if not date_naissance or not date_ref:
        return None
    d = date_ref.date() if hasattr(date_ref, 'date') else date_ref
    return d.year - date_naissance.year - ((d.month, d.day) < (date_naissance.month, date_naissance.day))


def _oui(donnees, cle):
    return donnees.get(cle) == 'oui'


def _nouvelle_tranche_dict():
    return {cle: 0 for cle, _ in TRANCHES_AGE}


def calculer_rapport_maternite(annee, mois):
    from patients.models import RendezVous, RegistreCPN, RegistreAccouchement, RegistrePostnatale

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])
    periode = [premier_jour, dernier_jour]

    # ── A-1 : CPN — rang de visite (RendezVous.type_visite_cpn) ──
    rdv_cpn_periode = RendezVous.objects.filter(date_heure__date__range=periode).exclude(type_visite_cpn='')

    def compte_rang(*rangs):
        return rdv_cpn_periode.filter(type_visite_cpn__in=rangs).count()

    cpn1 = compte_rang('cpn1')
    cpn1_at = compte_rang('cpn1_at')
    premiere_visite_par_patient = (
        RendezVous.objects.exclude(type_visite_cpn='')
        .values('patient').annotate(premiere=Min('date_heure'))
    )
    nouvelles_patientes = premiere_visite_par_patient.filter(premiere__date__range=periode).count()

    cpn = {
        'nouvelles_patientes': nouvelles_patientes,
        'total_consultations': rdv_cpn_periode.count(),
        'cpn1': cpn1,
        'cpn1_at': cpn1_at,
        'total_cpn1': cpn1 + cpn1_at,
        'cpn2': compte_rang('cpn2', 'cpn2_at'),
        'cpn3': compte_rang('cpn3', 'cpn3_at'),
        'cpn4_at': compte_rang('cpn4_at'),
        'cpn4': compte_rang('cpn4'),
        'cpn5plus': compte_rang('cpn5plus'),
        'grossesses_a_risque': None,  # aucun champ dédié
    }

    # ── A-1 (suite) : dépistages/prescriptions CPN (RegistreCPN.donnees) ──
    registres_cpn = RegistreCPN.objects.filter(rdv__date_heure__date__range=periode).select_related('rdv')
    cpn_ind = {
        'anemiees': 0, 'malnutris': 0, 'syphilis_positif': 0, 'aghbs_positif': 0,
        'sp1': 0, 'sp2': 0, 'sp3': 0, 'sp4': 0, 'sp5': 0,
        'conseil_nutritionnel': 0, 'milda': 0, 'fer_folate': 0, 'deparasitees': 0,
    }
    depistage_conjoint = {'positif_chez_mere_pos': 0, 'negatif_chez_mere_pos': 0,
                           'positif_chez_mere_neg': 0, 'negatif_chez_mere_neg': 0}
    for reg in registres_cpn:
        d = reg.donnees
        if _oui(d, 'cpn_anemie'):
            cpn_ind['anemiees'] += 1
        if d.get('cpn_etat_nutritionnel') == 'mauvais':
            cpn_ind['malnutris'] += 1
        if d.get('cpn_resultat_syphilis') == 'positif':
            cpn_ind['syphilis_positif'] += 1
        if d.get('cpn_resultat_aghbs') == 'positif':
            cpn_ind['aghbs_positif'] += 1
        for n in ('1', '2', '3', '4', '5'):
            if _oui(d, f'cpn_sp{n}'):
                cpn_ind[f'sp{n}'] += 1
        if _oui(d, 'cpn_conseil_nutritionnel'):
            cpn_ind['conseil_nutritionnel'] += 1
        if _oui(d, 'cpn_milda'):
            cpn_ind['milda'] += 1
        if _oui(d, 'cpn_fer') and _oui(d, 'cpn_folates'):
            cpn_ind['fer_folate'] += 1
        if _oui(d, 'cpn_deparasitant'):
            cpn_ind['deparasitees'] += 1

        if _oui(d, 'cpn_depistage_conjoint'):
            mere_positive = d.get('cpn_statut_vih_accueil') == 'positif'
            conjoint_positif = d.get('cpn_statut_sero_conjoint') == 'positif'
            conjoint_negatif = d.get('cpn_statut_sero_conjoint') == 'negatif'
            if mere_positive and conjoint_positif:
                depistage_conjoint['positif_chez_mere_pos'] += 1
            elif mere_positive and conjoint_negatif:
                depistage_conjoint['negatif_chez_mere_pos'] += 1
            elif not mere_positive and conjoint_positif:
                depistage_conjoint['positif_chez_mere_neg'] += 1
            elif not mere_positive and conjoint_negatif:
                depistage_conjoint['negatif_chez_mere_neg'] += 1

    # ── VIH/PMTCT : 3 premières lignes, CPN1 uniquement ──
    registres_cpn1 = registres_cpn.filter(rdv__type_visite_cpn__in=['cpn1', 'cpn1_at'])
    vih_cpn1_connues = sum(1 for r in registres_cpn1 if r.donnees.get('cpn_statut_vih_accueil') == 'positif')
    vih_cpn1_deja_arv = sum(1 for r in registres_cpn1 if _oui(r.donnees, 'cpn_sous_arv'))
    vih_cpn1_resultat_recu = sum(1 for r in registres_cpn1 if _oui(r.donnees, 'cpn_annonce_resultat'))
    vih_cpn1 = {
        'deja_seropositives': vih_cpn1_connues,
        'deja_sous_arv': vih_cpn1_deja_arv,
        'resultat_recu': vih_cpn1_resultat_recu,
    }
    charge_virale_ok = sum(1 for r in registres_cpn if _oui(r.donnees, 'cpn_charge_virale'))

    # ── A-2 : Accouchement (RegistreAccouchement.donnees) ──
    registres_acc = RegistreAccouchement.objects.filter(
        rdv__date_heure__date__range=periode
    ).select_related('rdv', 'rdv__patient')

    lieu_etablissement = _nouvelle_tranche_dict()
    lieu_domicile = _nouvelle_tranche_dict()
    lieu_refere = _nouvelle_tranche_dict()
    vat = {'a_jour': 0, 'non_a_jour': 0, 'sans_vat': 0}
    issue = {
        'vivant': 0, 'mort_ne_frais': 0, 'mort_ne_macere': 0,
        'poids_faible': 0, 'prematures': 0, 'proteges_tetanos': 0,
        'multiples': 0, 'avortements_spontanes': 0, 'avortements_provoques': 0,
        'evacuation_nn': 0,
    }
    declaration = {'m': 0, 'f': 0}
    seropositives_accouchees = 0
    arv_nne_72h = 0

    for reg in registres_acc:
        d = reg.donnees
        rdv = reg.rdv
        age = _age_a(rdv.patient.date_naissance, rdv.date_heure)
        tranche = _tranche_age(age)

        lieu = d.get('acc_lieu_accouchement')
        if tranche:
            if lieu in ('cs', 'hopital'):
                lieu_etablissement[tranche] += 1
            elif lieu in ('domicile', 'en_route'):
                lieu_domicile[tranche] += 1
            if d.get('acc_mode_sortie') == 'transfere':
                lieu_refere[tranche] += 1

        statut_vat = d.get('acc_statut_vat')
        mere_a_jour = statut_vat in ('2', '3', '4', '5')
        if statut_vat == '0':
            vat['sans_vat'] += 1
        elif statut_vat == '1':
            vat['non_a_jour'] += 1
        elif mere_a_jour:
            vat['a_jour'] += 1

        etat = d.get('acc_etat_nouveau_ne')
        if etat == 'vivant':
            issue['vivant'] += 1
        elif etat == 'mort_ne':
            issue['mort_ne_frais'] += 1
        elif etat == 'macere':
            issue['mort_ne_macere'] += 1
        try:
            if float(d.get('acc_enfant_poids') or 0) > 0 and float(d['acc_enfant_poids']) < 2.5:
                issue['poids_faible'] += 1
        except (TypeError, ValueError):
            pass
        try:
            issue['prematures'] += int(d.get('acc_prematurite') or 0)
        except (TypeError, ValueError):
            pass
        try:
            issue['multiples'] += int(d.get('acc_gemelite') or 0)
        except (TypeError, ValueError):
            pass
        if mere_a_jour and etat == 'vivant':
            issue['proteges_tetanos'] += 1
        if d.get('acc_type_avortement') == 'spontane':
            issue['avortements_spontanes'] += 1
        elif d.get('acc_type_avortement') == 'provoque':
            issue['avortements_provoques'] += 1
        if _oui(d, 'acc_evacuation_nn'):
            issue['evacuation_nn'] += 1

        sexe = d.get('acc_enfant_sexe')
        if _oui(d, 'acc_fiche_naissance_renseignee') and sexe in ('m', 'f'):
            declaration[sexe] += 1

        mere_seropositive = d.get('acc_statut_vih_accueil') == 'positif' or _oui(d, 'acc_sous_arv')
        if mere_seropositive:
            seropositives_accouchees += 1
            if _oui(d, 'acc_prophylaxie_arv'):
                arv_nne_72h += 1

    vat['total'] = vat['a_jour'] + vat['non_a_jour'] + vat['sans_vat']
    lieu_lignes = [
        {
            'label': label,
            'etablissement': lieu_etablissement[cle],
            'domicile': lieu_domicile[cle],
            'total': lieu_etablissement[cle] + lieu_domicile[cle],
            'refere': lieu_refere[cle],
        }
        for cle, label in TRANCHES_AGE
    ]
    lieu_total_etablissement = sum(lieu_etablissement.values())
    lieu_total_domicile = sum(lieu_domicile.values())

    # ── Consultations postnatales (RegistrePostnatale.donnees) ──
    registres_post = RegistrePostnatale.objects.filter(
        rdv__date_heure__date__range=periode
    ).select_related('rdv')
    postnatales = {'immediate': 0, 'jusqu_6e_jour': 0, 'six_huit_semaines': 0}
    for reg in registres_post:
        t = reg.donnees.get('cposo_type_consultation')
        if t == 'j3':
            postnatales['immediate'] += 1
        elif t == 'j7':
            postnatales['jusqu_6e_jour'] += 1
        elif t in ('j28', 'j42'):
            postnatales['six_huit_semaines'] += 1
    postnatales['total'] = sum(postnatales.values())

    # ── VIH/PMTCT : lignes agrégées CPN + Accouchement + Postnatal ──
    def _somme(qs, cle):
        return sum(1 for r in qs if _oui(r.donnees, cle))

    vih_cascade = {}
    for label, cpn_cle, acc_cle, post_cle in [
        ('resultat_recu', 'cpn_annonce_resultat', 'acc_annonce_resultat', 'cposo_annonce_resultat'),
        ('retesting', 'cpn_retesting', 'acc_retesting', 'cposo_retesting'),
        ('initiation_arv', 'cpn_initiation_arv', 'acc_initiation_arv_vih', 'cposo_initiation_arv'),
    ]:
        c = _somme(registres_cpn, cpn_cle)
        a = _somme(registres_acc, acc_cle)
        p = _somme(registres_post, post_cle)
        vih_cascade[label] = {'cpn': c, 'accouchement': a, 'postnatal': p, 'total': c + a + p}

    def _somme_positif(qs, cle):
        return sum(1 for r in qs if r.donnees.get(cle) == 'positif')

    c = _somme_positif(registres_cpn, 'cpn_resultat_vih')
    a = _somme_positif(registres_acc, 'acc_resultat_vih')
    p = _somme_positif(registres_post, 'cposo_resultat_vih')
    vih_cascade['depistees_positives'] = {'cpn': c, 'accouchement': a, 'postnatal': p, 'total': c + a + p}

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': calendar.month_name[mois].capitalize(),
        'premier_jour': premier_jour,
        'dernier_jour': dernier_jour,
        'cpn': cpn,
        'cpn_indicateurs': cpn_ind,
        'lieu_accouchement': {
            'lignes': lieu_lignes,
            'total_etablissement': lieu_total_etablissement,
            'total_domicile': lieu_total_domicile,
            'total_refere': sum(lieu_refere.values()),
            'grand_total': lieu_total_etablissement + lieu_total_domicile,
        },
        'vat_accouchement': vat,
        'issue_accouchement': issue,
        'declaration_naissance': declaration,
        'postnatales': postnatales,
        'vih_cpn1': vih_cpn1,
        'vih_cascade': vih_cascade,
        'charge_virale_ok': charge_virale_ok,
        'depistage_conjoint': depistage_conjoint,
        'seropositives_accouchees': seropositives_accouchees,
        'arv_nne_72h': arv_nne_72h,
    }
