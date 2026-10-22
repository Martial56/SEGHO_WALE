"""Recomposer les groupes à partir des paires, à la lecture.

Les groupes ne sont pas stockés. Un groupe n'est pas une donnée saisie : c'est
une vue sur les paires, qui se refait entièrement à chaque passage du recalcul.
L'écrire voudrait dire, à chaque fois, le réconcilier avec ce qu'une personne a
décidé — fiche à garder choisie à la main, paire écartée —, et c'est
exactement là que ces décisions se perdraient. On préfère relire les paires :
8 500 lignes, quelques centièmes de seconde.

La règle de composition vient de `tester_doublons_excel.regrouper`, et elle est
la même : pas d'effet de chaîne. « A ressemble à B, B ressemble à C » ne suffit
pas — sinon, de maillon en maillon, 37 000 fiches finissaient dans un seul
groupe. Deux groupes ne se réunissent que si **chaque** fiche de l'un ressemble
à **chaque** fiche de l'autre, et jamais au-delà de huit.

Les paires « à vérifier », elles, ne se regroupent pas : chacune reste un duo.
"""

import datetime

from django.core.cache import cache

from .doublons import normaliser_texte

#: Au-delà, ce n'est plus « la même personne saisie plusieurs fois ».
TAILLE_MAX = 8

#: Les groupes se recomposent en un dixième de seconde, mais pas à chaque
#: clic de pagination. La clé porte la date du dernier recalcul : le relevé
#: suivant la périme tout seul, sans qu'on ait à y penser.
DUREE_CACHE = 3600

#: À incrémenter dès que `_construire_index` change la forme de ses lignes.
#: Sans cela, un serveur fraîchement déployé continue de servir l'ancienne
#: forme jusqu'au recalcul suivant — et l'écran perd en silence ce qu'elle
#: n'avait pas encore (la raison du rapprochement, par exemple).
VERSION_INDEX = 4


def _scores_certains(centre_id):
    from .models import DoublonPaire
    return list(DoublonPaire.all_objects
                .filter(centre_id=centre_id, niveau='certain')
                .order_by('-score')
                .values_list('patient_a_id', 'patient_b_id', 'score', 'details'))


def composer(paires):
    """Les groupes, depuis des `(pk_a, pk_b, score)` triés du plus sûr au moins.

    Rendu : liste de {'membres': [pk…], 'score': le plus faible lien du groupe,
    'paire': les deux fiches de ce lien}. C'est de cette paire-là que l'écran
    tire la raison affichée : donner celle du lien le plus sûr ferait promettre
    au groupe entier une ressemblance que son maillon le plus faible n'a pas.
    """
    connus = {(a, b): score for a, b, score in paires}

    def lien(x, y):
        return connus.get((x, y) if x < y else (y, x), 0)

    groupe_de = {}
    for a, b, _score in paires:
        ga, gb = groupe_de.get(a), groupe_de.get(b)
        if ga is not None and ga is gb:
            continue
        ma = ga if ga is not None else [a]
        mb = gb if gb is not None else [b]
        if len(ma) + len(mb) > TAILLE_MAX:
            continue
        # Chacune avec chacune : un lien manquant, et les deux groupes restent
        # séparés. La paire n'est pas perdue pour autant, elle reste dans le
        # relevé et se lira comme « à vérifier ».
        if all(lien(x, y) for x in ma for y in mb):
            fusion = ma + mb
            for x in fusion:
                groupe_de[x] = fusion

    vus, groupes = set(), []
    for membres in groupe_de.values():
        if id(membres) in vus:
            continue
        vus.add(id(membres))
        tries = sorted(membres)
        maillons = [((x, y), lien(x, y))
                    for i, x in enumerate(tries) for y in tries[i + 1:]]
        paire, faible = min(maillons, key=lambda maillon: maillon[1])
        groupes.append({'membres': tries, 'score': faible, 'paire': paire})
    groupes.sort(key=lambda g: (-g['score'], -len(g['membres']), g['membres'][0]))
    return groupes


# ── L'index, mis en cache ───────────────────────────────────────────────────

def cle_groupe(membres):
    """L'identifiant d'un groupe dans une adresse : « 12-34 »."""
    return '-'.join(str(pk) for pk in sorted(membres))


def membres_depuis_cle(cle):
    try:
        return sorted({int(x) for x in cle.split('-') if x})
    except ValueError:
        return []


def _construire_index(centre_id):
    from .models import DoublonPaire, Patient

    certaines = _scores_certains(centre_id)
    details = {(a, b): d for a, b, _score, d in certaines}

    # L'index range les mesures (`details`) et le maillon d'où elles viennent
    # (`paire`) ; la phrase qu'on affiche se compose à l'affichage, quand les
    # fiches sont là. Voir `_raisons_du_groupe`.
    lignes = []
    for groupe in composer([(a, b, s) for a, b, s, _d in certaines]):
        lignes.append({'membres': groupe['membres'], 'score': groupe['score'],
                       'niveau': 'certain', 'paire': groupe['paire'],
                       'details': details.get(groupe['paire'])})

    deja = {pk for ligne in lignes for pk in ligne['membres']}
    a_verifier = (DoublonPaire.all_objects
                  .filter(centre_id=centre_id, niveau='avertissement')
                  .order_by('-score')
                  .values_list('patient_a_id', 'patient_b_id', 'score', 'details'))
    for a, b, score, detail in a_verifier:
        # Une paire dont les deux fiches sont déjà réunies dans un groupe
        # certain n'a pas à être reposée : on l'a déjà sous les yeux.
        if a in deja and b in deja:
            continue
        lignes.append({'membres': [a, b], 'score': score,
                       'niveau': 'avertissement', 'paire': (a, b),
                       'details': detail})

    # Une seule lecture des fiches citées : de quoi chercher par nom ou par
    # code sans relire la table à chaque frappe, et de quoi composer la
    # phrase de raison une fois pour toutes (voir `_phrase_de_la_ligne`).
    fiches = {pk: (code, nom, prenoms) for pk, code, nom, prenoms
              in Patient.all_objects.filter(
                  pk__in={pk for ligne in lignes for pk in ligne['membres']}
              ).values_list('pk', 'code_patient', 'nom', 'prenoms')}
    # Les écritures mises à plat une fois par fiche, et non une fois par
    # ligne : les mêmes fiches reviennent dans plusieurs paires, et
    # normaliser huit mille cinq cents fois de plus coûtait une demi-seconde.
    normes = {pk: (normaliser_texte(nom), normaliser_texte(prenoms))
              for pk, (_code, nom, prenoms) in fiches.items()}
    for ligne in lignes:
        ligne['cle'] = cle_groupe(ligne['membres'])
        ligne['recherche'] = ' '.join(
            '{} {} {}'.format(*fiches.get(pk, ('', '', '')))
            for pk in ligne['membres']).lower()
        ligne['raison'] = _phrase_de_la_ligne(ligne, normes)
    return lignes


def _phrase_de_la_ligne(ligne, normes):
    """La phrase de raison, rangée dans l'index pour pouvoir filtrer dessus.

    L'affichage, lui, la recompose à partir des fiches chargées (voir
    `_raisons_du_groupe`) : c'est ce qui la corrige sans attendre un
    recalcul. Les deux peuvent donc se contredire sur un groupe dont un nom
    vient d'être corrigé, le temps que l'index se refasse — un lot le refait
    tout de suite, le recalcul de nuit sinon.

    `normes` porte les écritures déjà mises à plat. « Même nom » se recompose
    ici à partir des deux champs plutôt que d'appeler `memes_noms`, qui
    normaliserait une troisième chaîne : la mise à plat réunit les champs par
    une espace et replie les blancs, les deux calculs donnent le même mot.
    """
    from .doublons import raisons

    details = dict(ligne.get('details') or {})
    a, b = ligne.get('paire') or (None, None)
    if a in normes and b in normes:
        (nom_a, prenoms_a), (nom_b, prenoms_b) = normes[a], normes[b]
        details['nom_identique'] = nom_a == nom_b
        details['prenoms_identiques'] = prenoms_a == prenoms_b
        details['noms_identiques'] = (f'{nom_a} {prenoms_a}'.strip()
                                      == f'{nom_b} {prenoms_b}'.strip())
    return ', '.join(raisons(details))


def index(centre_id):
    """Toutes les entrées de la liste, certaines d'abord, mises en cache.

    Ne porte que des identifiants : les fiches elles-mêmes ne sont chargées que
    pour la page affichée. Mettre 8 500 patients en cache pour en montrer
    vingt-cinq n'aurait pas de sens.
    """
    from django.db.models import Count, Max
    from .models import DoublonPaire

    # La clé se lit en base, pas en mémoire : trois workers gunicorn ont chacun
    # leur cache, et vider le sien ne vide pas celui des autres. Le nombre de
    # paires **et** la date du dernier calcul : la date seule ne bougerait pas
    # quand une décision supprime une paire, et la liste continuerait de
    # montrer un groupe déjà traité.
    etat = DoublonPaire.all_objects.filter(centre_id=centre_id).aggregate(
        nombre=Count('pk'), dernier=Max('date_calcul'))
    if not etat['nombre']:
        return []
    cle = (f'doublons:index:{VERSION_INDEX}:{centre_id}:'
           f"{etat['nombre']}:{etat['dernier'].timestamp()}")
    lignes = cache.get(cle)
    if lignes is None:
        lignes = _construire_index(centre_id)
        cache.set(cle, lignes, DUREE_CACHE)
    return lignes


#: Les trois états de données rattachées, et ce qu'ils veulent dire sur un
#: groupe. L'ordre est celui du menu, du plus facile à traiter au moins.
RATTACHEES = [
    ('aucune', 'Aucune des deux fiches'),
    ('une', 'Une seule des deux'),
    ('deux', 'Les deux fiches'),
]


def classer_rattachees(ligne, totaux):
    """« aucune », « une » ou « deux » pour ce groupe.

    « deux » se lit « au moins deux » : un groupe de trois fiches dont deux
    portent des données se traite comme un groupe de deux qui en portent.
    """
    porteuses = sum(1 for pk in ligne['membres'] if totaux.get(pk))
    if not porteuses:
        return 'aucune'
    return 'une' if porteuses == 1 else 'deux'


def filtrer(lignes, niveau='tous', recherche='', raisons=(), rattachees=(),
            totaux=None):
    """Les quatre filtres de l'écran, cumulables.

    `niveau` est exclusif — un groupe est quasi certain ou à vérifier ;
    `raisons` et `rattachees` sont des listes : cocher deux phrases montre
    les groupes de l'une **ou** de l'autre.

    `totaux` ({pk: nombre rattaché}) n'est demandé que si le filtre des
    données rattachées est posé : il coûte une seconde et demie à constituer
    (voir `liens_patient.totaux_rattaches`), autant ne pas le payer pour
    rien.
    """
    if niveau in ('certain', 'avertissement'):
        lignes = [l for l in lignes if l['niveau'] == niveau]
    recherche = (recherche or '').strip().lower()
    if recherche:
        mots = recherche.split()
        lignes = [l for l in lignes if all(m in l['recherche'] for m in mots)]
    if raisons:
        voulues = set(raisons)
        lignes = [l for l in lignes if l.get('raison') in voulues]
    if rattachees and totaux is not None:
        voulus = set(rattachees)
        lignes = [l for l in lignes
                  if classer_rattachees(l, totaux) in voulus]
    return lignes


def compter_par_raison(lignes):
    """[(phrase, nombre)] de la plus fréquente à la moins fréquente.

    Compté sur les lignes qu'on lui donne, c'est-à-dire sur le relevé déjà
    filtré par les *autres* filtres : le nombre annoncé est celui qu'on
    obtiendra en cochant, pas un nombre théorique.
    """
    from collections import Counter

    comptes = Counter(l.get('raison') or '' for l in lignes)
    return [(phrase, nombre) for phrase, nombre
            in sorted(comptes.items(), key=lambda c: (-c[1], c[0])) if phrase]


def compter_par_niveau(lignes):
    from collections import Counter
    return Counter(l['niveau'] for l in lignes)


def compter_par_rattachees(lignes, totaux):
    from collections import Counter
    return Counter(classer_rattachees(l, totaux) for l in lignes)


#: Les dimensions de regroupement, et le libellé de leur bande.
DIMENSIONS = [
    ('raison', 'Raison'),
    ('niveau', 'Niveau de ressemblance'),
    ('rattachees', 'Données rattachées'),
]

NIVEAUX_AFFICHES = {'certain': 'Quasi certain', 'avertissement': 'À vérifier'}


def sections(lignes, dimension, totaux=None):
    """Les lignes rangées en sections, et le total de chacune.

    Rendu : [(libellé, [lignes])], les sections les plus fournies d'abord.
    Le total vient de l'ensemble filtré, pas de la page : une section qui
    déborde doit annoncer ce qu'elle contient, pas ce qu'on en voit.
    """
    if dimension == 'raison':
        cle = lambda l: l.get('raison') or 'Sans raison relevée'          # noqa: E731
    elif dimension == 'niveau':
        cle = lambda l: NIVEAUX_AFFICHES.get(l['niveau'], l['niveau'])    # noqa: E731
    elif dimension == 'rattachees':
        libelles = dict(RATTACHEES)
        cle = lambda l: libelles[classer_rattachees(l, totaux or {})]     # noqa: E731
    else:
        return None

    paquets = {}
    for ligne in lignes:
        paquets.setdefault(cle(ligne), []).append(ligne)
    return sorted(paquets.items(), key=lambda s: (-len(s[1]), s[0]))


# ── Les fiches d'une page ───────────────────────────────────────────────────

def garnir(lignes):
    """Charge les fiches et les comptes des entrées affichées.

    Appelée sur une page, jamais sur l'index entier.
    """
    from .liens_patient import champs_en_plus, comptes
    from .models import ChoixFicheGardee, Patient

    pks = [pk for ligne in lignes for pk in ligne['membres']]
    fiches = {p.pk: p for p in Patient.all_objects.filter(pk__in=pks)
              .select_related('assurance')}
    rattachees = comptes(pks)
    choisis = dict(ChoixFicheGardee.all_objects.filter(patient_id__in=pks)
                   .values_list('patient_id', 'date'))

    garnies = []
    for ligne in lignes:
        membres = [fiches[pk] for pk in ligne['membres'] if pk in fiches]
        if len(membres) < 2:
            continue                      # une fiche supprimée entre-temps
        for fiche in membres:
            # Posés sur la fiche elle-même : le gabarit n'a plus qu'à les
            # lire, sans filtre maison pour aller chercher dans un dictionnaire.
            fiche.rattache = rattachees.get(fiche.pk, {})
            fiche.rattache_total = sum(fiche.rattache.values())
            fiche.rattache_resume = resumer(fiche.rattache)
            fiche.naissance = naissance_affichee(fiche)
        marquer_differences(membres)
        humains = [p.pk for p in membres if p.pk in choisis]
        garnie = dict(ligne)
        garnie['fiches'] = membres
        garnie['garder'] = (max(humains, key=lambda pk: choisis[pk]) if humains
                            else suggerer_a_garder(membres, rattachees))
        garnie['choix_humain'] = bool(humains)
        garnie['raisons'] = _raisons_du_groupe(ligne, fiches)
        garnie['masquable'] = _masquable(membres, garnie['garder'],
                                         champs_en_plus, ligne.get('niveau'))
        garnies.append(garnie)
    return garnies


def naissance_affichee(fiche):
    """« 01/10/1996 », « ≈ 1996 », ou rien du tout."""
    if not fiche.date_naissance:
        return ''
    if fiche.date_naissance_approx:
        return f'≈ {fiche.date_naissance.year}'
    return fiche.date_naissance.strftime('%d/%m/%Y')


def _raisons_du_groupe(ligne, fiches):
    """Pourquoi ce groupe est là, dit d'après les fiches qu'on affiche.

    Le relevé range des mesures ; l'écriture exacte des noms, elle, se lit sur
    les fiches elles-mêmes. On la relit ici plutôt que de l'attendre du
    prochain recalcul : « même nom » ne doit jamais s'afficher devant BALO et
    BALLO.
    """
    from .doublons import memes_champs, memes_noms, raisons

    details = dict(ligne.get('details') or {})
    a, b = ligne.get('paire') or (None, None)
    if a in fiches and b in fiches:
        details['noms_identiques'] = memes_noms(fiches[a], fiches[b])
        (details['nom_identique'],
         details['prenoms_identiques']) = memes_champs(fiches[a], fiches[b])
    return raisons(details)


def resume_du_groupe(fiches):
    """Le score et la raison de ce groupe, relus en base. None si plus rien.

    L'écran de comparaison s'ouvre depuis une carte qui portait les deux ; les
    perdre en chemin oblige à revenir en arrière pour se rappeler pourquoi ces
    fiches sont rapprochées.

    Le score retenu est celui du **maillon le plus faible**, comme dans la
    liste : annoncer celui du lien le plus sûr promettrait au groupe entier
    une ressemblance que sa paire la moins bonne n'a pas.
    """
    from .models import DoublonPaire

    pks = [f.pk for f in fiches]
    paires = list(DoublonPaire.all_objects
                  .filter(patient_a_id__in=pks, patient_b_id__in=pks)
                  .values_list('patient_a_id', 'patient_b_id', 'score',
                               'niveau', 'details'))
    if not paires:
        return None
    a, b, score, _niveau, details = min(paires, key=lambda paire: paire[2])
    return {
        'score': score,
        # Le groupe est « certain » dès qu'un de ses liens l'est : c'est ainsi
        # que l'index le classe, et la pastille doit dire la même chose.
        'niveau': ('certain' if any(p[3] == 'certain' for p in paires)
                   else 'avertissement'),
        'raisons': _raisons_du_groupe({'details': details, 'paire': (a, b)},
                                      {f.pk: f for f in fiches}),
    }


def valeur_affichee(fiche, champ):
    """Un champ de la fiche, tel qu'il doit se lire à l'écran.

    Ici plutôt que dans chaque gabarit : la comparaison côte à côte et l'écran
    de fusion montrent les mêmes champs, et doivent les montrer pareil. Une
    date approximative dit « ≈ 1996 », un sexe dit « Masculin » et non « M »,
    une photo dit son nom de fichier.
    """
    if champ == 'date_naissance':
        return naissance_affichee(fiche)
    if champ == 'sexe':
        return fiche.get_sexe_display() if fiche.sexe else ''
    if champ == 'assurance':
        return str(fiche.assurance) if fiche.assurance_id else ''
    valeur = getattr(fiche, champ, None)
    if hasattr(valeur, 'storage'):                       # FieldFile
        return valeur.name.rsplit('/', 1)[-1] if valeur.name else ''
    if valeur is None or valeur is False:
        return ''
    if isinstance(valeur, datetime.date):
        return valeur.strftime('%d/%m/%Y')
    return str(valeur)


def marquer_differences(membres):
    """Pose sur chaque fiche du groupe ce qui les sépare.

    Même règle qu'à la saisie : seul un écart entre deux valeurs **renseignées**
    en est un. Un champ vide d'un côté ne contredit rien, et le surligner
    détournerait le regard de ce qui se contredit vraiment.

    Le même verdict est posé sur toutes les fiches du groupe : on surligne les
    deux côtés, pour que l'œil ait quelque chose à comparer.

    Les noms se marquent **mot à mot** : entre « ASSENA ELIAQUIM » et
    « ASSENA ELIAKIM », seul le second mot diffère, et c'est lui seul qu'il
    faut montrer. Surligner la ligne entière noierait l'écart dans ce que les
    deux fiches ont en commun.
    """
    from .doublons import normaliser_telephone

    naissances = [f.naissance for f in membres]
    # Dès qu'une des dates n'est qu'une estimation, seule l'année se compare :
    # « ≈ 1996 » et « 01/10/1996 » ne se contredisent pas.
    if any(n.startswith('≈') for n in naissances if n):
        naissances = [n[-4:] for n in naissances]

    noms = mots_marques([f.nom for f in membres])
    prenoms = mots_marques([f.prenoms for f in membres])
    ecarts = {
        'nom': any(m['diff'] for liste in noms for m in liste),
        'prenoms': any(m['diff'] for liste in prenoms for m in liste),
        'naissance': _se_contredisent(naissances),
        'telephone': _se_contredisent(
            normaliser_telephone(f.telephone) for f in membres),
    }
    for fiche, mots_nom, mots_prenoms in zip(membres, noms, prenoms):
        fiche.differe = ecarts
        fiche.mots_nom = mots_nom
        fiche.mots_prenoms = mots_prenoms
        # Nom et prénoms s'écrivent d'un seul tenant sur la carte : une liste
        # unique évite au gabarit d'avoir à recoller l'espace entre les deux.
        fiche.mots_identite = mots_nom + mots_prenoms


def mots_marques(valeurs):
    """Les mots de chaque valeur, ceux que toutes ne partagent pas marqués.

    Rendu : une liste par valeur, de {'mot': tel qu'écrit, 'diff': bool}. Le
    rapprochement se fait sur la forme normalisée — « Kôné » et « KONE » sont
    le même mot — mais c'est l'écriture d'origine qui s'affiche.
    """
    from .doublons import normaliser_texte

    ecrits = [str(valeur or '').split() for valeur in valeurs]
    normalises = [[normaliser_texte(mot) for mot in liste] for liste in ecrits]
    # Une valeur vide ne contredit rien : elle ne retire aucun mot commun.
    remplies = [set(liste) for liste in normalises if liste]
    communs = set.intersection(*remplies) if remplies else set()
    return [[{'mot': mot, 'diff': cle not in communs}
             for mot, cle in zip(ecrit, normalise)]
            for ecrit, normalise in zip(ecrits, normalises)]


def _se_contredisent(valeurs):
    return len({v for v in valeurs if v}) > 1


def _masquable(membres, garder, champs_en_plus, niveau='certain'):
    """La fiche qu'on peut retirer d'un clic, s'il y en a une.

    La grande majorité des groupes sont une fiche pleine et sa copie vide,
    créée par une seconde saisie. Les ouvrir une par une pour n'y rien lire
    ferait des centaines d'écrans ; le bouton n'apparaît que lorsqu'il n'y a
    précisément rien à lire : deux fiches, aucune donnée rattachée d'un côté,
    et pas un champ que l'autre n'ait déjà.

    Jamais sur un groupe « à vérifier ». Ces groupes-là sont souvent deux
    personnes différentes — un prénom voisin, deux dates qui ne concordent
    pas —, et la fiche vide est alors simplement une fiche neuve. Un clic
    rapide la ferait disparaître sous le nom d'une autre. Il reste possible
    de la masquer, mais depuis l'écran de comparaison, les deux fiches sous
    les yeux.
    """
    if niveau != 'certain':
        return None
    if len(membres) != 2 or any(f.masque for f in membres):
        return None
    gardee = next((f for f in membres if f.pk == garder), None)
    autre = next((f for f in membres if f.pk != garder), None)
    if gardee is None or autre is None or autre.rattache_total:
        return None
    if champs_en_plus(autre, gardee):
        return None
    return autre


def resumer(rattache):
    """« 3 rendez-vous, 2 factures », ou rien du tout."""
    return ', '.join(f'{nombre} {libelle.lower()}'
                     for libelle, nombre in sorted(rattache.items()))


def fiche_a_garder(fiches, rattachees=None):
    """(pk de la fiche gardée, les fiches explicitement choisies).

    Le choix d'une personne prime sur la suggestion ; s'il y en a plusieurs
    dans le groupe, le plus récent l'emporte. L'écran côte à côte et l'écran
    de fusion doivent répondre pareil, d'où cette fonction partagée.
    """
    from .models import ChoixFicheGardee

    choisis = dict(ChoixFicheGardee.all_objects.filter(patient__in=fiches)
                   .values_list('patient_id', 'date'))
    humains = [f.pk for f in fiches if f.pk in choisis]
    if humains:
        return max(humains, key=lambda pk: choisis[pk]), set(choisis)
    return suggerer_a_garder(fiches, rattachees or {}), set(choisis)


def suggerer_a_garder(fiches, rattachees=None):
    """Celle qui porte le plus de données, puis la plus complète, puis la plus
    ancienne.

    Les données rattachées passent avant tout : garder la fiche qui porte trois
    rendez-vous et deux factures, c'est trois lignes de moins à déplacer le
    jour de la fusion — et c'est celle que les gens connaissent. La complétude
    des champs ne départage qu'à égalité ; c'est tout ce dont disposait
    l'analyse d'origine, qui travaillait sur un fichier Excel sans rien
    derrière.

    Une suggestion, rien de plus : l'écran la propose, la personne tranche. Un
    `ChoixFicheGardee` la remplace sans discuter.
    """
    rattachees = rattachees or {}

    def cle(p):
        porte = sum(rattachees.get(p.pk, {}).values())
        completude = ((1 if p.telephone else 0) + (1 if p.telephone2 else 0)
                      + (0 if p.date_naissance_approx else 1) + (1 if p.sexe else 0)
                      + min(len((p.prenoms or '').split()), 3))
        return (-porte, -completude, p.code_patient or 'ZZZ')
    return min(fiches, key=cle).pk
