"""Déclaration du registre des naissances pour la brique core.listing.

Même rôle que patient_listing et rdv_listing : décrire *quoi* filtrer et
regrouper, le comment (menus, comptages réels, pagination par groupe, conditions
personnalisées) venant de core.listing. Le registre avait sa propre mécanique,
écrite à la main : filtres exclusifs, un seul regroupement à la fois, et des
liens qui perdaient les paramètres des autres menus. Il se comporte désormais
comme les listes de rendez-vous.

Les découpages de date et leurs libellés sont importés de rdv_listing : deux
copies finiraient par produire deux libellés de mois différents.
"""

from datetime import date, timedelta

from django.db.models import Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

# Libellés de date partagés avec les listes de rendez-vous : mêmes groupes
# « Mars 2026 » / « Semaine du 02/03/2026 » d'un module à l'autre.
from .rdv_listing import (_debut_semaine, _lib_jour, _lib_mois, _lib_semaine,
                          _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('numero', 'mere__nom', 'mere__prenoms', 'nom_enfant',
                    'prenoms_enfant', 'lieu_naissance')


# ── Filtres ─────────────────────────────────────────────────────────────────
# Une famille est appliquée en ET avec les autres ; ses valeurs se combinent en
# OU. « Vivant + Mort-né » donne les deux états, « Vivant + Césarienne » croise
# les deux critères.

def _appliquer_periode(qs, codes, contexte):
    """Période d'accouchement : un intervalle explicite l'emporte sur les raccourcis.

    Le registre s'ouvre sans restriction de période — on y cherche autant une
    naissance de l'an dernier que celle du matin — contrairement aux listes de
    rendez-vous qui s'ouvrent sur la journée.
    """
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_accouchement__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_accouchement__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_accouchement__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_accouchement__date__gte=aujourdhui - timedelta(days=7),
                         date_accouchement__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_accouchement__year=aujourdhui.year,
                         date_accouchement__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_accouchement__year=aujourdhui.year)
    return qs


#: Codes de la famille « Période », qui s'excluent mutuellement. Le script de la
#: page s'en sert pour remplacer la période retenue au lieu de l'ajouter.
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
    return ''


def familles_naissances():
    """Familles de filtres du registre des naissances."""
    from core.listing import Famille
    from .models import Naissance

    return [
        Famille('periode', "Période d'accouchement", exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",     Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',   Q()),
                    ('annee',   'Année en cours',  Q()),
                ]),
        Famille('etat', "État de l'enfant", valeurs=[
            (code, libelle, Q(statut=code)) for code, libelle in Naissance.STATUT
        ]),
        Famille('mode', "Mode d'accouchement", valeurs=[
            (f'mode_{code}', libelle, Q(mode_accouchement=code))
            for code, libelle in Naissance.MODE
        ]),
        Famille('sexe', "Sexe de l'enfant", valeurs=[
            ('sexe_M', 'Masculin', Q(sexe_enfant='M')),
            ('sexe_F', 'Féminin',  Q(sexe_enfant='F')),
        ]),
        Famille('dossier', 'Dossier', valeurs=[
            (f'dossier_{code}', libelle, Q(statut_dossier=code))
            for code, libelle in Naissance.STATUT_DOSSIER
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
SOUS_MENU_DATE = "Date d'accouchement"


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Naissance

    lib_mode = dict(Naissance.MODE)
    lib_statut = dict(Naissance.STATUT)
    lib_sexe = dict(Naissance.SEXE)
    # Le choix vide de la liste d'éducation porte le libellé « — » : écarté, pour
    # que le groupe des valeurs absentes s'annonce « Non précisé » comme ailleurs.
    lib_education = {code: libelle for code, libelle in Naissance.EDUCATION if code}
    lib_dossier = dict(Naissance.STATUT_DOSSIER)

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
            'annotate': {'g_annee': TruncYear('date_accouchement')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date_accouchement).year) if o.date_accouchement else 'Sans date',
            'order':  ('-date_accouchement',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_accouchement')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date_accouchement)),
            'order':  ('-date_accouchement',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_accouchement')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date_accouchement)),
            'order':  ('-date_accouchement',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_accouchement')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date_accouchement))),
            'order':  ('-date_accouchement',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_accouchement')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date_accouchement)),
            'order':  ('-date_accouchement',),
        }),
        ('cree_le', "Date d'enregistrement", None, {
            'annotate': {'g_cree': TruncDay('date_creation')},
            'values': ('g_cree',),
            'label':  lambda r: _lib_jour(_local(r['g_cree'])),
            'valeur': lambda o: _lib_jour(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('mere', 'Nom de la mère', None, {
            'values': ('mere__nom', 'mere__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['mere__nom'], r['mere__prenoms']), 'Sans mère'),
            'valeur': lambda o: _vide(_nom_complet(o.mere.nom, o.mere.prenoms) if o.mere_id else '', 'Sans mère'),
            'order':  ('mere__nom', 'mere__prenoms'),
        }),
        # Medecin.nom / .prenoms sont des propriétés déléguant à Employe : il faut
        # viser medecin__employe__* pour l'agrégation comme pour le tri.
        ('medecin', 'Médecin', None, {
            'values': ('medecin__employe__nom', 'medecin__employe__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['medecin__employe__nom'],
                                                   r['medecin__employe__prenoms']), 'Sans médecin'),
            'valeur': lambda o: _vide(_nom_complet(o.medecin.nom, o.medecin.prenoms) if o.medecin_id else '',
                                      'Sans médecin'),
            'order':  ('medecin__employe__nom', 'medecin__employe__prenoms'),
        }),
        ('mode', "Mode d'accouchement", None, choix('mode_accouchement', lib_mode)),
        ('statut', "État de l'enfant", None, choix('statut', lib_statut)),
        ('genre', "Sexe de l'enfant", None, choix('sexe_enfant', lib_sexe)),
        ('groupe_sanguin', 'Groupe sanguin', None, {
            'values': ('groupe_sanguin_enfant',),
            'label':  lambda r: _vide(r['groupe_sanguin_enfant'], 'Non précisé'),
            'valeur': lambda o: _vide(o.groupe_sanguin_enfant, 'Non précisé'),
            'order':  ('groupe_sanguin_enfant',),
        }),
        ('lieu', 'Lieu de naissance', None, {
            'values': ('lieu_naissance',),
            'label':  lambda r: _vide(r['lieu_naissance'], 'Non précisé'),
            'valeur': lambda o: _vide(o.lieu_naissance, 'Non précisé'),
            'order':  ('lieu_naissance',),
        }),
        ('parite', 'Parité', None, {
            'values': ('parite',),
            'label':  lambda r: f"Parité {r['parite']}" if r['parite'] is not None else 'Non précisée',
            'valeur': lambda o: f'Parité {o.parite}' if o.parite is not None else 'Non précisée',
            'order':  ('parite',),
        }),
        ('education', 'Éducation de la mère', None, choix('education_mere', lib_education)),
        ('dossier', 'Statut du dossier', None, choix('statut_dossier', lib_dossier)),
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}


# ── Filtre et regroupement personnalisés ────────────────────────────────────

#: Chemins traversant une relation : utiles mais non découvrables sans exposer
#: tout le schéma. Le second élément est le groupe sous lequel le champ est
#: présenté dans les menus.
CHAMPS_EXTRA = (
    ('mere__nom', 'Mère'),
    ('mere__prenoms', 'Mère'),
    ('mere__code_patient', 'Mère'),
    ('mere__sexe', 'Mère'),
    ('mere__telephone', 'Mère'),
    ('mere__date_naissance', 'Mère'),
    ('mere__groupe_sanguin', 'Mère'),
    ('mere__assurance', 'Mère'),
    ('medecin__employe__nom', 'Médecin'),
    ('medecin__employe__prenoms', 'Médecin'),
)

#: Champs déjà proposés en clair par le menu : inutile de les répéter dans
#: « Ajouter un groupement personnalisé ».
CHAMPS_DEJA_GROUPABLES = (
    'mere', 'medecin', 'mode_accouchement', 'statut', 'sexe_enfant',
    'groupe_sanguin_enfant', 'lieu_naissance', 'parite', 'education_mere',
    'statut_dossier',
)


def champs_naissances():
    """Champs proposés au filtre et au groupement personnalisés."""
    from core.listing import champs_filtrables
    from .models import Naissance
    return champs_filtrables(Naissance, extra=CHAMPS_EXTRA, groupe='Naissance')


def dimensions_personnalisees(champs=None):
    """Dimensions générées depuis les champs, pour le groupement personnalisé.

    L'appelant qui a déjà la liste des champs la passe : la construire interroge
    la base, autant ne pas le faire deux fois par requête.
    """
    from core.listing import dimensions_auto
    return dimensions_auto(champs or champs_naissances(), exclure=CHAMPS_DEJA_GROUPABLES)
