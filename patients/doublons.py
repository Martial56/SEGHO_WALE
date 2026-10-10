"""Détection des doublons patients.

Inspiré de duplicate-finder (similarité de chaînes), mais adapté à des fiches
courtes et structurées : on ne compare pas un bloc de texte, on compare champ
par champ et on pondère. Un même nom compte beaucoup, une même date de
naissance aussi ; un même téléphone un peu moins, parce qu'une famille entière
partage souvent un seul numéro.

Score sur 100 :
    nom + prénoms ........ 50  (tolérant aux fautes, accents, ordre inversé,
                                variantes Kouassi/Kwassi, N'Guessan/Guessan)
    date de naissance .... 30  (tolérant jour/mois inversés, faute de frappe,
                                date approximative au 1er janvier)
    téléphone ............ 15  (principal ou secondaire, n'importe quel format)
    sexe ................. +5 s'il concorde, -15 s'il diffère

Décision :
    score >= SEUIL_BLOCAGE ........ doublon quasi certain : création refusée
    score >= SEUIL_AVERTISSEMENT .. doublon possible : confirmation exigée
    en dessous .................... rien

Une date « approximative » (âge converti en date, ou 1er janvier) ne vaut que
l'année : elle ne peut pas prouver à elle seule que c'est la même personne.
Un mot du nom ou des prénoms qui ne ressemble à rien dans l'autre fiche
(« ALINE » contre « EUGENIE ») fait chuter la ressemblance : deux personnes
d'une même famille ne sont plus prises pour la même.

Les seuils se règlent dans settings.py (DOUBLONS_PATIENTS_SEUIL_BLOCAGE,
DOUBLONS_PATIENTS_SEUIL_AVERTISSEMENT) sans toucher au code.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.db.models import Q

POIDS_NOM = 50
POIDS_DATE = 30
POIDS_TELEPHONE = 15
BONUS_SEXE = 5
MALUS_SEXE = -15

SEUIL_BLOCAGE = getattr(settings, 'DOUBLONS_PATIENTS_SEUIL_BLOCAGE', 85)
SEUIL_AVERTISSEMENT = getattr(settings, 'DOUBLONS_PATIENTS_SEUIL_AVERTISSEMENT', 65)
TOUS_CENTRES = getattr(settings, 'DOUBLONS_PATIENTS_TOUS_CENTRES', False)
MAX_CANDIDATS = 5
# Jours/mois « par défaut » : une date qui tombe dessus ne vaut que par son
# année (1er janvier quand on ne connaît que l'année, 30/09 quand l'âge a été
# converti en date…). À compléter dans settings.py si votre base en contient
# d'autres : DOUBLONS_PATIENTS_DATES_PAR_DEFAUT = [(1, 1), (30, 9)]
DATES_PAR_DEFAUT = {tuple(x) for x in getattr(settings, 'DOUBLONS_PATIENTS_DATES_PAR_DEFAUT', [(1, 1)])}


# ── Normalisation ────────────────────────────────────────────────────────────

def normaliser_texte(s):
    """« N'Guéssan-Kôné » → « NGUESSAN KONE » : majuscules, sans accents, la
    ponctuation (apostrophe, trait d'union, point) devient séparateur ou
    disparaît."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"['’`.]", '', s)          # N'GUESSAN → NGUESSAN
    s = re.sub(r'[^A-Z]+', ' ', s)         # tirets, chiffres, etc. → espace
    return ' '.join(s.split())


def mots(s):
    return normaliser_texte(s).split()


def cle_phonetique(mot):
    """Rapproche les graphies qui se prononcent pareil, pour les noms
    ivoiriens et français : Kouassi/Kwassi, Yao/Yaho, Konan/Konnan,
    N'Dri/Dri, Philippe/Filipe, Christelle/Cristel."""
    m = normaliser_texte(mot).replace(' ', '')
    if not m:
        return ''
    m = re.sub(r'^N(?=[^AEIOUY])', '', m)  # N'DRI, N'GORAN → DRI, GORAN
    m = m.replace('PH', 'F').replace('Y', 'I')
    m = re.sub(r'OU(?=[AEIO])', 'W', m)    # KOUASSI → KWASSI
    m = m.replace('OU', 'U')
    m = re.sub(r'C(?=[EI])', 'S', m)
    m = re.sub(r'[CQ]', 'K', m)
    m = re.sub(r'GU(?=[EI])', 'G', m)
    m = re.sub(r'(?<!C)(?<!S)H', '', m)    # YAHO → YAO, mais garde CH/SH
    m = re.sub(r'(.)\1+', r'\1', m)        # lettres doublées
    if len(m) > 3:
        m = re.sub(r'E$', '', m)           # CHRISTELLE ~ CHRISTEL
    return m


def normaliser_telephone(tel):
    """Les 10 chiffres nationaux : « +225 07 49 ... » = « 0749... »."""
    chiffres = re.sub(r'\D', '', str(tel or ''))
    if chiffres.startswith('00'):
        chiffres = chiffres[2:]
    if chiffres.startswith('225') and len(chiffres) == 13:
        chiffres = chiffres[3:]
    return chiffres if len(chiffres) >= 8 else ''


# ── Similarités élémentaires ────────────────────────────────────────────────

def jaro_winkler(a, b):
    """Similarité de Jaro-Winkler (0..1), adaptée aux chaînes courtes comme les
    noms : une faute de frappe pèse peu, un début identique compte davantage."""
    if a == b:
        return 1.0 if a else 0.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    portee = max(max(la, lb) // 2 - 1, 0)
    pris_a, pris_b = [False] * la, [False] * lb
    communs = 0
    for i, ca in enumerate(a):
        for j in range(max(0, i - portee), min(lb, i + portee + 1)):
            if not pris_b[j] and b[j] == ca:
                pris_a[i] = pris_b[j] = True
                communs += 1
                break
    if not communs:
        return 0.0
    transpositions, k = 0, 0
    for i in range(la):
        if pris_a[i]:
            while not pris_b[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    jaro = (communs / la + communs / lb + (communs - transpositions / 2) / communs) / 3
    prefixe = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca != cb:
            break
        prefixe += 1
    return jaro + prefixe * 0.1 * (1 - jaro)


def similarite_mot(a, b):
    """Le meilleur de la comparaison écrite et de la comparaison phonétique."""
    return max(jaro_winkler(a, b), jaro_winkler(cle_phonetique(a), cle_phonetique(b)))


SEUIL_MOT_PROCHE = 0.85   # en dessous, le mot est considéré comme « sans équivalent »


def _poids_mot(score):
    """Un mot qui ressemble peu à son meilleur partenaire est une vraie
    différence (ALINE / EUGENIE), pas une faute de frappe : on l'écrase
    plutôt que de le laisser faire une moyenne flatteuse avec le nom commun."""
    return score if score >= SEUIL_MOT_PROCHE else score ** 3


def similarite_ensembles(mots_a, mots_b):
    """Chaque mot du plus petit ensemble cherche son meilleur partenaire dans
    l'autre, sans réutilisation. Indifférent à l'ordre : « Ama Christelle »
    contre « Christelle Ama »."""
    if not mots_a or not mots_b:
        return 0.0
    petit, grand = (mots_a, mots_b) if len(mots_a) <= len(mots_b) else (mots_b, mots_a)
    restants = list(grand)
    total = 0.0
    for m in petit:
        scores = [similarite_mot(m, r) for r in restants]
        i = max(range(len(scores)), key=scores.__getitem__)
        total += _poids_mot(scores[i])
        restants.pop(i)
    moyenne = total / len(petit)
    # Un prénom en moins (« Ama » contre « Ama Christelle ») reste très
    # probablement la même personne, mais pas tout à fait aussi sûrement.
    return moyenne * (1.0 if len(mots_a) == len(mots_b) else 0.93)


def similarite_noms(nom_a, prenoms_a, nom_b, prenoms_b):
    na, pa, nb, pb = mots(nom_a), mots(prenoms_a), mots(nom_b), mots(prenoms_b)
    # 1. Champ par champ : le nom contre le nom, les prénoms contre les prénoms.
    structure = 0.5 * similarite_ensembles(na, nb) + 0.5 * similarite_ensembles(pa, pb)
    # 2. Tout mélangé : rattrape le nom saisi dans la case prénoms et inversement.
    melange = similarite_ensembles(na + pa, nb + pb) * 0.97
    return max(structure, melange)


def similarite_dates(a, b):
    if not a or not b:
        return 0.0
    # Date « par défaut » (1er janvier, 30/09…) : seule l'année est connue.
    if (a.day, a.month) in DATES_PAR_DEFAUT or (b.day, b.month) in DATES_PAR_DEFAUT:
        return similarite_dates_approx(a, b)
    if a == b:
        return 1.0
    # Jour et mois inversés (12/04 saisi 04/12).
    if a.year == b.year and a.month == b.day and a.day == b.month:
        return 0.85
    # Date « par défaut » quand on ne connaît que l'année.
    if a.year == b.year and ((a.month, a.day) == (1, 1) or (b.month, b.day) == (1, 1)):
        return 0.7
    # Un seul élément différent (faute de frappe sur le jour, le mois ou l'année).
    egaux = (a.year == b.year) + (a.month == b.month) + (a.day == b.day)
    if egaux == 2:
        return 0.75 if a.year == b.year else 0.6
    if abs((a - b).days) <= 31:
        return 0.5
    if abs(a.year - b.year) <= 1:
        return 0.15
    return 0.0


def similarite_dates_approx(a, b):
    """Quand l'une des dates n'est qu'une estimation (âge converti en date,
    1er janvier…), on connaît seulement l'année, à un an près : on ne peut ni
    conclure « même date » ni « date différente »."""
    if not a or not b:
        return 0.0
    ecart = abs((a - b).days)
    if ecart <= 200:
        return 0.6
    if ecart <= 400:
        return 0.35
    return 0.0


def score_depuis_similarites(s_noms, s_date, meme_tel, sexe_a, sexe_b):
    """Le calcul du score, à UN seul endroit : l'application et le script de
    test Excel l'appellent tous les deux. Renvoie (score entier, sexe différent ?)."""
    score = POIDS_NOM * s_noms + POIDS_DATE * s_date + (POIDS_TELEPHONE if meme_tel else 0)
    sexe_diff = bool(sexe_a and sexe_b and sexe_a != sexe_b)
    if sexe_a and sexe_b:
        score += MALUS_SEXE if sexe_diff else BONUS_SEXE
    # Garde-fou : sans un nom au moins ressemblant, ce n'est pas un doublon,
    # quels que soient la date et le téléphone (mère et enfant, par exemple).
    if s_noms < 0.75:
        score = min(score, SEUIL_AVERTISSEMENT - 1)
    return max(0, round(score)), sexe_diff


# ── Score global ─────────────────────────────────────────────────────────────

@dataclass
class Correspondance:
    patient: object
    score: int
    details: dict = field(default_factory=dict)

    @property
    def niveau(self):
        if self.score >= SEUIL_BLOCAGE:
            return 'blocage'
        if self.score >= SEUIL_AVERTISSEMENT:
            return 'avertissement'
        return 'aucun'

    @property
    def raisons(self):
        r = []
        d = self.details
        if d.get('noms', 0) >= 0.97:
            r.append('même nom')
        elif d.get('noms', 0) >= 0.85:
            r.append('nom très proche')
        if d.get('date', 0) == 1.0:
            r.append('même date de naissance')
        elif d.get('date', 0) >= 0.6:
            r.append('date de naissance proche')
        if d.get('telephone'):
            r.append('même téléphone')
        return r


def _telephones(obj):
    if isinstance(obj, dict):
        tels = [obj.get('telephone'), obj.get('telephone2')]
    else:
        tels = [getattr(obj, 'telephone', ''), getattr(obj, 'telephone2', '')]
    return {t for t in (normaliser_telephone(x) for x in tels) if t}


def _champ(obj, nom):
    return obj.get(nom) if isinstance(obj, dict) else getattr(obj, nom, None)


def scorer(saisie, existant):
    """Compare une saisie (dict ou Patient) à un patient existant.
    Si l'un des deux objets porte `date_precise = False`, sa date est traitée
    comme une simple estimation (année seulement)."""
    s_noms = similarite_noms(_champ(saisie, 'nom'), _champ(saisie, 'prenoms'),
                             existant.nom, existant.prenoms)
    d_a, d_b = _champ(saisie, 'date_naissance'), existant.date_naissance
    approx = _champ(saisie, 'date_precise') is False or getattr(existant, 'date_precise', True) is False
    s_date = similarite_dates_approx(d_a, d_b) if approx else similarite_dates(d_a, d_b)
    meme_tel = bool(_telephones(saisie) & _telephones(existant))
    score, _ = score_depuis_similarites(s_noms, s_date, meme_tel, _champ(saisie, 'sexe'), existant.sexe)
    return Correspondance(existant, score,
                          {'noms': round(s_noms, 3), 'date': s_date, 'telephone': meme_tel})


# ── Recherche des candidats ─────────────────────────────────────────────────

def _base_queryset():
    from .models import Patient
    return Patient.all_objects if TOUS_CENTRES else Patient.objects


def _preselection(saisie):
    """Filtre SQL large (« blocage » au sens du record linkage) : on ne score en
    Python que les fiches qui ont au moins une chance d'être la même personne."""
    q = Q()
    d = _champ(saisie, 'date_naissance')
    if d:
        q |= Q(date_naissance__year__gte=d.year - 1, date_naissance__year__lte=d.year + 1)
    for tel in _telephones(saisie):
        fin = tel[-8:]
        q |= Q(telephone__endswith=fin) | Q(telephone2__endswith=fin)
    for m in mots(_champ(saisie, 'nom')) + mots(_champ(saisie, 'prenoms')):
        if len(m) >= 3:
            q |= Q(nom__icontains=m[:3]) | Q(prenoms__icontains=m[:3])
    return q


def chercher_doublons(saisie, exclure_pk=None, seuil=None, limite=MAX_CANDIDATS, queryset=None):
    """Les patients existants qui ressemblent à `saisie`, du plus probable au
    moins probable. `saisie` : dict (nom, prenoms, date_naissance, sexe,
    telephone, telephone2) ou instance de Patient. `queryset` remplace le
    périmètre par défaut (centre actif, ou tous si DOUBLONS_PATIENTS_TOUS_CENTRES)."""
    seuil = SEUIL_AVERTISSEMENT if seuil is None else seuil
    if not (_champ(saisie, 'nom') or _champ(saisie, 'prenoms')):
        return []
    q = _preselection(saisie)
    if not q:
        return []
    qs = (queryset if queryset is not None else _base_queryset()).filter(q)
    if exclure_pk:
        qs = qs.exclude(pk=exclure_pk)
    resultats = [scorer(saisie, p) for p in qs.only(
        'pk', 'code_patient', 'nom', 'prenoms', 'date_naissance', 'sexe',
        'telephone', 'telephone2', 'centre_id')]
    resultats = [r for r in resultats if r.score >= seuil]
    resultats.sort(key=lambda r: r.score, reverse=True)
    return resultats[:limite]
