"""
Utilitaires pour le module congés — Code du travail ivoirien (Loi n° 2015-532).
"""
from datetime import date, timedelta


def easter(year: int) -> date:
    """
    Calcule la date de Pâques (algorithme Anonymous Gregorian / Meeus/Jones/Butcher).
    Aucune dépendance externe requise.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# ── Jours fériés islamiques (tables 2020-2035) ───────────────────────────────
_AID_FITR = {
    2020:(5,24),2021:(5,13),2022:(5,2),2023:(4,21),2024:(4,10),
    2025:(3,30),2026:(3,20),2027:(3,9),2028:(2,26),2029:(2,14),
    2030:(2,5),2031:(1,25),2032:(1,14),2033:(1,3),2034:(12,23),2035:(12,13),
}
_AID_KEBIR = {
    2020:(7,31),2021:(7,20),2022:(7,9),2023:(6,28),2024:(6,16),
    2025:(6,6),2026:(5,27),2027:(5,16),2028:(5,4),2029:(4,23),
    2030:(4,13),2031:(4,2),2032:(3,22),2033:(3,11),2034:(3,1),2035:(2,18),
}
_MAOULOUD = {
    2020:(10,29),2021:(10,19),2022:(10,8),2023:(9,27),2024:(9,15),
    2025:(9,4),2026:(8,25),2027:(8,14),2028:(8,2),2029:(7,22),
    2030:(7,12),2031:(7,1),2032:(6,19),2033:(6,9),2034:(5,30),2035:(5,19),
}


def _approx_islamic(table, year):
    """
    Approximate Islamic holiday date for years outside the hardcoded table
    by shifting 11 days earlier per year from the nearest known year.
    """
    if year in table:
        m, d = table[year]
        return date(year, m, d)
    # Find the nearest known year
    known_years = sorted(table.keys())
    ref_year = min(known_years, key=lambda y: abs(y - year))
    ref_m, ref_d = table[ref_year]
    ref_date = date(ref_year, ref_m, ref_d)
    delta_years = year - ref_year
    approx = ref_date + timedelta(days=delta_years * -11)
    # Adjust year in the approximated date
    try:
        return date(year, approx.month, approx.day)
    except ValueError:
        # Handle edge cases
        return date(year, approx.month, min(approx.day, 28))


def jours_feries_ivoire(year: int) -> set:
    """
    Retourne l'ensemble des jours fériés ivoiriens pour une année donnée.
    Basé sur le Code du travail ivoirien.
    """
    feries = set()

    # Jours fériés fixes
    feries.add(date(year, 1, 1))   # Jour de l'An
    feries.add(date(year, 5, 1))   # Fête du Travail
    feries.add(date(year, 8, 7))   # Fête Nationale
    feries.add(date(year, 8, 15))  # Assomption
    feries.add(date(year, 11, 1))  # Toussaint
    feries.add(date(year, 11, 15)) # Fête Nationale (Paix)
    feries.add(date(year, 12, 25)) # Noël

    # Jours fériés chrétiens mobiles
    paques = easter(year)
    feries.add(paques + timedelta(days=1))   # Lundi de Pâques
    feries.add(paques + timedelta(days=39))  # Ascension
    feries.add(paques + timedelta(days=50))  # Lundi de Pentecôte

    # Jours fériés islamiques
    feries.add(_approx_islamic(_AID_FITR, year))   # Aïd el-Fitr
    feries.add(_approx_islamic(_AID_KEBIR, year))  # Aïd el-Kébir
    feries.add(_approx_islamic(_MAOULOUD, year))   # Maouloud

    return feries


def jours_feries_labels(year: int) -> dict:
    """
    Retourne un dictionnaire {date: label} des jours fériés pour une année.
    """
    labels = {
        date(year, 1, 1):   "Jour de l'An",
        date(year, 5, 1):   "Fête du Travail",
        date(year, 8, 7):   "Fête Nationale",
        date(year, 8, 15):  "Assomption",
        date(year, 11, 1):  "Toussaint",
        date(year, 11, 15): "Fête Nationale (Paix)",
        date(year, 12, 25): "Noël",
    }
    paques = easter(year)
    labels[paques + timedelta(days=1)]  = "Lundi de Pâques"
    labels[paques + timedelta(days=39)] = "Ascension"
    labels[paques + timedelta(days=50)] = "Lundi de Pentecôte"
    labels[_approx_islamic(_AID_FITR, year)]  = "Aïd el-Fitr"
    labels[_approx_islamic(_AID_KEBIR, year)] = "Aïd el-Kébir"
    labels[_approx_islamic(_MAOULOUD, year)]  = "Maouloud"
    return labels


def compter_jours_ouvres(date_debut, date_fin) -> int:
    """
    Compte les jours ouvrés (lundi-vendredi hors jours fériés ivoiriens)
    entre date_debut et date_fin inclus.
    """
    if date_fin < date_debut:
        return 0

    # Collect all holiday years needed
    years = set(range(date_debut.year, date_fin.year + 1))
    feries = set()
    for y in years:
        feries |= jours_feries_ivoire(y)

    count = 0
    current = date_debut
    while current <= date_fin:
        if current.weekday() < 5 and current not in feries:
            count += 1
        current += timedelta(days=1)
    return count


def quota_annuel(employe, annee=None) -> float:
    """
    Calcule le quota annuel de congés selon le Code du travail ivoirien Art. 25.10.
    Base : 2,2 jours ouvrés par mois travaillé (min 26,4 jours/an).
    Bonus d'ancienneté à partir de 5 ans, évalué au 31/12 de `annee`
    (année en cours par défaut) — pour ne pas appliquer rétroactivement
    un bonus d'ancienneté acquis après l'année du solde recalculé.
    """
    ref_date = date(annee, 12, 31) if annee else date.today()
    anc = employe.anciennete_a(ref_date)
    annees = anc.get('annees', 0)
    mois = anc.get('mois', 0)
    total_mois = annees * 12 + mois

    if total_mois < 12:
        # Moins d'un an : proratisation
        base = 2.2 * max(total_mois, 0)
    else:
        base = 26.4  # minimum légal annuel

    # Bonus d'ancienneté
    bonus = 0
    if annees >= 25:
        bonus = 5
    elif annees >= 20:
        bonus = 4
    elif annees >= 15:
        bonus = 3
    elif annees >= 10:
        bonus = 2
    elif annees >= 5:
        bonus = 1

    return round(base + bonus, 1)


def detecter_conflits(employe, date_debut, date_fin, exclude_pk=None) -> list:
    """
    Retourne la liste des congés en chevauchement pour cet employé
    (statuts actifs : demande, approuve, en_cours).
    """
    from employer.models import Conge
    qs = Conge.objects.filter(
        employe=employe,
        statut__in=['demande', 'approuve', 'en_cours'],
        date_debut__lte=date_fin,
        date_fin__gte=date_debut,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs)


# ── Types de congé (configurables — voir conges.models.TypeConge) ───────────
def durees_exceptionnelles() -> dict:
    """{code: nb_jours} pour les types de congé à durée forfaitaire (mariage, décès...)."""
    from conges.models import TypeConge
    return dict(TypeConge.objects.exclude(duree_forfaitaire__isnull=True).values_list('code', 'duree_forfaitaire'))


def types_deductibles() -> set:
    """Codes des types de congé qui déduisent du solde annuel."""
    from conges.models import TypeConge
    return set(TypeConge.objects.filter(deductible=True).values_list('code', flat=True))


def jours_pris_annee(employe, annee) -> float:
    """
    Jours ouvrés déductibles pris par l'employé pour `annee`.
    Un congé à cheval sur deux années civiles (ex: 22/12 → 06/01) n'est compté
    que pour sa portion réellement dans `annee`, pas pour la totalité de sa durée.
    """
    from employer.models import Conge
    jan1  = date(annee, 1, 1)
    dec31 = date(annee, 12, 31)
    conges = Conge.objects.filter(
        employe=employe,
        statut__in=['approuve', 'en_cours', 'termine'],
        deduit_du_solde=True,
        date_debut__lte=dec31,
        date_fin__gte=jan1,
    ).values_list('date_debut', 'date_fin', 'nb_jours_ouvres')

    total = 0
    for d_debut, d_fin, nb in conges:
        if d_debut >= jan1 and d_fin <= dec31:
            total += nb
        else:
            total += compter_jours_ouvres(max(d_debut, jan1), min(d_fin, dec31))
    return total


def get_or_create_solde(employe, annee) -> 'SoldeConge':
    """
    Récupère ou crée le SoldeConge pour un employé et une année.
    Recalcule quota et jours_pris à chaque appel.
    """
    from employer.models import SoldeConge

    quota = quota_annuel(employe, annee)
    solde, created = SoldeConge.objects.get_or_create(
        employe=employe,
        annee=annee,
        defaults={'quota': quota},
    )
    solde.quota = quota
    solde.jours_pris = jours_pris_annee(employe, annee)
    solde.save()
    return solde
