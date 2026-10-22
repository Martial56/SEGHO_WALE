"""
Indicateurs du tableau de bord « Vue d'ensemble » (core.views.kpi_dashboard),
calqués sur la feuille Excel « Tableau de bord » des DONNÉES WALÉ.

Deux lectures des mêmes activités :
- `calculer_kpi_annuels(annee)` : détail par trimestre de l'année (T1 à T4
  des cartes) et par mois (graphiques) ;
- `calculer_totaux_periode(debut, fin)` : total de chaque carte sur la période
  choisie dans le bandeau (jour, semaine, mois ou année).

Sources :
- Consultation générale : RDV du département Médecine générale ('medg'/'MEDGEN').
- Consultation prénatale : RDV portant un rang CPN (`cpn_type_visite`), comme
  le rapport maternité (voir rapports/maternite.py).
- Consultation gynécologie : RDV du département 'GYN' hors CPN.
- Cardiologie : RDV d'un département reconnu par son code ou son nom (voir
  `_Q_CARDIO`). Aucun n'existe encore en base : l'indicateur reste à 0 jusqu'à
  la création du département.
- Une consultation compte dès qu'elle a démarré (« En consultation » ou
  « Terminé ») : un RDV planifié, annulé ou absent n'est pas une consultation.
- Examens laboratoire : lignes de demandes d'examen (hors brouillons). Une
  ligne est interne (« WALÉ ») si un médecin du centre l'a prescrite, externe
  sinon (patient venu directement au laboratoire).
- Soins infirmiers : fiches de soins hors brouillons et annulées.
- Mise en observation : hospitalisations admises (même base que le listing
  MO, voir rapports/registry.py), hors annulées.

Adulte / enfant : moins de 15 ans à la date de la visite = enfant.
"""
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from patients.utils import CODES_MEDECINE_GENERALE

AGE_ENFANT_MAX = 15
MOIS_NOMS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
             'août', 'septembre', 'octobre', 'novembre', 'décembre']
MOIS_LABELS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
               'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']

STATUTS_CONSULTATION = ('en_consultation', 'termine')

_Q_CARDIO = (Q(departement__code__icontains='card')
             | Q(departement__nom__icontains='cardio'))


def _mois(dt):
    return timezone.localtime(dt).month if timezone.is_aware(dt) else dt.month


def _est_enfant(date_naissance, date_visite):
    if not date_naissance:
        return False
    age = date_visite.year - date_naissance.year - (
        (date_visite.month, date_visite.day) < (date_naissance.month, date_naissance.day))
    return age < AGE_ENFANT_MAX


def _serie(mois):
    return {'mois': mois, 'trimestres': [sum(mois[i:i + 3]) for i in (0, 3, 6, 9)]}


def _pourcentages(a, b):
    total = a + b
    if not total:
        return 0, 0
    pa = round(a * 100 / total)
    return pa, 100 - pa


def _activites(**filtre_date):
    """Querysets de chaque activité, filtrés sur leur propre champ date.
    `filtre_date` porte sur un champ appelé `date` (ex. date__year=2026),
    renommé ici selon le modèle."""
    from hospitalisation.models import Hospitalisation
    from laboratoire.models import LigneDemandeExamen
    from patients.models import RendezVous
    from soins.models import Soin

    def sur(champ):
        return {k.replace('date', champ, 1): v for k, v in filtre_date.items()}

    rdv = RendezVous.objects.filter(statut__in=STATUTS_CONSULTATION, **sur('date_heure'))
    return {
        'mg': rdv.filter(departement__code__in=CODES_MEDECINE_GENERALE),
        'cpn': rdv.filter(cpn_type_visite__isnull=False),
        'gyn': rdv.filter(departement__code='GYN', cpn_type_visite__isnull=True),
        'cardio': rdv.filter(_Q_CARDIO),
        'labo': (LigneDemandeExamen.objects.filter(**sur('demande__date_creation'))
                 .exclude(demande__statut='brouillon')),
        'soins': (Soin.objects.filter(**sur('date_heure'))
                  .exclude(statut__in=['brouillon', 'annule'])),
        'mo': (Hospitalisation.objects.filter(**sur('date_admission'))
               .exclude(statut='annule')),
    }


def _provenance_labo(labo):
    externe = labo.filter(demande__medecin_prescripteur__isnull=True).count()
    wale = labo.count() - externe
    part_wale, part_externe = _pourcentages(wale, externe)
    return {'wale': wale, 'externe': externe, 'part_wale': part_wale, 'part_externe': part_externe}


def calculer_totaux_periode(debut, fin):
    """Total de chaque carte entre `debut` et `fin` (dates incluses)."""
    act = _activites(date__date__range=[debut, fin])
    totaux = {cle: act[cle].count() for cle in ('mg', 'cpn', 'gyn', 'cardio', 'labo', 'soins', 'mo')}
    totaux['provenance'] = _provenance_labo(act['labo'])
    return totaux


def _compter_par_mois(qs, champ_date):
    mois = [0] * 12
    for dt in qs.values_list(champ_date, flat=True):
        if dt:
            mois[_mois(dt) - 1] += 1
    return mois


def _consultations_par_age(qs):
    """Séries mensuelles adultes / enfants / total et répartition par sexe."""
    adultes, enfants = [0] * 12, [0] * 12
    sexe = {'M': 0, 'F': 0}
    for dt, naissance, s in qs.values_list('date_heure', 'patient__date_naissance', 'patient__sexe'):
        local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
        serie = enfants if _est_enfant(naissance, local.date()) else adultes
        serie[local.month - 1] += 1
        if s in sexe:
            sexe[s] += 1
    total = [a + e for a, e in zip(adultes, enfants)]
    return dict(_serie(total), adultes=adultes, enfants=enfants, sexe=sexe)


def _laboratoire_par_mois(labo):
    internes, externes = [0] * 12, [0] * 12
    for dt, prescripteur_id in labo.values_list('demande__date_creation', 'demande__medecin_prescripteur_id'):
        (internes if prescripteur_id else externes)[_mois(dt) - 1] += 1
    total = [i + e for i, e in zip(internes, externes)]
    return dict(_serie(total), internes=internes, externes=externes)


def calculer_kpi_annuels(annee):
    """Détail trimestriel et mensuel de l'année `annee`."""
    act = _activites(date__year=annee)
    return {
        'mg': _consultations_par_age(act['mg']),
        'cpn': _serie(_compter_par_mois(act['cpn'], 'date_heure')),
        'gyn': _serie(_compter_par_mois(act['gyn'], 'date_heure')),
        'cardio': _serie(_compter_par_mois(act['cardio'], 'date_heure')),
        'labo': _laboratoire_par_mois(act['labo']),
        'soins': _serie(_compter_par_mois(act['soins'], 'date_heure')),
        'mo': _serie(_compter_par_mois(act['mo'], 'date_admission')),
    }


def annees_disponibles(annee_courante):
    """Années proposées dans le sélecteur : de la première consultation à
    l'année en cours."""
    from patients.models import RendezVous
    premiere = RendezVous.objects.order_by('date_heure').values_list('date_heure', flat=True).first()
    debut = min(timezone.localtime(premiere).year if premiere else annee_courante, annee_courante)
    return list(range(annee_courante, debut - 1, -1))


def _entier(valeur, defaut):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def _semaines(annee, today):
    """Semaines ISO de l'année, jusqu'à la semaine en cours pour l'année en
    cours : [(numéro, lundi, dimanche)]."""
    nb = date(annee, 12, 28).isocalendar()[1]
    semaines = []
    for n in range(1, nb + 1):
        lundi = date.fromisocalendar(annee, n, 1)
        if lundi > today:
            break
        semaines.append((n, lundi, lundi + timedelta(days=6)))
    return semaines


def calendrier(annees, today):
    """Les choix des listes déroulantes pour chaque année, d'un seul tenant.

    L'écran les redessine lui-même quand on change d'année ou de mois, sans
    rien demander au serveur : il faut donc qu'il ait tout sous la main dès
    le départ. C'est quelques dizaines de lignes par année, rien de plus.

    Chaque semaine porte les mois de l'année qu'elle touche — une semaine à
    cheval en a deux, et l'écran la propose dans les deux. Les mois sont
    calculés ici plutôt que redevinés en JavaScript, pour qu'un seul endroit
    décide de ce qu'« une semaine de mars » veut dire.
    """
    tout = {}
    for annee in annees:
        semaines = []
        for n, lundi, dimanche in _semaines(annee, today):
            mois = sorted({j.month for j in (lundi, dimanche) if j.year == annee})
            semaines.append({
                'n': n,
                'libelle': f"S{n} — {lundi.strftime('%d/%m')} au {dimanche.strftime('%d/%m')}",
                'mois': mois,
            })
        dernier_mois = today.month if annee == today.year else 12
        tout[str(annee)] = {
            'semaines': list(reversed(semaines)),
            'mois': [{'n': m, 'libelle': MOIS_NOMS[m - 1].capitalize()}
                     for m in range(1, dernier_mois + 1)],
        }
    return tout


def resoudre_periode(params, today, annees):
    """Lit les filtres du bandeau (`period`, `annee`, `mois`, `semaine`) et
    renvoie la période retenue, ses bornes, son libellé et les choix des
    listes déroulantes. L'année choisie porte aussi les trimestres et les
    graphiques ; la semaine et le mois se choisissent dans cette année."""
    period = params.get('period', 'annee')
    if period not in ('jour', 'semaine', 'mois', 'annee'):
        period = 'annee'
    annee = _entier(params.get('annee'), today.year)
    if period == 'jour' or annee not in annees:
        annee = today.year

    semaines = _semaines(annee, today)
    dernier_mois = today.month if annee == today.year else 12
    mois_choix = [(m, MOIS_NOMS[m - 1].capitalize()) for m in range(1, dernier_mois + 1)]
    defaut_mois = dernier_mois

    # Le mois joue deux rôles : c'est une période à part entière, et c'est le
    # cadre dans lequel on choisit une semaine. Il est donc lu même quand la
    # période retenue est la semaine — sans quoi la liste des semaines se
    # réélargirait à l'année dès qu'on en choisit une.
    cadre = _entier(params.get('mois'), 0)
    if not 1 <= cadre <= dernier_mois:
        cadre = defaut_mois if period == 'mois' else 0
    if cadre:
        premier = date(annee, cadre, 1)
        dernier = date(annee + (cadre == 12), cadre % 12 + 1, 1) - timedelta(days=1)
        # Une semaine à cheval compte dans les deux mois qu'elle touche : on
        # cherche « la semaine du 28 septembre », pas « la semaine dont le
        # lundi tombe en octobre ».
        semaines = [(n, l, d) for n, l, d in semaines if l <= dernier and d >= premier]

    semaine = mois = None
    if period == 'jour':
        debut = fin = today
        label = f"Aujourd'hui — {today.strftime('%d/%m/%Y')}"
    elif period == 'semaine':
        par_numero = {n: (lundi, dimanche) for n, lundi, dimanche in semaines}
        # La semaine en cours si elle est proposée, la dernière de la liste
        # sinon : une année passée n'a pas de semaine en cours, et un mois
        # choisi ne contient pas forcément celle d'aujourd'hui.
        defaut = today.isocalendar()[1]
        if defaut not in par_numero and semaines:
            defaut = semaines[-1][0]
        semaine = _entier(params.get('semaine'), defaut)
        if semaine not in par_numero:
            semaine = defaut
        # Début janvier, la semaine en cours peut encore être la dernière de
        # l'année précédente (semaine ISO 52 ou 53) : elle n'est pas listée.
        debut, fin = par_numero.get(semaine) or (today - timedelta(days=today.weekday()),
                                                 today + timedelta(days=6 - today.weekday()))
        label = f"Semaine {semaine} — du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}"
    elif period == 'mois':
        mois = cadre
        debut = date(annee, mois, 1)
        fin = (date(annee + (mois == 12), mois % 12 + 1, 1)) - timedelta(days=1)
        label = f"{MOIS_NOMS[mois - 1].capitalize()} {annee}"
    else:
        debut, fin = date(annee, 1, 1), date(annee, 12, 31)
        label = f"Année {annee}"

    return {
        'period': period, 'annee': annee, 'semaine': semaine, 'mois': mois,
        # Le mois retenu dans la liste déroulante, qu'il soit la période
        # affichée ou seulement le cadre d'une semaine. `mois` ne dit que le
        # premier cas ; c'est `cadre_mois` qui coche l'option.
        'cadre_mois': cadre or None,
        'debut': debut, 'fin': fin, 'label': label,
        'semaines_choix': [(n, f"S{n} — {l.strftime('%d/%m')} au {d.strftime('%d/%m')}")
                           for n, l, d in reversed(semaines)],
        'mois_choix': mois_choix,
    }
