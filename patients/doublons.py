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
from functools import lru_cache
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

@lru_cache(maxsize=20000)
def _normaliser_texte_cache(s):
    return _normaliser_texte(s)


def normaliser_texte(s):
    """Mémorisée : la recherche compare une saisie à des centaines de fiches,
    et les mêmes mots — KOUASSI, AYA, KOFFI — reviennent à chaque comparaison.
    Sans cela, 300 000 appels à `re.sub` pour une seule recherche.
    """
    return _normaliser_texte_cache(s) if isinstance(s, str) else _normaliser_texte(s)


def _normaliser_texte(s):
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


@lru_cache(maxsize=20000)
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


@lru_cache(maxsize=100000)
def similarite_mot(a, b):
    """Le meilleur de la comparaison écrite et de la comparaison phonétique.

    Mémorisée comme `cle_phonetique` : comparer une saisie à huit cents fiches
    rejoue sans cesse les mêmes couples de mots, « KOUASSI » contre
    « KOUASSI » revenant à lui seul des centaines de fois.
    """
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


def _prenoms_orphelins(prenoms_a, prenoms_b):
    """Chaque côté porte-t-il un prénom que l'autre n'a pas ?

    Deux frères nés le même jour, déclarés sous le même téléphone, partagent le
    nom, le patronyme du père et souvent un premier prénom : N'GORAN KOUASSI
    N'DA JEAN **NATHANAEL** et N'GORAN KOUAME N'DA JEAN **EMMANUEL** montent à
    93 % et seraient refusés à la création. Or ce sont deux personnes. Le
    logiciel ne cherche pas à savoir pourquoi : il constate l'écart, abaisse le
    score sous le seuil de blocage et laisse l'utilisateur décider.

    Ce qui les distingue n'est pas la moyenne des ressemblances, c'est la
    réciprocité du désaccord : chacun a un prénom que l'autre n'a pas. Une
    faute de frappe, elle, ne crée l'orphelin que d'un seul côté — l'autre
    retrouve toujours son partenaire.
    """
    a, b = mots(prenoms_a), mots(prenoms_b)
    if not a or not b:
        return False, False

    def orphelins(gauche, droite):
        return any(max(similarite_mot(m, d) for d in droite) < SEUIL_MOT_PROCHE
                   for m in gauche)

    return orphelins(a, b), orphelins(b, a)


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
        return raisons(self.details)


#: En dessous, la ressemblance des noms ne vaut pas d'être annoncée : si la
#: paire est là, c'est la date ou le téléphone qui l'a amenée.
SEUIL_NOM_ANNONCE = 0.85


def memes_noms(a, b):
    """Les deux fiches s'écrivent-elles exactement pareil ?

    Accents, apostrophes et espaces mis à part — « N'Guéssan Kôné » et
    « NGUESSAN KONE » sont la même écriture. Le seuil ne répond pas à cette
    question : BALO et BALLO passent au-dessus de 0,97 sans être le même mot,
    et annoncer « même nom » là-dessus serait affirmer ce qu'on n'a pas mesuré.
    """
    def ecrit(x):
        return normaliser_texte(f"{_champ(x, 'nom') or ''} "
                                f"{_champ(x, 'prenoms') or ''}")
    return ecrit(a) == ecrit(b)


def raisons(details):
    """Pourquoi ces deux fiches se ressemblent, en clair.

    Une fonction et non plus une seule propriété : l'écran des doublons relit
    des `details` rangés en base, sans la `Correspondance` qui les a produits.
    """
    r = []
    d = details or {}
    if d.get('noms', 0) >= SEUIL_NOM_ANNONCE:
        r.append('même nom' if d.get('noms_identiques')
                 else 'nom presque identique')
    if d.get('date', 0) == 1.0:
        r.append('même date de naissance')
    elif d.get('date', 0) >= 0.6:
        r.append('date de naissance proche')
    if d.get('telephone'):
        r.append('même téléphone')
    if d.get('prenoms_differents'):
        r.append('prénoms différents')
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
    # Prénoms différents de part et d'autre : on demande une confirmation, on
    # ne refuse pas. Le plafond est posé juste sous le seuil de blocage, pour
    # que la paire reste signalée. Le logiciel ne dit pas de qui il s'agit —
    # c'est à celui qui saisit de trancher.
    gauche, droite = _prenoms_orphelins(_champ(saisie, 'prenoms'), existant.prenoms)
    prenoms_differents = gauche and droite
    if prenoms_differents:
        score = min(score, SEUIL_BLOCAGE - 1)
    return Correspondance(existant, score,
                          {'noms': round(s_noms, 3), 'date': s_date,
                           'noms_identiques': memes_noms(saisie, existant),
                           'telephone': meme_tel,
                           'prenoms_differents': prenoms_differents})


# ── Recherche des candidats ─────────────────────────────────────────────────

def _base_queryset():
    from .models import Patient
    return Patient.all_objects if TOUS_CENTRES else Patient.objects


def _mot_present(mot):
    """Le mot figure dans le nom ou dans les prénoms, où qu'il soit."""
    return Q(nom__icontains=mot) | Q(prenoms__icontains=mot)


def _debut_present(mot):
    return Q(nom__icontains=mot[:3]) | Q(prenoms__icontains=mot[:3])


def _cles_phonetiques(fiche):
    """Les clés phonétiques d'une fiche, triées.

    Déportées dans `patients.cles_phonetiques`, qui les écrit aussi en base :
    une clé calculée ici et une clé stockée là-bas doivent être la même, sinon
    la présélection ne retrouve rien.
    """
    from .cles_phonetiques import cles
    return sorted(cles(_champ(fiche, 'nom'), _champ(fiche, 'prenoms')))


def _pks_phonetiques(saisie, queryset):
    """Les fiches que la ressemblance sonore désigne, en une requête.

    Deux familles, et jamais une clé seule : « KWASI » à lui tout seul porte
    3 092 des 47 813 fiches, la présélection y perdrait tout ce qu'elle a
    gagné. Mesuré sur 300 saisies réelles, ces deux familles ajoutent 2
    candidats à la médiane et 112 au pire.

    1. **Deux clés en commun.** Presque gratuit : quand deux mots concordent à
       la fois phonétiquement et à la lettre, la famille des mots exacts les
       trouvait déjà. Le gain est pour les variantes d'écriture des deux mots.
    2. **Une clé + l'année à un an près.** La plus coûteuse, et la seule qui
       rattrape N'GESSAN N'DRISCA PRISCA / N'GUESSAN PRSICA : elles ne
       partagent que `GESAN`, plus l'année.

    Le tri se fait en Python plutôt qu'en SQL : exprimer « au moins deux clés
    parmi celles-ci » demanderait une sous-requête par clé, là où une seule
    lecture indexée suffit. Elle ramène au plus quelques milliers de lignes
    (clé, année), et rend quelques centaines de fiches.
    """
    from .models import ClePhonetique

    cles = _cles_phonetiques(saisie)
    if not cles:
        return set()

    # Lecture sur la seule clé, sans filtre de périmètre : la requête qui
    # englobe celle-ci applique déjà le centre, les fusionnées et les masquées,
    # et les identifiants rendus ici ne font que s'y intersecter. Croiser le
    # périmètre ici (`patient__in=queryset`) coûtait 95 ms au lieu de 3 : la
    # sous-requête sur 47 800 fiches écartait l'index.
    lignes = (ClePhonetique.all_objects
              .filter(cle__in=cles)
              .values_list('patient_id', 'cle', 'annee'))

    d = _champ(saisie, 'date_naissance')
    annees = {d.year - 1, d.year, d.year + 1} if d else set()
    comptes, retenus = {}, set()
    for patient_id, _cle, annee in lignes:
        comptes[patient_id] = comptes.get(patient_id, 0) + 1
        if comptes[patient_id] >= 2:
            retenus.add(patient_id)
        if annees and annee in annees:
            retenus.add(patient_id)
    return retenus


def _preselection(saisie, queryset=None):
    """Filtre SQL : les fiches qui ont au moins une chance d'être la même personne.

    Chaque condition **croise deux indices**. L'ancienne version les posait en
    « ou » séparés — année de naissance à un an près, ou trois lettres d'un mot
    n'importe où — et ramenait 17 275 fiches sur 47 813 pour un nom courant :
    la recherche tenait huit secondes, dont sept passées à scorer des gens qui
    n'avaient rien à voir.

    Les quatre familles reprennent les clés de blocage du script d'analyse
    (`tester_doublons_excel._cles`), pour que l'écran de saisie et l'analyse de
    masse voient les mêmes candidats :

    1. même téléphone ;
    2. deux mots du nom en commun ;
    3. un mot du nom + l'année de naissance à un an près ;
    4. le début d'un mot + la date exacte, jour et mois inversés compris ;
    5. la ressemblance sonore, croisée elle aussi (voir `_pks_phonetiques`).

    Les familles 1 et 2 ne demandent aucune date : une fiche sans date de
    naissance — le champ est facultatif — reste trouvable par son téléphone ou
    par deux mots de son nom.
    """
    q = Q()
    d = _champ(saisie, 'date_naissance')
    noms = [m for m in mots(_champ(saisie, 'nom')) + mots(_champ(saisie, 'prenoms'))
            if len(m) >= 3]

    # 1. Le téléphone, l'indice le plus sûr et le plus sélectif.
    for tel in _telephones(saisie):
        fin = tel[-8:]
        q |= Q(telephone__endswith=fin) | Q(telephone2__endswith=fin)

    # 2. Deux mots en commun : « KOUASSI » seul ramène des milliers de fiches,
    #    « KOUASSI » et « BELINDA » ensemble, une poignée.
    for i in range(len(noms)):
        for j in range(i + 1, len(noms)):
            q |= _mot_present(noms[i]) & _mot_present(noms[j])

    if d:
        annees = Q(date_naissance__year__gte=d.year - 1,
                   date_naissance__year__lte=d.year + 1)
        dates = Q(date_naissance=d)
        # Jour et mois intervertis à la saisie (12/04 pour 04/12).
        if d.day <= 12:
            try:
                dates |= Q(date_naissance=d.replace(day=d.month, month=d.day))
            except ValueError:
                pass
        for m in noms:
            # 3. Un mot entier + l'année : rattrape une date mal saisie.
            q |= _mot_present(m) & annees
            # 4. Le début du mot + la date exacte : rattrape une faute dans le
            #    nom, puisque la date, elle, concorde au jour près.
            q |= _debut_present(m) & dates

    # 5. La ressemblance sonore. Elle a besoin du périmètre pour ne lire que
    #    les clés du bon centre ; sans lui, on s'en passe plutôt que de lire
    #    celles de tout le monde.
    if queryset is not None:
        pks = _pks_phonetiques(saisie, queryset)
        if pks:
            q |= Q(pk__in=pks)
    return q


def chercher_doublons(saisie, exclure_pk=None, seuil=None, limite=MAX_CANDIDATS, queryset=None):
    """Les patients existants qui ressemblent à `saisie`, du plus probable au
    moins probable. `saisie` : dict (nom, prenoms, date_naissance, sexe,
    telephone, telephone2) ou instance de Patient. `queryset` remplace le
    périmètre par défaut (centre actif, ou tous si DOUBLONS_PATIENTS_TOUS_CENTRES)."""
    seuil = SEUIL_AVERTISSEMENT if seuil is None else seuil
    if not (_champ(saisie, 'nom') or _champ(saisie, 'prenoms')):
        return []
    perimetre = queryset if queryset is not None else _base_queryset()
    # Une fiche absorbée par une fusion, ou écartée à la main, n'est plus un
    # dossier : la proposer rouvrirait ce qu'on vient de fermer.
    perimetre = perimetre.filter(fusionne_dans__isnull=True, masque=False)
    q = _preselection(saisie, perimetre)
    if not q:
        return []
    qs = perimetre.filter(q)
    if exclure_pk:
        qs = qs.exclude(pk=exclure_pk)
        # « Ce n'est pas un doublon » a déjà été dit de ces paires-là : à la
        # modification d'une fiche connue, on ne repose pas la question.
        qs = qs.exclude(pk__in=_pks_ecartes(exclure_pk))
    resultats = [scorer(saisie, p) for p in qs.only(
        'pk', 'code_patient', 'nom', 'prenoms', 'date_naissance', 'sexe',
        # `date_naissance_approx` porte `Patient.date_precise`, que `scorer`
        # consulte : absent de cette liste, Django le rechargerait fiche par
        # fiche, et la présélection en ramène des milliers.
        'date_naissance_approx',
        'telephone', 'telephone2', 'centre_id')]
    resultats = [r for r in resultats if r.score >= seuil]
    resultats.sort(key=lambda r: r.score, reverse=True)
    return resultats[:limite]


def _pks_ecartes(pk):
    """Les fiches dont on a déjà dit qu'elles ne font pas doublon avec `pk`."""
    from .models import PaireEcartee
    paires = PaireEcartee.all_objects.filter(Q(patient_a_id=pk) | Q(patient_b_id=pk))
    return {autre for a, b in paires.values_list('patient_a_id', 'patient_b_id')
            for autre in (a, b) if autre != pk}


def paire_ordonnee(pk_a, pk_b):
    """(plus petit, plus grand) — l'ordre sous lequel une paire s'écrit.

    Sans ordre fixe, la même paire s'enregistrerait deux fois et aucune
    contrainte d'unicité ne tiendrait.
    """
    return (pk_a, pk_b) if pk_a < pk_b else (pk_b, pk_a)


# ── Index de blocage, pour les traitements de masse ─────────────────────────

def cles_blocage(fiche):
    """Les clés sous lesquelles une fiche se range, pour un rapprochement en
    mémoire. Reprend `tester_doublons_excel._cles` : deux fiches ne sont
    comparées que si elles partagent au moins une clé.

    `fiche` : dict ou objet portant nom, prenoms, date_naissance, telephone,
    telephone2 et, facultativement, date_precise.
    """
    cles = set()
    for tel in _telephones(fiche):
        cles.add('T' + tel[-8:])
    noms = [m for m in mots(_champ(fiche, 'nom')) + mots(_champ(fiche, 'prenoms'))
            if len(m) >= 3]
    for i in range(len(noms)):
        for j in range(i + 1, len(noms)):
            cles.add('W' + '|'.join(sorted((noms[i], noms[j]))))
    d = _champ(fiche, 'date_naissance')
    if d:
        precise = _champ(fiche, 'date_precise') is not False
        for m in noms:
            cles.add(f'Y{m}|{d.year}')
            cles.add(f'Y{m}|{d.year + 1}')
            if precise:
                cles.add(f'D{m[:3]}|{d.isoformat()}')
                if d.day <= 12:
                    cles.add(f'D{m[:3]}|{d.year}-{d.day:02d}-{d.month:02d}')
    # Les deux familles sonores, dans la même forme qu'en SQL : l'écran de
    # saisie et les traitements de masse doivent voir les mêmes candidats.
    phonetiques = _cles_phonetiques(fiche)
    for i in range(len(phonetiques)):
        for j in range(i + 1, len(phonetiques)):
            cles.add('P' + '|'.join((phonetiques[i], phonetiques[j])))
    if d:
        for c in phonetiques:
            cles.add(f'A{c}|{d.year}')
            cles.add(f'A{c}|{d.year + 1}')
    return cles


class IndexBlocage:
    """Rapprochement sans requête, pour l'import d'un gros fichier.

    Interroger la base ligne à ligne coûterait des heures sur 48 000 lignes.
    L'import tient déjà toutes les fiches en mémoire pour sa clé d'identité :
    on les range ici sous leurs clés de blocage, et chaque ligne ne se compare
    qu'aux quelques fiches qui en partagent une.

    L'année ±1 est posée des deux côtés (`Y…|année` et `Y…|année+1`) : une
    fiche de 1992 et une de 1993 se retrouvent donc sous la même clé.
    """

    def __init__(self):
        self._par_cle = {}
        self._fiches = {}

    def ajouter(self, identifiant, fiche):
        self._fiches[identifiant] = fiche
        for cle in cles_blocage(fiche):
            self._par_cle.setdefault(cle, set()).add(identifiant)

    def candidats(self, fiche):
        trouves = set()
        for cle in cles_blocage(fiche):
            trouves |= self._par_cle.get(cle, set())
        return [(i, self._fiches[i]) for i in trouves]

    def meilleur(self, saisie, seuil=None):
        """(identifiant, score) de la fiche la plus proche au-dessus du seuil,
        ou (None, 0). Le seuil par défaut est celui de l'avertissement."""
        seuil = SEUIL_AVERTISSEMENT if seuil is None else seuil
        meilleur_id, meilleur_score = None, 0
        for identifiant, fiche in self.candidats(saisie):
            score = scorer(saisie, fiche).score
            if score >= seuil and score > meilleur_score:
                meilleur_id, meilleur_score = identifiant, score
        return meilleur_id, meilleur_score
