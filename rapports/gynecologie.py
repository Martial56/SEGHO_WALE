"""
Calculs pour la Fiche de rapport mensuel de consultations gynécologiques,
à partir des données saisies dans l'onglet Curatif du formulaire gynécologie
(voir templates/gynecologie/rdv_form.html).

Sources :
- cur_diagnostic       : pathologies sélectionnées (multi-select), classées
                         par Pathologie.categorie (grossesse / infectieuse /
                         autre_gyneco) — chaque catégorie alimente l'un des
                         3 tableaux de la fiche (A / B infectieuses / B autres).
- type de consultation du rendez-vous : Nombre de consultant = les rendez-vous
                         dont le type est une consultation gynécologique simple
                         ou gynéco-obstétrique (voir REFERENCES_CONSULTANT).
- cur_type_visite      : 'controle' complète le Nombre de consultations, qui
                         vaut donc consultants + contrôles.
- cur_issue_consultation == 'refere_externe' : cas référés.
- Cas contre référés : aucun champ correspondant — case vide à remplir à la main.

Le Nombre de consultant se lit sur le rendez-vous et non sur l'onglet Curatif :
le type de consultation est saisi à la prise du rendez-vous, donc toujours
présent, là où l'onglet Curatif est renseigné plus tard — quand il l'est. Compté
sur le registre curatif, le consultant manquait tous les rendez-vous dont
l'onglet n'avait pas été ouvert, et la fiche sortait vide.

Disposition : le rapport reproduit à l'identique la fiche papier « Fiche de
rapport mensuel de consultations gynécologiques » (3 pages, voir FICHE_GROSSESSE /
FICHE_INFECTIEUSE / FICHE_AUTRE ci-dessous) — mêmes lignes, même ordre, mêmes
coupures de page. Les lignes sont rapprochées du catalogue par nom normalisé ou
alias (voir fiche.py) ; une pathologie de la catégorie absente de la fiche est
ajoutée juste après la dernière ligne de sa catégorie, dans l'ordre de création.

Périmètre : uniquement les rendez-vous du module gynécologie (département
'GYN' ou médecin de spécialité gynécologie), comme pour le listing des RDV
gynécologie dans core/views.py.
"""
import calendar
from datetime import date

from .fiche import ranger_selon_fiche
from .periode import nom_du_mois

#: Références internes des types de consultation qui font un « consultant » de
#: la fiche. `Articleservice.reference_interne` est unique et mise en majuscules
#: à la sauvegarde : elle survit à un changement de libellé, contrairement au
#: nom de l'article ou à son identifiant.
REFERENCES_CONSULTANT = ('CS_CSGS', 'CS_GYNOBS')

AGE_BRACKETS = [
    ('a0_11m', '0-11 mois'),
    ('a1_4', '1-4 ans'),
    ('a5_9', '5-9 ans'),
    ('a10_14', '10-14 ans'),
    ('a15_19', '15-19 ans'),
    ('a20_24', '20-24 ans'),
    ('a25_49', '25-49 ans'),
    ('a50p', '50 et plus'),
]


# Lignes de la fiche papier, dans l'ordre et par page :
# (libellé imprimé, alias du catalogue, options).
# Ne pas réordonner : l'ordre et les coupures de page sont ceux de la fiche.
FICHE_GROSSESSE = [
    [  # page 1
        ('paludisme simple sur grossesse', ['paludisme sur grossesse'], {}),
        ("Menace d'accouchement Prématuré", [], {}),
        ('Rupture prématurée des membranes (24 – 34 SA)', [], {}),
        ('Rupture prématurée des membranes à terme', [], {}),
        ('Hépatite B', [], {}),
        ('Hépatite C', [], {}),
        ('Infection urinaire', [], {}),
        ('HTA et complications', ['HTA et complication'], {}),
        ('Mort in utéro', [], {}),
        ('Diabète gestationnel', [], {}),
        ('Diabète antérieur à la grossesse', [], {}),
        ('Utérus cicatriciel', [], {}),
        ('Grossesse prolongée', [], {}),
    ],
    [  # page 2
        ('Grossesse gemellaire', [], {}),
        ("Complication de l'allaitement", [], {}),
        # Remplace la ligne « Autres » de la fiche ; reste la dernière ligne
        # du tableau A, les pathologies hors fiche s'insèrent avant elle.
        ('Autres maladies infectieuses', [], {'en_dernier': True}),
    ],
]

FICHE_INFECTIEUSE = [
    [  # page 2
        ('Écoulement vaginal et /ou brûlure ou prurit et/ou malodeur vaginale', [], {}),
        ('Ulcération génitale et/ou bubon', [], {}),
        ('Douleurs abdominale basse (pelviennes) chez la femme', [], {}),
        ('Infection génitale haute', [], {}),
        ('Bartholinite', [], {}),
        ('Condylomes', [], {}),
    ],
]

FICHE_AUTRE = [
    [  # page 2
        ('Grossesse molaire', [], {}),
        ('G .E .V', [], {}),
        ('Avortement spontané', ['Avortement spontatné'], {}),
        ('Trouble du cycle', ['Troubles du cycle'], {}),
        ('Hémorragie génitale', [], {}),
        ('Aménorrhée', ['Aménorrhé'], {}),
        ('Désir de maternité', [], {}),
    ],
    [  # page 3
        ("Tumeurs bénignes de l'utérus", [], {}),
        ('Prolapsus génitaux', [], {}),
        ("Tumeurs et Kystes de l'ovaire", [], {}),
        ('Tumeurs bénignes et malignes du sein', [], {}),
        ('Mastopathie', [], {}),
        ('Incontinence urinaire', [], {}),
        ('Tumeurs malignes du col et état précancéreux', [], {}),
        ('Endométriose', [], {}),
        ('Adénomyose', [], {}),
        ('Synéchies', [], {}),
        ('Régulation des naissances', [], {}),
        ('GEU', [], {}),
        ('Complication obstétricales', [], {}),
        ('Fibrome utérin', ['Fibrome utérien'], {}),
        ('Violence sexuelle', [], {}),
    ],
]


def _age_bracket(date_naissance, reference_date):
    if not date_naissance or not reference_date:
        return None
    jours = (reference_date - date_naissance).days
    if jours < 0:
        return None
    mois = jours / 30.4368
    ans = jours / 365.25
    if mois < 12:
        return AGE_BRACKETS[0][0]
    if ans < 5:
        return AGE_BRACKETS[1][0]
    if ans < 10:
        return AGE_BRACKETS[2][0]
    if ans < 15:
        return AGE_BRACKETS[3][0]
    if ans < 20:
        return AGE_BRACKETS[4][0]
    if ans < 25:
        return AGE_BRACKETS[5][0]
    if ans < 50:
        return AGE_BRACKETS[6][0]
    return AGE_BRACKETS[7][0]


def _grille_vide():
    return {cle: {'F': 0, 'M': 0} for cle, _ in AGE_BRACKETS}


def _totaux(grille):
    return {
        'F': sum(grille[cle]['F'] for cle, _ in AGE_BRACKETS),
        'M': sum(grille[cle]['M'] for cle, _ in AGE_BRACKETS),
    }


def _cellules(grille):
    """Aplatit la grille {cle: {F,M}} en liste ordonnée (même ordre qu'AGE_BRACKETS),
    pour que le template puisse itérer sans avoir besoin d'un lookup dynamique."""
    return [grille[cle] for cle, _ in AGE_BRACKETS]


def _compter_les_consultants(premier_jour, dernier_jour):
    """Grille des consultants du mois, et identifiants des rendez-vous comptés.

    Le critère est le type de consultation du rendez-vous, pas son département :
    une consultation gynécologique reste une consultation gynécologique où
    qu'elle ait été enregistrée.

    Les identifiants sont renvoyés pour que le comptage des contrôles puisse les
    écarter : un rendez-vous déjà compté comme consultant ne doit pas s'ajouter
    une seconde fois aux consultations parce que son onglet Curatif porte aussi
    la mention « contrôle ».
    """
    from patients.models import RendezVous

    grille = _grille_vide()
    comptes = set()

    rdvs = (
        RendezVous.objects
        .filter(type_consultation__reference_interne__in=REFERENCES_CONSULTANT)
        .filter(date_heure__date__gte=premier_jour, date_heure__date__lte=dernier_jour)
        .select_related('patient')
    )
    for rdv in rdvs:
        patient = rdv.patient
        if patient is None or patient.sexe not in ('F', 'M'):
            continue
        bracket = _age_bracket(patient.date_naissance, rdv.date_heure.date())
        if not bracket:
            continue
        grille[bracket][patient.sexe] += 1
        comptes.add(rdv.pk)
    return grille, comptes


def calculer_rapport_gynecologie(annee, mois):
    from django.db.models import Q
    from patients.models import RegistreCuratif, Pathologie

    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, calendar.monthrange(annee, mois)[1])

    registres = (
        RegistreCuratif.objects
        .filter(Q(rdv__departement__code='GYN') | Q(rdv__medecin__specialite__nom__icontains='gyn'))
        .filter(rdv__date_heure__date__gte=premier_jour, rdv__date_heure__date__lte=dernier_jour)
        .select_related('rdv', 'rdv__patient')
    )

    activite_consultant, rdvs_consultants = _compter_les_consultants(premier_jour, dernier_jour)
    # Les consultations partent des consultants : la boucle ci-dessous n'y
    # ajoute que les contrôles, pour que consultations ≥ consultants toujours.
    activite_consultations = {cle: dict(cases) for cle, cases in activite_consultant.items()}
    activite_referes = _grille_vide()

    # Tri par pk = ordre de création : les pathologies hors fiche s'ajoutent
    # dans l'ordre où elles ont été créées.
    pathos_grossesse = list(Pathologie.objects.filter(departement__code='GYN', categorie='grossesse').order_by('pk'))
    pathos_infectieuse = list(Pathologie.objects.filter(departement__code='GYN', categorie='infectieuse').order_by('pk'))
    pathos_autre = list(Pathologie.objects.filter(departement__code='GYN', categorie='autre_gyneco').order_by('pk'))

    patho_grilles = {
        p.pk: {'grille': _grille_vide(), 'referes': {'F': 0, 'M': 0}}
        for p in pathos_grossesse + pathos_infectieuse + pathos_autre
    }

    for reg in registres:
        rdv = reg.rdv
        patient = rdv.patient
        sexe = patient.sexe
        if sexe not in ('F', 'M'):
            continue
        bracket = _age_bracket(patient.date_naissance, rdv.date_heure.date())
        if not bracket:
            continue

        d = reg.donnees
        type_visite = d.get('cur_type_visite', '')
        est_refere = d.get('cur_issue_consultation', '') == 'refere_externe'

        # Les consultants sont déjà comptés depuis les rendez-vous ; il ne reste
        # ici que les contrôles, et seulement ceux qui n'ont pas déjà été pris.
        if type_visite == 'controle' and rdv.pk not in rdvs_consultants:
            activite_consultations[bracket][sexe] += 1

        if est_refere:
            activite_referes[bracket][sexe] += 1

        raw_diag = d.get('cur_diagnostic', [])
        if isinstance(raw_diag, str):
            raw_diag = [raw_diag] if raw_diag else []
        pks = {int(v) for v in raw_diag if str(v).strip().isdigit()}
        for pk in pks:
            entry = patho_grilles.get(pk)
            if entry is None:
                continue
            entry['grille'][bracket][sexe] += 1
            if est_refere:
                entry['referes'][sexe] += 1

    def _ligne(label, pks, opts):
        """Ligne prête à rendre (même format que la médecine générale, voir
        templates/rapports/_rmg_lignes.html) : une cellule par (tranche, sexe),
        Total F/M puis Cas référés F/M, en sommant toutes les pathologies `pks`."""
        cellules = []
        totaux = {'F': 0, 'M': 0}
        for cle, _ in AGE_BRACKETS:
            for sexe in ('F', 'M'):
                val = sum(patho_grilles[pk]['grille'][cle][sexe] for pk in pks)
                totaux[sexe] += val
                cellules.append({'val': val})
        for sexe in ('F', 'M'):
            cellules.append({'val': totaux[sexe], 'total': True})
        for sexe in ('F', 'M'):
            cellules.append({'val': sum(patho_grilles[pk]['referes'][sexe] for pk in pks), 'refere': True})
        return {'label': label, 'cellules': cellules, 'hors_fiche': opts.get('hors_fiche', False)}

    grossesse = ranger_selon_fiche(FICHE_GROSSESSE, pathos_grossesse, _ligne)
    (infectieuse,) = ranger_selon_fiche(FICHE_INFECTIEUSE, pathos_infectieuse, _ligne)
    autre = ranger_selon_fiche(FICHE_AUTRE, pathos_autre, _ligne)

    return {
        'annee': annee,
        'mois': mois,
        'mois_nom': nom_du_mois(annee, mois),
        'age_brackets': [label for _, label in AGE_BRACKETS],
        'activites': {
            'consultant': {'cells': _cellules(activite_consultant), 'total': _totaux(activite_consultant)},
            'consultations': {'cells': _cellules(activite_consultations), 'total': _totaux(activite_consultations)},
            'referes': {'cells': _cellules(activite_referes), 'total': _totaux(activite_referes)},
        },
        'brackets': AGE_BRACKETS,
        'grossesse_page1': grossesse[0],
        'grossesse_page2': grossesse[1],
        # La fiche laisse une ligne vierge en fin de tableau A, tant
        # qu'aucune pathologie hors fiche n'y a été ajoutée.
        'grossesse_ligne_vierge': not any(l['hors_fiche'] for l in grossesse[1]),
        'infectieuse': infectieuse,
        'autre_page2': autre[0],
        'autre_page3': autre[1],
    }
