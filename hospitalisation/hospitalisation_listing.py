"""Déclaration de la liste des hospitalisations pour la brique core.listing.

Même rôle que soin_listing ou rdv_listing : décrire *quoi* filtrer et regrouper,
le comment venant de core.listing — cumul des valeurs d'une famille en OU,
croisement des familles en ET, comptages calculés en base, regroupement
imbriqué.

Attention au cloisonnement : Hospitalisation n'est pas un ModeleCentre, c'est la
vue qui restreint au centre actif en passant par le patient. Cette déclaration
ne s'en occupe pas.
"""

from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('numero', 'patient__nom', 'patient__prenoms',
                    'patient__code_patient', 'motif_admission',
                    'nom_parent_gardien', 'chambre__nom', 'chambre__salle_no')


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période d'admission : un intervalle explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_admission__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_admission__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_admission__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_admission__date__gte=aujourdhui - timedelta(days=7),
                         date_admission__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_admission__year=aujourdhui.year,
                         date_admission__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_admission__year=aujourdhui.year)
    return qs


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')

#: La liste s'ouvrait déjà sur la journée : comportement conservé.
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


def _chambres():
    """Chambres réellement occupées par un dossier, lues en base."""
    from .models import Hospitalisation
    lignes = (Hospitalisation.objects.exclude(chambre=None)
              .values_list('chambre_id', 'chambre__nom', 'chambre__salle_no')
              .order_by('chambre__salle_no').distinct())
    return [(f'ch_{pk}', nom or f'Salle {salle}', Q(chambre_id=pk))
            for pk, nom, salle in lignes]


def familles_hospitalisations():
    """Familles de filtres de la liste des hospitalisations."""
    from core.listing import Famille
    from .models import Hospitalisation

    return [
        Famille('periode', "Période d'admission", exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État du dossier', valeurs=[
            (code, libelle, Q(statut=code)) for code, libelle in Hospitalisation.STATUT
        ]),
        Famille('hebergement', 'Hébergement', valeurs=[
            ('chambre_oui', 'Chambre attribuée', Q(chambre__isnull=False)),
            ('chambre_non', 'Sans chambre',      Q(chambre__isnull=True)),
        ]),
        Famille('chambre', 'Chambre', source=_chambres),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin', Q(patient__sexe='M')),
            ('genre_F', 'Féminin',  Q(patient__sexe='F')),
        ]),
        Famille('particularite', 'Particularité', valeurs=[
            ('cas_legal',  'Cas légal',            Q(cas_legal=True)),
            ('police',     'Signalé à la police',  Q(signale_police='oui')),
            ('reference',  'Référé ailleurs',      ~Q(etablissement_destination='')),
        ]),
        Famille('sejour', 'Séjour', valeurs=[
            ('entre',     'Entré',     Q(heure_entree__isnull=False)),
            ('non_entre', 'Pas encore entré', Q(heure_entree__isnull=True)),
            ('sorti',     'Sorti',     Q(heure_sortie__isnull=False)),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def _nom_complet(nom, prenoms):
    return f"{(nom or '').upper()} {prenoms or ''}".strip()


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = "Date d'admission"


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Hospitalisation

    lib_statut = dict(Hospitalisation.STATUT)

    brut = [
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date_admission')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date_admission).year) if o.date_admission else 'Sans date',
            'order':  ('-date_admission',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_admission')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date_admission)),
            'order':  ('-date_admission',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_admission')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date_admission)),
            'order':  ('-date_admission',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_admission')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date_admission))),
            'order':  ('-date_admission',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_admission')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date_admission)),
            'order':  ('-date_admission',),
        }),
        ('patient', 'Patient', None, {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['patient__nom'], r['patient__prenoms']), 'Sans patient'),
            'valeur': lambda o: _vide(_nom_complet(o.patient.nom, o.patient.prenoms) if o.patient_id else '',
                                      'Sans patient'),
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        # Medecin.nom / .prenoms sont des propriétés déléguant à Employe : il faut
        # viser medecin_traitant__employe__* pour l'agrégation comme pour le tri.
        ('medecin', 'Médecin traitant', None, {
            'values': ('medecin_traitant__employe__nom', 'medecin_traitant__employe__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['medecin_traitant__employe__nom'],
                                                   r['medecin_traitant__employe__prenoms']), 'Sans médecin'),
            'valeur': lambda o: _vide(_nom_complet(o.medecin_traitant.nom, o.medecin_traitant.prenoms)
                                      if o.medecin_traitant_id else '', 'Sans médecin'),
            'order':  ('medecin_traitant__employe__nom', 'medecin_traitant__employe__prenoms'),
        }),
        ('chambre', 'Chambre', None, {
            'values': ('chambre__nom', 'chambre__salle_no'),
            'label':  lambda r: _vide(r['chambre__nom'] or r['chambre__salle_no'], 'Sans chambre'),
            'valeur': lambda o: _vide((o.chambre.nom or o.chambre.salle_no) if o.chambre_id else '',
                                      'Sans chambre'),
            'order':  ('chambre__salle_no',),
        }),
        ('statut', 'État du dossier', None, {
            'values': ('statut',),
            'label':  lambda r: lib_statut.get(r['statut']) or 'Non précisé',
            'valeur': lambda o: lib_statut.get(o.statut) or 'Non précisé',
            'order':  ('statut',),
        }),
        ('genre', 'Genre du patient', None, {
            'values': ('patient__sexe',),
            'label':  lambda r: {'M': 'Masculin', 'F': 'Féminin'}.get(r['patient__sexe'], 'Non précisé'),
            'valeur': lambda o: {'M': 'Masculin', 'F': 'Féminin'}.get(o.patient.sexe, 'Non précisé'),
            'order':  ('patient__sexe',),
        }),
        ('maladie', 'Maladie', None, {
            'values': ('maladie__nom',),
            'label':  lambda r: _vide(r['maladie__nom'], 'Non précisée'),
            'valeur': lambda o: _vide(o.maladie.nom if o.maladie_id else '', 'Non précisée'),
            'order':  ('maladie__nom',),
        }),
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}
