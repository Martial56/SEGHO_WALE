"""Déclaration de la liste des soins infirmiers pour la brique core.listing.

Même rôle que patient_listing, rdv_listing ou naissance_listing : décrire *quoi*
filtrer et regrouper, le comment — combinaison des filtres, comptages réels,
arbre de groupes, pagination par groupe, génération des menus — venant de
core.listing.

La liste avait sa propre mécanique : un statut à la fois, une période à la fois,
et des liens qui perdaient les paramètres des autres menus. Elle se comporte
désormais comme les listes de rendez-vous et le registre des naissances — les
valeurs d'une même famille se cumulent en OU, les familles se croisent en ET.

Les découpages de date et leurs libellés viennent de rdv_listing : deux copies
finiraient par produire deux libellés de mois différents d'un module à l'autre.
"""

from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
#: Pas de traversée vers les procédures : la jointure multiplierait les lignes
#: d'un soin qui en compte plusieurs.
CHAMPS_RECHERCHE = ('numero', 'nom', 'motif', 'patient__nom', 'patient__prenoms',
                    'patient__code_patient', 'infirmier__nom', 'infirmier__prenoms')


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période d'enregistrement : un intervalle explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_creation__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_creation__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_creation__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_creation__date__gte=aujourdhui - timedelta(days=7),
                         date_creation__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_creation__year=aujourdhui.year,
                         date_creation__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_creation__year=aujourdhui.year)
    return qs


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')

#: Sélection au premier affichage : la journée en cours, comme les listes de
#: rendez-vous. « Effacer » n'apparaît que si l'on s'en écarte.
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


def _departements():
    """Départements réellement portés par un soin.

    Lu en base : un département ajouté en configuration devient filtrable sans
    toucher au code, et on n'encombre pas le menu de ceux qui ne servent pas.
    """
    from .models import Soin
    lignes = (Soin.objects.exclude(departement=None)
              .values_list('departement_id', 'departement__nom')
              .order_by('departement__nom').distinct())
    return [(f'dep_{pk}', nom, Q(departement_id=pk)) for pk, nom in lignes]


def familles_soins():
    """Familles de filtres de la liste des soins infirmiers."""
    from core.listing import Famille
    from .models import Soin

    return [
        Famille('periode', "Période d'enregistrement", exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État du soin', valeurs=[
            (code, libelle, Q(statut=code)) for code, libelle in Soin.STATUT
        ]),
        Famille('severite', 'Sévérité', valeurs=[
            (f'sev_{code}', libelle, Q(severite=code))
            for code, libelle in Soin.SEVERITE if code
        ]),
        Famille('maladie', 'Statut de la maladie', valeurs=[
            (f'mal_{code}', libelle, Q(statut_maladie=code))
            for code, libelle in Soin.STATUT_MALADIE if code
        ]),
        Famille('departement', 'Département', source=_departements),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin', Q(patient__sexe='M')),
            ('genre_F', 'Féminin',  Q(patient__sexe='F')),
        ]),
        Famille('particularite', 'Particularité', valeurs=[
            ('infectieuse', 'Maladie infectieuse',      Q(maladie_infectieuse=True)),
            ('allergique',  'Maladie allergique',       Q(maladie_allergique=True)),
            ('lactation',   'Lactation',                Q(lactation=True)),
            ('grossesse',   'Avertissement grossesse',  Q(avertissement_grossesse=True)),
        ]),
        Famille('facturation', 'Facturation', valeurs=[
            ('facture_oui', 'Facturé',     Q(facture__isnull=False)),
            ('facture_non', 'Non facturé', Q(facture__isnull=True)),
        ]),
        Famille('origine', 'Origine', valeurs=[
            ('hosp_oui', "Issu d'une hospitalisation", Q(hospitalisation__isnull=False)),
            ('hosp_non', 'Soin externe',               Q(hospitalisation__isnull=True)),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────
# `valeur(objet)` et `label(ligne agrégée)` doivent produire exactement le même
# libellé : c'est la clé qui relie un en-tête de groupe à son compteur calculé en
# base. Deux libellés différents et le groupe s'affiche avec son compte mais
# reste vide au dépliage.

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def _nom_complet(nom, prenoms):
    return f"{(nom or '').upper()} {prenoms or ''}".strip()


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = "Date d'enregistrement"


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Soin

    lib_statut = dict(Soin.STATUT)
    # Le choix vide porte le libellé « — » : écarté, pour que le groupe des
    # valeurs absentes s'annonce « Non précisé » comme ailleurs.
    lib_severite = {code: libelle for code, libelle in Soin.SEVERITE if code}
    lib_maladie = {code: libelle for code, libelle in Soin.STATUT_MALADIE if code}

    def choix(champ, libelles, defaut='Non précisé'):
        """Dimension d'un champ à choix : le code est traduit des deux côtés."""
        return {
            'values': (champ,),
            'label':  lambda r: libelles.get(r[champ]) or defaut,
            'valeur': lambda o: libelles.get(getattr(o, champ)) or defaut,
            'order':  (champ,),
        }

    brut = [
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date_creation')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date_creation).year) if o.date_creation else 'Sans date',
            'order':  ('-date_creation',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_creation')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_creation')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_creation')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date_creation))),
            'order':  ('-date_creation',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_creation')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('patient', 'Patient', None, {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['patient__nom'], r['patient__prenoms']), 'Sans patient'),
            'valeur': lambda o: _vide(_nom_complet(o.patient.nom, o.patient.prenoms) if o.patient_id else '',
                                      'Sans patient'),
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        ('infirmier', 'Infirmier responsable', None, {
            'values': ('infirmier__nom', 'infirmier__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['infirmier__nom'], r['infirmier__prenoms']),
                                      'Sans infirmier'),
            'valeur': lambda o: _vide(_nom_complet(o.infirmier.nom, o.infirmier.prenoms) if o.infirmier_id else '',
                                      'Sans infirmier'),
            'order':  ('infirmier__nom', 'infirmier__prenoms'),
        }),
        ('departement', 'Département', None, {
            'values': ('departement__nom',),
            'label':  lambda r: _vide(r['departement__nom'], 'Sans département'),
            'valeur': lambda o: _vide(o.departement.nom if o.departement_id else '', 'Sans département'),
            'order':  ('departement__nom',),
        }),
        ('statut', 'État du soin', None, choix('statut', lib_statut)),
        ('severite', 'Sévérité', None, choix('severite', lib_severite)),
        ('maladie', 'Statut de la maladie', None, choix('statut_maladie', lib_maladie)),
        ('genre', 'Genre du patient', None, {
            'values': ('patient__sexe',),
            'label':  lambda r: {'M': 'Masculin', 'F': 'Féminin'}.get(r['patient__sexe'], 'Non précisé'),
            'valeur': lambda o: {'M': 'Masculin', 'F': 'Féminin'}.get(o.patient.sexe, 'Non précisé'),
            'order':  ('patient__sexe',),
        }),
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}


#: Colonnes triables de la liste : clé lue dans l'URL -> champs du modèle.
#: Le tri porte sur la totalité du résultat filtré, pas sur la page affichée.
#: `Medecin`/`Employe` exposent `nom` en propriété : le tri vise la table.
TRIS = {
    'numero':   ('numero',),
    'patient':  ('patient__nom', 'patient__prenoms'),
    'date':     ('date_creation',),
    'sexe':     ('patient__sexe',),
    'age':      ('patient__date_naissance',),
    'statut':   ('statut',),
    'severite': ('severite',),
}
