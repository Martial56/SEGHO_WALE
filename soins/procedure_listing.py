"""Déclaration de la liste des soins (procédures) pour la brique core.listing.

Pendant de soin_listing pour ProcedureSoin. Même principe : on décrit *quoi*
filtrer et regrouper, core.listing s'occupe du reste — cumul des valeurs d'une
famille en OU, croisement des familles en ET, comptages calculés en base et
regroupement imbriqué.

La période porte ici sur `date`, la date de réalisation de l'acte, et non sur la
date d'enregistrement : c'est celle qu'on lit dans le tableau et celle sur
laquelle on raisonne quand on cherche « les soins de mardi ».
"""

from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('numero', 'patient__nom', 'patient__prenoms',
                    'patient__code_patient', 'infirmier__nom', 'infirmier__prenoms',
                    'soin_type__nom', 'maladie__nom')


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période de réalisation : un intervalle explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date__date__gte=aujourdhui - timedelta(days=7),
                         date__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date__year=aujourdhui.year, date__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date__year=aujourdhui.year)
    return qs


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')

#: Cette liste s'ouvre sans restriction de période, contrairement aux soins
#: infirmiers : on y consulte l'historique des actes autant que la journée.
FILTRES_DEFAUT = ()


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


def _departements():
    """Départements réellement portés par une procédure, lus en base."""
    from .models import ProcedureSoin
    lignes = (ProcedureSoin.objects.exclude(departement=None)
              .values_list('departement_id', 'departement__nom')
              .order_by('departement__nom').distinct())
    return [(f'dep_{pk}', nom, Q(departement_id=pk)) for pk, nom in lignes]


def _types_de_soin():
    """Types de soin effectivement pratiqués, lus en base.

    La configuration en compte bien plus que ceux qui servent : n'exposer que
    les seconds garde le menu utilisable.
    """
    from .models import ProcedureSoin
    lignes = (ProcedureSoin.objects.exclude(soin_type=None)
              .values_list('soin_type_id', 'soin_type__nom')
              .order_by('soin_type__nom').distinct())
    return [(f'type_{pk}', nom, Q(soin_type_id=pk)) for pk, nom in lignes]


def familles_procedures():
    """Familles de filtres de la liste des soins."""
    from core.listing import Famille
    from .models import ProcedureSoin

    return [
        Famille('periode', 'Période de réalisation', exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État', valeurs=[
            (code, libelle, Q(statut=code)) for code, libelle in ProcedureSoin.STATUT
        ]),
        Famille('type', 'Type de soin', source=_types_de_soin),
        Famille('departement', 'Département', source=_departements),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin', Q(patient__sexe='M')),
            ('genre_F', 'Féminin',  Q(patient__sexe='F')),
        ]),
        Famille('facturation', 'Facturation', valeurs=[
            ('facture_oui',  'Facturé',        Q(facture__isnull=False)),
            ('facture_non',  'Non facturé',    Q(facture__isnull=True)),
            ('facture_payee', 'Facture payée', Q(facture__statut='payee')),
        ]),
        Famille('rattachement', 'Rattachement', valeurs=[
            ('soin_oui', 'Rattaché à une fiche de soin', Q(soin__isnull=False)),
            ('soin_non', 'Acte isolé',                   Q(soin__isnull=True)),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def _nom_complet(nom, prenoms):
    return f"{(nom or '').upper()} {prenoms or ''}".strip()


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = 'Date de réalisation'


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import ProcedureSoin

    lib_statut = dict(ProcedureSoin.STATUT)

    brut = [
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date).year) if o.date else 'Sans date',
            'order':  ('-date',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date)),
            'order':  ('-date',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date)),
            'order':  ('-date',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date))),
            'order':  ('-date',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date)),
            'order':  ('-date',),
        }),
        ('patient', 'Patient', None, {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['patient__nom'], r['patient__prenoms']), 'Sans patient'),
            'valeur': lambda o: _vide(_nom_complet(o.patient.nom, o.patient.prenoms) if o.patient_id else '',
                                      'Sans patient'),
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        ('infirmier', 'Infirmier', None, {
            'values': ('infirmier__nom', 'infirmier__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['infirmier__nom'], r['infirmier__prenoms']),
                                      'Sans infirmier'),
            'valeur': lambda o: _vide(_nom_complet(o.infirmier.nom, o.infirmier.prenoms) if o.infirmier_id else '',
                                      'Sans infirmier'),
            'order':  ('infirmier__nom', 'infirmier__prenoms'),
        }),
        ('soin_type', 'Type de soin', None, {
            'values': ('soin_type__nom',),
            'label':  lambda r: _vide(r['soin_type__nom'], 'Non précisé'),
            'valeur': lambda o: _vide(o.soin_type.nom if o.soin_type_id else '', 'Non précisé'),
            'order':  ('soin_type__nom',),
        }),
        ('departement', 'Département', None, {
            'values': ('departement__nom',),
            'label':  lambda r: _vide(r['departement__nom'], 'Sans département'),
            'valeur': lambda o: _vide(o.departement.nom if o.departement_id else '', 'Sans département'),
            'order':  ('departement__nom',),
        }),
        ('maladie', 'Maladie', None, {
            'values': ('maladie__nom',),
            'label':  lambda r: _vide(r['maladie__nom'], 'Non précisée'),
            'valeur': lambda o: _vide(o.maladie.nom if o.maladie_id else '', 'Non précisée'),
            'order':  ('maladie__nom',),
        }),
        ('statut', 'État', None, {
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


#: Colonnes triables (voir soin_listing.TRIS).
TRIS = {
    'numero':      ('numero',),
    'patient':     ('patient__nom', 'patient__prenoms'),
    'soin_type':   ('soin_type__nom',),
    'infirmier':   ('infirmier__nom', 'infirmier__prenoms'),
    'departement': ('departement__nom',),
    'date':        ('date',),
    'prix':        ('prix',),
    'statut':      ('statut',),
}
