"""Recomposer les groupes à partir des paires, à la lecture.

Les groupes ne sont pas stockés. Un groupe n'est pas une donnée saisie : c'est
une vue sur les paires, qui se refait entièrement à chaque passage du recalcul.
L'écrire voudrait dire, à chaque fois, le réconcilier avec ce qu'une personne a
décidé — fiche à garder choisie à la main, paire écartée —, et c'est
exactement là que ces décisions se perdraient. On préfère relire les paires :
8 500 lignes, quelques millisecondes.

La règle vient de `tester_doublons_excel.regrouper`, et elle est la même :
pas d'effet de chaîne. « A ressemble à B, B ressemble à C » ne suffit pas —
sinon, de maillon en maillon, 37 000 fiches finissaient dans un seul groupe.
Deux groupes ne se réunissent que si **chaque** fiche de l'un ressemble à
**chaque** fiche de l'autre, et jamais au-delà de huit.
"""

#: Au-delà, ce n'est plus « la même personne saisie plusieurs fois ».
TAILLE_MAX = 8


def _scores_certains(centre_id):
    from .models import DoublonPaire
    return list(DoublonPaire.all_objects
                .filter(centre_id=centre_id, niveau='certain')
                .order_by('-score')
                .values_list('patient_a_id', 'patient_b_id', 'score'))


def composer(paires):
    """Les groupes, depuis des `(pk_a, pk_b, score)` triés du plus sûr au moins.

    Rendu : liste de {'membres': [pk…], 'score': le plus faible lien du groupe}.
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
        faible = min(lien(x, y) for i, x in enumerate(tries) for y in tries[i + 1:])
        groupes.append({'membres': tries, 'score': faible})
    groupes.sort(key=lambda g: (-g['score'], -len(g['membres']), g['membres'][0]))
    return groupes


def groupes(centre_id):
    """Les groupes quasi certains d'un centre, avec la fiche à garder."""
    composes = composer(_scores_certains(centre_id))
    if not composes:
        return []

    from .models import ChoixFicheGardee, Patient
    tous = {p.pk: p for p in Patient.all_objects.filter(
        pk__in=[pk for g in composes for pk in g['membres']])}
    # Une décision prise à la main l'emporte sur la suggestion ; si deux
    # fiches choisies tombent dans le même groupe, la plus récente gagne.
    choisis = {c.patient_id: c.date for c in ChoixFicheGardee.all_objects.filter(
        patient_id__in=tous)}

    for groupe in composes:
        membres = groupe['membres']
        humains = [pk for pk in membres if pk in choisis]
        groupe['garder'] = (max(humains, key=lambda pk: choisis[pk]) if humains
                            else suggerer_a_garder([tous[pk] for pk in membres]))
        groupe['choix_humain'] = bool(humains)
        groupe['fiches'] = [tous[pk] for pk in membres]
    return composes


def suggerer_a_garder(fiches):
    """La fiche la plus complète, et à égalité la plus ancienne.

    Une suggestion, rien de plus : l'écran de fusion la propose, la personne
    tranche. Un `ChoixFicheGardee` la remplace sans discuter.
    """
    def cle(p):
        completude = ((1 if p.telephone else 0) + (1 if p.telephone2 else 0)
                      + (0 if p.date_naissance_approx else 1) + (1 if p.sexe else 0)
                      + min(len((p.prenoms or '').split()), 3))
        return (-completude, p.code_patient or 'ZZZ')
    return min(fiches, key=cle).pk
