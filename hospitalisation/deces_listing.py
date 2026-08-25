"""Déclaration du registre des décès pour la brique core.listing.

La période porte sur `date_deces`, le fait constaté, et non sur `cree_le` : on
cherche « les décès de mars », pas les fiches saisies en mars. Le registre
s'ouvre sans restriction de période — on y consulte l'historique autant que la
journée.
"""

from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('code', 'patient__nom', 'patient__prenoms',
                    'patient__code_patient', 'raison_deces', 'remarques')

#: Aucune restriction au premier affichage.
FILTRES_DEFAUT = ()


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période de décès : un intervalle explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_deces__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_deces__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_deces=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_deces__gte=aujourdhui - timedelta(days=7),
                         date_deces__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_deces__year=aujourdhui.year,
                         date_deces__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_deces__year=aujourdhui.year)
    return qs


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')


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


def familles_deces():
    """Familles de filtres du registre des décès."""
    from core.listing import Famille
    from .models import RegistreDeces

    return [
        Famille('periode', 'Période de décès', exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État de la fiche', valeurs=[
            (code, libelle, Q(statut=code)) for code, libelle in RegistreDeces.STATUT
        ]),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin', Q(patient__sexe='M')),
            ('genre_F', 'Féminin',  Q(patient__sexe='F')),
        ]),
        Famille('contexte', 'Contexte', valeurs=[
            ('hosp_oui', "Survenu en hospitalisation", Q(hospitalisation__isnull=False)),
            ('hosp_non', 'Hors hospitalisation',       Q(hospitalisation__isnull=True)),
        ]),
        Famille('constat', 'Constat', valeurs=[
            ('medecin_oui', 'Médecin renseigné', Q(medecin__isnull=False)),
            ('medecin_non', 'Sans médecin',      Q(medecin__isnull=True)),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def _nom_complet(nom, prenoms):
    return f"{(nom or '').upper()} {prenoms or ''}".strip()


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = 'Date de décès'


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import RegistreDeces

    lib_statut = dict(RegistreDeces.STATUT)

    brut = [
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date_deces')},
            'values': ('g_annee',),
            'label':  lambda r: str(r['g_annee'].year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(o.date_deces.year) if o.date_deces else 'Sans date',
            'order':  ('-date_deces',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_deces')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(r['g_trim']),
            'valeur': lambda o: _lib_trimestre(o.date_deces),
            'order':  ('-date_deces',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_deces')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(r['g_mois']),
            'valeur': lambda o: _lib_mois(o.date_deces),
            'order':  ('-date_deces',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_deces')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(r['g_sem']),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(o.date_deces)),
            'order':  ('-date_deces',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_deces')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(r['g_jour']),
            'valeur': lambda o: _lib_jour(o.date_deces),
            'order':  ('-date_deces',),
        }),
        ('patient', 'Patient', None, {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['patient__nom'], r['patient__prenoms']), 'Sans patient'),
            'valeur': lambda o: _vide(_nom_complet(o.patient.nom, o.patient.prenoms) if o.patient_id else '',
                                      'Sans patient'),
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        # Medecin.nom / .prenoms délèguent à Employe : viser medecin__employe__*
        # pour l'agrégation comme pour le tri.
        ('medecin', 'Médecin', None, {
            'values': ('medecin__employe__nom', 'medecin__employe__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['medecin__employe__nom'],
                                                   r['medecin__employe__prenoms']), 'Sans médecin'),
            'valeur': lambda o: _vide(_nom_complet(o.medecin.nom, o.medecin.prenoms) if o.medecin_id else '',
                                      'Sans médecin'),
            'order':  ('medecin__employe__nom', 'medecin__employe__prenoms'),
        }),
        ('statut', 'État de la fiche', None, {
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
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}
