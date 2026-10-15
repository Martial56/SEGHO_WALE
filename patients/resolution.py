"""Retrouver une fiche par un repère qui ne mène plus nulle part.

Une fusion laisse derrière elle deux repères périmés : le **code** de la fiche
absorbée, et l'**ancien identifiant** qu'elle portait dans le logiciel
précédent. Les deux doivent ramener à la fiche gardée — c'est elle qui a tout
reçu, et c'est le dossier que la personne cherchait.

Deux chemins, dans cet ordre :

1. la fiche existe encore, marquée `fusionne_dans` : on remonte la chaîne de
   fiche en fiche ;
2. elle a été **supprimée définitivement** : plus aucune ligne de `Patient` ne
   porte ce code, et c'est le journal des fusions qui répond
   (`FusionPatient.code_absorbee`, `ancien_identifiant_absorbee`,
   `code_gardee`). La chaîne se remonte alors de fusion en fusion, et les deux
   chemins s'enchaînent : une fiche intermédiaire supprimée ne coupe rien.

Rien ici ne lève : un terme qui ne désigne rien rend un ensemble vide, et la
recherche ordinaire fait son travail comme avant.
"""

from django.db.models import Q

#: Les repères qu'on reconnaît. Un code se tape en entier ou pas du tout :
#: la correspondance est donc exacte, à la casse près. Chercher « PAT2026 » en
#: sous-chaîne remonterait la moitié de la base.
REPERES = ('code_patient', 'ancien_identifiant')

#: Garde-fou contre une chaîne qui se mordrait la queue. Une fusion de fusion
#: est normale (un groupe de trois), un cycle ne l'est pas.
PROFONDEUR_MAX = 10


def fiche_gardee(fiche):
    """Remonte `fusionne_dans` jusqu'à la fiche encore ouverte."""
    vus = set()
    while (fiche is not None and fiche.fusionne_dans_id
           and fiche.pk not in vus and len(vus) < PROFONDEUR_MAX):
        vus.add(fiche.pk)
        fiche = fiche.fusionne_dans
    return fiche


def pks_depuis_un_repere(terme):
    """Les fiches **ouvertes** que ce code ou cet ancien identifiant désigne.

    Rendu : un ensemble de pk, vide si le terme ne ressemble à rien de connu.
    Une fiche seulement masquée ne ramène rien : son contenu n'est allé nulle
    part, et la faire apparaître sous un autre nom tromperait.
    """
    from .models import Patient

    terme = (terme or '').strip()
    if not terme:
        return set()
    condition = Q()
    for champ in REPERES:
        condition |= Q(**{f'{champ}__iexact': terme})
    trouvees = (Patient.all_objects.filter(condition)
                .select_related('fusionne_dans')[:20])
    gardees = {fiche_gardee(fiche) for fiche in trouvees}
    # Le journal est consulté dans tous les cas, et non seulement quand rien
    # n'a été trouvé : les anciens identifiants ressemblent aux codes, et un
    # dossier bien vivant porte parfois comme ancien identifiant le code
    # d'une fiche supprimée. Les deux réponses sont justes ; laisser la
    # première masquer la seconde ferait disparaître la redirection.
    gardees.add(_par_le_journal(terme))
    return {f.pk for f in gardees if f is not None and not f.retiree}


def _par_le_journal(terme):
    """La fiche gardée au bout d'une chaîne dont une fiche a été supprimée.

    On ne lit que les fusions encore actives : une fusion annulée a rendu à
    la fiche absorbée son indépendance, et faire apparaître son ancien code
    sous un autre nom tromperait.
    """
    from .models import FusionPatient

    vus = set()
    for _ in range(PROFONDEUR_MAX):
        if not terme or terme.upper() in vus:
            return None
        vus.add(terme.upper())
        fusion = (FusionPatient.all_objects
                  .filter(Q(code_absorbee__iexact=terme)
                          | Q(ancien_identifiant_absorbee__iexact=terme),
                          annulee_le__isnull=True)
                  .select_related('gardee__fusionne_dans')
                  .order_by('-date').first())
        if fusion is None:
            return None
        if fusion.gardee_id:
            return fiche_gardee(fusion.gardee)
        # La fiche gardée a été supprimée elle aussi : son propre code
        # reprend la chaîne là où elle s'est arrêtée.
        terme = fusion.code_gardee


def condition_reperes(terme):
    """`Q` à ajouter en OU à une recherche, ou None s'il n'y a rien à ajouter."""
    pks = pks_depuis_un_repere(terme)
    return Q(pk__in=pks) if pks else None
