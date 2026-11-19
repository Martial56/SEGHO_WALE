"""Déclaration de la liste des patients pour la brique core.listing.

Décrit *quoi* filtrer et regrouper ; le comment (menus, comptages, pagination
par groupe, conditions personnalisées) vient de core.listing. Les vues n'ont plus
qu'à assembler.

Utilisé par la liste des patientes de gynécologie, et réutilisable tel quel par
toute autre liste de patients : seul le jeu de départ change.
"""

import re
from datetime import date

from django.db.models import Case, CharField, F, Q, Value, When
from django.db.models.functions import Length, Replace
from django.db.models.lookups import Contains, GreaterThan

from .doublons import normaliser_telephone
from .resolution import condition_reperes

from core.utils import annees_avant


# ── Bornes d'âge ────────────────────────────────────────────────────────────
# Les mêmes seuils servent au filtre et au regroupement : sans cela, « Adulte »
# dans les filtres et « Adultes » dans les groupes pourraient diverger.
SEUIL_MINEUR = 18
SEUIL_SENIOR = 60

LIBELLE_MINEUR = 'Mineurs (< 18 ans)'
LIBELLE_ADULTE = 'Adultes (18–60 ans)'
LIBELLE_SENIOR = 'Seniors (> 60 ans)'

#: `ancien_identifiant` en fait partie : les dossiers venus de l'ancien
#: logiciel se cherchent encore par le numéro qu'ils y portaient.
CHAMPS_RECHERCHE = ('nom', 'prenoms', 'code_patient', 'telephone',
                    'ancien_identifiant')


# ── Recherche par numéro de téléphone ───────────────────────────────────────
# La recherche libre compare le texte tel quel. Or un numéro s'écrit de dix
# façons : « 07 58 89 97 35 », « 07/58/89/97/35 », « 0.758899735 », « +225
# 0758899735 »… Une cinquantaine de fiches sont enregistrées avec des
# séparateurs, et taper les chiffres seuls ne les trouvait pas ; à l'inverse,
# taper le numéro avec points, tirets ou indicatif ne trouvait aucune fiche.
# On compare donc aussi les chiffres seuls, des deux côtés.

#: Caractères retirés du numéro enregistré avant comparaison.
SEPARATEURS_TELEPHONE = (' ', '.', '-', '/', '+', '*', ',', '(', ')')
#: Une saisie n'est un numéro que si, séparateurs ôtés, il ne reste que des chiffres.
_SAISIE_TELEPHONE = re.compile(r'^[\d\s.\-/+*,()]+$')


def _chiffres_seuls(champ):
    """Expression SQL : `champ` sans ses séparateurs (SQLite comme PostgreSQL)."""
    expression = F(champ)
    for separateur in SEPARATEURS_TELEPHONE:
        expression = Replace(expression, Value(separateur), Value(''))
    return expression


def condition_telephone(q):
    """`Q` qui retrouve un numéro quelle que soit son écriture, ou None si la
    saisie n'est pas un numéro (au moins 8 chiffres, rien d'autre que des
    séparateurs)."""
    if not q or not _SAISIE_TELEPHONE.match(q):
        return None
    chiffres = normaliser_telephone(q)
    if not chiffres:
        return None
    condition = Q()
    for champ in ('telephone', 'telephone2'):
        # Un numéro écrit avec des séparateurs est forcément plus long que
        # les chiffres cherchés : le nettoyage, coûteux, n'est appliqué qu'à
        # ceux-là (quelques centaines de fiches) ; les autres se comparent
        # directement.
        condition |= Q(**{f'{champ}__contains': chiffres})
        condition |= (Q(GreaterThan(Length(champ), len(chiffres)))
                      & Q(Contains(_chiffres_seuls(champ), chiffres)))
    return condition


def condition_recherche_en_plus(q):
    """Ce qui s'ajoute en OU à la recherche libre : repères d'une fiche
    fusionnée (voir `patients.resolution`) et numéro de téléphone normalisé."""
    condition = None
    for en_plus in (condition_reperes(q), condition_telephone(q)):
        if en_plus is not None:
            condition = en_plus if condition is None else condition | en_plus
    return condition


def _bornes(aujourdhui):
    return annees_avant(aujourdhui, SEUIL_MINEUR), annees_avant(aujourdhui, SEUIL_SENIOR)


def _appliquer_age(qs, codes, contexte):
    """Tranches d'âge retenues, combinées en OU.

    Passe par une fonction plutôt que par des Q figés : les bornes dépendent de
    la date du jour, qu'un Q construit à l'import figerait au démarrage du
    serveur — le filtre se décalerait après minuit.
    """
    if not codes:
        return qs
    borne_18, borne_60 = _bornes(contexte.get('aujourdhui') or date.today())
    condition = Q()
    if 'mineur' in codes:
        condition |= Q(date_naissance__gt=borne_18)
    if 'adulte' in codes:
        condition |= Q(date_naissance__lte=borne_18, date_naissance__gt=borne_60)
    if 'senior' in codes:
        condition |= Q(date_naissance__lte=borne_60)
    return qs.filter(condition)


def _appliquer_nouveaux(qs, codes, contexte):
    if 'nouveau' not in codes:
        return qs
    from datetime import timedelta

    from django.utils import timezone
    return qs.filter(date_creation__gte=timezone.now() - timedelta(days=30))


def familles_patients():
    """Familles de filtres d'une liste de patients."""
    from core.listing import Famille

    return [
        Famille('genre', 'Genre', valeurs=[
            ('femme', 'Femme', Q(sexe='F')),
            ('homme', 'Homme', Q(sexe='M')),
        ]),
        Famille('age', "Tranche d'âge", applique=_appliquer_age, valeurs=[
            ('mineur', 'Mineur (moins de 18 ans)', Q()),
            ('adulte', 'Adulte (18 – 60 ans)',     Q()),
            ('senior', 'Senior (plus de 60 ans)',  Q()),
        ]),
        Famille('nouveau', 'Nouveaux (30 derniers jours)',
                applique=_appliquer_nouveaux,
                valeurs=[('nouveau', 'Nouveaux (30 derniers jours)', Q())]),
    ]


# ── Dimensions de regroupement ──────────────────────────────────────────────

def _tranche_age(patient, aujourdhui):
    if not patient.date_naissance:
        return 'Âge inconnu'
    borne_18, borne_60 = _bornes(aujourdhui)
    if patient.date_naissance > borne_18:
        return LIBELLE_MINEUR
    if patient.date_naissance > borne_60:
        return LIBELLE_ADULTE
    return LIBELLE_SENIOR


def construire_dimensions(aujourdhui=None):
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Patient

    aujourdhui = aujourdhui or date.today()
    borne_18, borne_60 = _bornes(aujourdhui)
    libelles_sexe = dict(Patient.SEXE)

    # L'annotation reproduit en SQL la logique de _tranche_age : les compteurs
    # agrégés en base et les libellés calculés côté Python doivent tomber sur les
    # mêmes clés, sinon les groupes s'affichent sans jamais charger leurs lignes.
    tranche_sql = Case(
        When(date_naissance__isnull=True, then=Value('Âge inconnu')),
        When(date_naissance__gt=borne_18, then=Value(LIBELLE_MINEUR)),
        When(date_naissance__gt=borne_60, then=Value(LIBELLE_ADULTE)),
        default=Value(LIBELLE_SENIOR),
        output_field=CharField(),
    )

    # `valeur` reçoit un objet, `label` reçoit la ligne agrégée (un dict) : les
    # deux doivent produire exactement le même libellé, sinon les compteurs
    # calculés en base ne retrouvent pas les groupes construits côté Python.
    return {
        'sexe': Dimension(
            cle='sexe', libelle='Genre',
            valeur=lambda p: libelles_sexe.get(p.sexe, p.sexe or 'Non renseigné'),
            values=('sexe',),
            label=lambda r: libelles_sexe.get(r['sexe'], r['sexe'] or 'Non renseigné'),
            order=('sexe',),
        ),
        'age': Dimension(
            cle='age', libelle="Tranche d'âge",
            valeur=lambda p, j=aujourdhui: _tranche_age(p, j),
            values=('tranche_age',), annotate={'tranche_age': tranche_sql},
            label=lambda r: r['tranche_age'],
            order=('-date_naissance',),
        ),
        'assurance': Dimension(
            cle='assurance', libelle='Assurance',
            valeur=lambda p: str(p.assurance) if p.assurance_id else 'Sans assurance',
            values=('assurance__nom',),
            label=lambda r: r['assurance__nom'] or 'Sans assurance',
            order=('assurance__nom',),
        ),
    }


#: Déjà proposés en clair par le menu : inutile de les répéter dans
#: « Ajouter un groupement personnalisé ».
CHAMPS_DEJA_GROUPABLES = ('sexe', 'assurance')


def champs_patients():
    """Champs proposés au filtre et au groupement personnalisés."""
    from core.listing import champs_filtrables
    from .models import Patient
    return champs_filtrables(Patient)


def dimensions_personnalisees(champs=None):
    """Dimensions générées depuis le modèle, pour le groupement personnalisé.

    L'appelant qui a déjà la liste des champs la passe, pour ne pas la
    reconstruire.
    """
    from core.listing import dimensions_auto
    return dimensions_auto(champs or champs_patients(), exclure=CHAMPS_DEJA_GROUPABLES)


def listing_patients(aujourdhui=None):
    """Déclaration de la liste patients, et champs du constructeur de conditions.

    Déclarée ici plutôt que dans la vue parce que deux appelants en ont besoin :
    la page, et son export. Les laisser la rebâtir chacun de leur côté garantit
    qu'un jour l'un gagnera un filtre que l'autre ignorera — et le fichier
    téléchargé cesserait silencieusement de correspondre à l'écran.
    """
    from core.listing import Listing

    aujourdhui = aujourdhui or date.today()
    champs = champs_patients()
    declarees = construire_dimensions(aujourdhui)
    perso = dimensions_personnalisees(champs)
    listing = Listing(
        recherche=CHAMPS_RECHERCHE,
        # Le code et l'ancien identifiant d'une fiche fusionnée ramènent la
        # fiche gardée (voir `patients.resolution`) ; un numéro se retrouve
        # quelle que soit son écriture (voir `condition_telephone`).
        recherche_en_plus=condition_recherche_en_plus,
        familles=familles_patients(),
        dimensions=list(declarees.values()) + perso,
        par_page=100,
        tri_defaut=('nom', 'prenoms'),
    )
    return listing, champs, declarees, perso
