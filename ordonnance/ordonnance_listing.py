"""Déclaration de la liste des ordonnances pour la brique core.listing.

Cette page avait son propre menu écrit à la main dans le gabarit : onze liens
`<a href="?…">` dont chacun recomposait la chaîne de requête entière. Ajouter un
critère obligeait à reprendre les onze, et les valeurs d'une même famille
s'excluaient — choisir « Délivrée » effaçait « Expirée ». Elle rejoint ici la
mécanique commune aux autres modules, comme la liste des factures : on déclare
*quoi* filtrer, core.listing combine, compte et génère le menu.

Un mot sur la recherche. Une ordonnance tient son patient de deux endroits
selon la façon dont elle est née : par une consultation, elle le lit sur
`consultation.patient` et laisse `patient` vide ; saisie directement, c'est
l'inverse (voir `Ordonnance.patient_effectif`). L'ancienne recherche
n'interrogeait que le premier chemin : chercher le nom d'un patient ne ramenait
jamais ses ordonnances libres, sans rien dire.
"""

from datetime import date, datetime as dt, timedelta

from django.db.models import Q


#: Champs interrogés par la barre de recherche — les deux chemins du patient.
CHAMPS_RECHERCHE = (
    'numero',
    'consultation__patient__nom', 'consultation__patient__prenoms',
    'consultation__patient__code_patient',
    'patient__nom', 'patient__prenoms', 'patient__code_patient',
)


def _appliquer_periode(qs, codes, contexte):
    """Période d'émission : un intervalle explicite l'emporte sur les raccourcis.

    Même règle que la liste des factures, d'où cette fonction est reprise : un
    raccourci et un intervalle saisi à la main se contrediraient, et c'est la
    saisie la plus précise qui gagne.
    """
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        try:
            if date_from:
                qs = qs.filter(date_emission__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_emission__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_emission__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_emission__date__gte=aujourdhui - timedelta(days=7),
                         date_emission__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_emission__year=aujourdhui.year,
                         date_emission__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_emission__year=aujourdhui.year)
    return qs


#: La page s'ouvrait déjà sur les ordonnances du jour — la pharmacie travaille
#: sur la journée en cours. Le défaut est conservé, mais il se déclare ici au
#: lieu d'être un `else` au milieu de la vue.
FILTRES_DEFAUT = ('today',)


def libelle_periode(filtres, date_from='', date_to=''):
    """Mention discrète de la période affichée, à côté du titre."""
    if date_from and date_to:
        return f'du {date_from} au {date_to}'
    if date_from:
        return f'à partir du {date_from}'
    if date_to:
        return f"jusqu'au {date_to}"
    for code, libelle in (('today', "aujourd'hui"), ('semaine', '7 derniers jours'),
                          ('mois', 'mois en cours'), ('annee', 'année en cours')):
        if code in filtres:
            return libelle
    return 'toutes périodes'


def familles_ordonnances():
    """Familles de filtres de la liste des ordonnances."""
    from consultations.models import Ordonnance
    from core.listing import Famille

    return [
        Famille('periode', "Période d'émission", exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État', valeurs=[
            (f'statut_{code}', libelle, Q(statut=code))
            for code, libelle in Ordonnance.STATUT
        ]),
        Famille('type', 'Type', valeurs=[
            ('type_interne', 'Interne', Q(type_ordonnance='interne')),
            ('type_externe', 'Externe', Q(type_ordonnance='externe')),
        ]),
        # L'expiration se lit sur une date, pas sur le statut : une ordonnance
        # encore « Émise » peut avoir dépassé sa date sans que personne ne l'ait
        # repassée à « Expirée ». Les deux familles disent donc deux choses
        # différentes, et se cumulent.
        Famille('echeance', 'Échéance', valeurs=[
            ('ech_depassee', 'Date dépassée',
             Q(date_expiration__lt=date.today())),
            ('ech_valide', 'Encore valide',
             Q(date_expiration__gte=date.today())),
            ('ech_sans', 'Sans date', Q(date_expiration__isnull=True)),
        ]),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin',
             Q(patient__sexe='M') | Q(consultation__patient__sexe='M')),
            ('genre_F', 'Féminin',
             Q(patient__sexe='F') | Q(consultation__patient__sexe='F')),
        ]),
    ]


#: Colonnes triables : clé lisible dans l'URL -> champs du modèle. Le tri se
#: fait en base, sur toute la sélection et non sur les 25 lignes affichées.
TRIS = {
    'numero':  ('numero',),
    'date':    ('date_emission',),
    'statut':  ('statut',),
    'type':    ('type_ordonnance',),
    'expire':  ('date_expiration',),
}


def listing_ordonnances():
    """Déclaration de la liste des ordonnances.

    Sans dimension de regroupement : la page n'en propose pas, et en inventer
    pour faire nombre donnerait un menu « Regrouper par » que personne n'a
    demandé. `core.listing` les accepte vides.
    """
    from core.listing import Listing

    return Listing(
        recherche=CHAMPS_RECHERCHE,
        familles=familles_ordonnances(),
        par_page=25,
        filtres_defaut=FILTRES_DEFAUT,
        tri_defaut=('-date_emission',),
        tris=TRIS,
    )
