"""Filtrage et regroupement partagés des listes de rendez-vous.

Utilisé par `rdv_global_list` (module patients) et `core.views.gynecologie_rdv` : les
deux pages offrent exactement les mêmes menus « Filtres » et « Regrouper par »,
seule leur requête de départ diffère. Tout est ici pour éviter deux logiques qui
divergent.

Deux principes reprennent le pattern de la liste patients :

* **Filtres cumulables** : lus via `getlist('filter')`. À l'intérieur d'une même
  famille (état, type…) les valeurs se combinent en OU ; entre familles
  différentes, en ET. « Confirmé + Annulé » donne donc les deux états, alors que
  « Confirmé + Urgent » croise les deux critères.
* **Regroupements cumulables** : lus via `getlist('group')`, avec un compteur
  réel calculé en base (toutes pages confondues), pas seulement sur la page
  courante.

Le regroupement par diagnostic est le seul cas particulier : un rendez-vous peut
porter plusieurs pathologies, il apparaît donc dans plusieurs groupes. Les
compteurs de ces groupes ne s'additionnent alors pas au nombre total de
rendez-vous, ce qui est attendu.
"""

from collections import Counter, OrderedDict
from datetime import date

from django.db.models import Case, CharField, Count, Q, Value, When
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncWeek, TruncYear
from django.utils import timezone

from core.utils import annees_avant


# ── Filtres ─────────────────────────────────────────────────────────────────
# Chaque famille est appliquée en ET avec les autres ; les valeurs d'une même
# famille sont combinées en OU.

_FILTRES_TYPE = {
    'urgence_medicale': Q(type_rdv='urgence'),
    'consultation':     Q(type_rdv='consultation'),
    'suivi':            Q(type_rdv='controle'),
    'examen':           Q(type_rdv='examen'),
    'vaccination':      Q(type_rdv='vaccination'),
}

_FILTRES_ETAT = {
    'planifie':        Q(statut='planifie'),
    'confirme':        Q(statut='confirme'),
    'en_attente':      Q(statut='en_attente'),
    'en_consultation': Q(statut='en_consultation'),
    'termine':         Q(statut='termine'),
    'annule':          Q(statut='annule'),
    'absent':          Q(statut='absent'),
    'not_done':        ~Q(statut__in=['termine', 'annule', 'absent']),
}

_FILTRES_URGENCE = {
    'urgent':      Q(niveau_urgence='urgent'),
    'tres_urgent': Q(niveau_urgence='tres_urgent'),
}



#: Valeur explicite signifiant « aucune restriction de période ». Nécessaire
#: parce que l'absence de paramètre `filter` déclenche le défaut « aujourd'hui » :
#: sans ce marqueur, décocher « Aujourd'hui » ramènerait au défaut.
FILTRE_TOUTES_PERIODES = 'tous'

#: Filtre appliqué quand l'URL ne porte aucun paramètre `filter` : les listes de
#: rendez-vous s'ouvrent sur la journée en cours.
FILTRES_PAR_DEFAUT = ['today']




def libelle_periode(filtres, date_from='', date_to=''):
    """Libellé court de la période affichée, pour la mention à côté du titre.

    Sert uniquement d'information : la période retenue reste visible même quand
    elle vient du défaut, sans pour autant compter comme un filtre à effacer.
    """
    if date_from and date_to:
        return f'du {date_from} au {date_to}'
    if date_from:
        return f'à partir du {date_from}'
    if date_to:
        return f"jusqu'au {date_to}"
    if FILTRE_TOUTES_PERIODES in filtres:
        return 'toutes périodes'
    if 'semaine' in filtres:
        return '7 derniers jours'
    if 'today' in filtres:
        return "aujourd'hui"
    return ''




# Familles de filtres dont les valeurs viennent des tables de configuration : on
# ne peut pas les énumérer à l'avance, elles sont donc reconnues par préfixe.
# Ajouter un type de visite en configuration le rend filtrable immédiatement,
# sans toucher au code.
PREFIXE_VISITE_CPN = 'visite_'
PREFIXE_VISITE_CURATIVE = 'curatif_'



# ── Regroupements ───────────────────────────────────────────────────────────
# Pour chaque dimension :
#   values   : champs à passer à .values() pour l'agrégation en base
#   annotate : annotations nécessaires à ces champs (optionnel)
#   label    : construit le libellé depuis une ligne d'agrégation (dict)
#   cle      : construit le même libellé depuis une instance RendezVous
#   order    : tri à appliquer pour que les groupes soient cohérents
# `label` et `cle` doivent produire des chaînes identiques : c'est la clé qui
# relie un en-tête de groupe à son compteur calculé en base.

def _tranche_age(naissance, aujourdhui):
    if not naissance:
        return 'Âge inconnu'
    if naissance > annees_avant(aujourdhui, 18):
        return 'Mineurs (< 18 ans)'
    if naissance > annees_avant(aujourdhui, 60):
        return 'Adultes (18–60 ans)'
    return 'Seniors (> 60 ans)'


_MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
         'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


def _local(dt_value):
    """Date locale d'un datetime, pour coller aux troncatures faites en base."""
    if dt_value is None:
        return None
    if timezone.is_aware(dt_value):
        return timezone.localtime(dt_value).date()
    return dt_value.date() if hasattr(dt_value, 'date') else dt_value


def _vide(valeur, defaut):
    return valeur if valeur else defaut


#: Libellés des types de visite curative, indexés par code. Rempli à la demande.
_LIB_VISITE_CURATIVE = {}


def _type_visite_curative_libelle(rdv):
    """Libellé du type de visite curative d'un rendez-vous.

    Lit le code dans le registre curatif (`donnees` → `cur_type_visite`), qui est
    la valeur de référence — le formulaire l'écrit là et les rapports l'y lisent.
    Le code est traduit via la table de configuration ; s'il n'y correspond plus,
    on affiche le code brut plutôt que de faire disparaître la ligne.
    """
    if not _LIB_VISITE_CURATIVE:
        from .models import TypeVisiteCurative
        _LIB_VISITE_CURATIVE.update(dict(TypeVisiteCurative.objects.values_list('code', 'nom')))

    reg = getattr(rdv, 'registre_curatif', None)
    code = ((reg.donnees or {}).get('cur_type_visite') or '') if reg is not None else ''
    if not code and rdv.cur_type_visite_id:      # rendez-vous saisi sans registre
        return rdv.cur_type_visite.nom
    if not code:
        return 'Sans type de visite'
    return _LIB_VISITE_CURATIVE.get(code, code)


#: Libellés des dimensions dans le menu « Regrouper par ».
LIBELLES_DIMENSIONS = {
    'age': 'Age du patient', 'sexe': 'Sexe', 'type_rdv': 'Type de rendez-vous',
    'type_consultation': 'Type de consultation',
    'type_visite_cpn': 'Type de visite (CPN)',
    'type_visite_curative': 'Type de visite curative',
    'patient': 'Patient', 'medecin': 'Rendez-vous du docteur', 'statut': 'État',
    'departement': 'Département', 'assurance': "Compagnie d'assurance",
    'police': "Police d'assurance", 'diagnostic': 'Diagnostic retenu',
    'date_annee': 'Année', 'date_trimestre': 'Trimestre', 'date_mois': 'Mois',
    'date_semaine': 'Semaine', 'date_jour': 'Jour',
}

#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENUS_DIMENSIONS = {
    'date_annee': 'Date', 'date_trimestre': 'Date', 'date_mois': 'Date',
    'date_semaine': 'Date', 'date_jour': 'Date',
}


def construire_dimensions(aujourdhui):
    """Dimensions de regroupement, au format de la brique commune (core.listing).

    Les descriptions ci-dessous sont converties en objets `Dimension` : la clé du
    dictionnaire devient l'identifiant, `cle` la fonction qui calcule le libellé
    depuis un rendez-vous, et le reste passe tel quel.
    """
    from core.listing import Dimension

    # Indispensable : les libellés des champs à choix servent à la fois au
    # comptage SQL et au calcul depuis l'objet. S'ils ne sont pas résolus, les
    # deux chemins produisent des clés différentes (« absent » contre
    # « Absent ») et les lignes ne retrouvent plus leur groupe.
    _init_libelles()

    brut = OrderedDict([
        ('age', {
            'annotate': {'g_age': Case(
                When(patient__date_naissance__gt=annees_avant(aujourdhui, 18), then=Value('Mineurs (< 18 ans)')),
                When(patient__date_naissance__gt=annees_avant(aujourdhui, 60), then=Value('Adultes (18–60 ans)')),
                When(patient__date_naissance=None, then=Value('Âge inconnu')),
                default=Value('Seniors (> 60 ans)'), output_field=CharField(),
            )},
            'values': ('g_age',),
            'label':  lambda r: r['g_age'],
            'cle':    lambda o: _tranche_age(o.patient.date_naissance if o.patient else None, aujourdhui),
            'order':  ('-patient__date_naissance',),
        }),
        ('sexe', {
            'values': ('patient__sexe',),
            'label':  lambda r: {'F': 'Féminin', 'M': 'Masculin'}.get(r['patient__sexe'], 'Non précisé'),
            'cle':    lambda o: {'F': 'Féminin', 'M': 'Masculin'}.get(o.patient.sexe if o.patient else None, 'Non précisé'),
            'order':  ('patient__sexe',),
        }),
        ('type_rdv', {
            'values': ('type_rdv',),
            'label':  lambda r: _LIB_TYPE.get(r['type_rdv'], _vide(r['type_rdv'], 'Non précisé')),
            'cle':    lambda o: o.get_type_rdv_display() if o.type_rdv else 'Non précisé',
            'order':  ('type_rdv',),
        }),
        ('type_consultation', {
            'values': ('type_consultation__nom',),
            'label':  lambda r: _vide(r['type_consultation__nom'], 'Sans type de consultation'),
            'cle':    lambda o: o.type_consultation.nom if o.type_consultation else 'Sans type de consultation',
            'order':  ('type_consultation__nom',),
        }),
        # Type de visite de la gynécologie : les CPN définis en configuration.
        ('type_visite_cpn', {
            'values': ('cpn_type_visite__nom',),
            'label':  lambda r: _vide(r['cpn_type_visite__nom'], 'Sans type de visite'),
            'cle':    lambda o: o.cpn_type_visite.nom if o.cpn_type_visite else 'Sans type de visite',
            'order':  ('cpn_type_visite__nom',),
        }),
        # Type de visite curative (consultations) : la valeur de référence est le
        # code stocké dans le registre curatif, et non la clé étrangère — celle-ci
        # n'est renseignée que depuis la correction du formulaire, alors que le
        # JSON porte tout l'historique et alimente déjà les rapports. Pas de
        # `values` : aucune agrégation SQL n'est possible sur ce JSON, le comptage
        # passe donc par le parcours Python (cf. DIMS_PYTHON).
        ('type_visite_curative', {
            'cle':    _type_visite_curative_libelle,
            'order':  ('cur_type_visite__nom',),
            'filtre': lambda v: _filtre_visite_curative(v),
        }),
        ('patient', {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: f"{(r['patient__nom'] or '').upper()} {r['patient__prenoms'] or ''}".strip(),
            'cle':    lambda o: f"{(o.patient.nom or '').upper()} {o.patient.prenoms or ''}".strip() if o.patient else 'Sans patient',
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        # Medecin.nom / .prenoms sont des propriétés qui délèguent à Employe :
        # il faut viser medecin__employe__* pour l'agrégation comme pour le tri.
        ('medecin', {
            'values': ('medecin__employe__nom', 'medecin__employe__prenoms'),
            'label':  lambda r: _vide(f"{(r['medecin__employe__nom'] or '').upper()} {r['medecin__employe__prenoms'] or ''}".strip(), 'Sans médecin'),
            'cle':    lambda o: f"{(o.medecin.nom or '').upper()} {o.medecin.prenoms or ''}".strip() if o.medecin else 'Sans médecin',
            'order':  ('medecin__employe__nom', 'medecin__employe__prenoms'),
        }),
        ('statut', {
            'values': ('statut',),
            'label':  lambda r: _LIB_STATUT.get(r['statut'], _vide(r['statut'], 'Non précisé')),
            'cle':    lambda o: o.get_statut_display() if o.statut else 'Non précisé',
            'order':  ('statut',),
        }),
        ('departement', {
            'values': ('departement__nom',),
            'label':  lambda r: _vide(r['departement__nom'], 'Sans département'),
            'cle':    lambda o: o.departement.nom if o.departement else 'Sans département',
            'order':  ('departement__nom',),
        }),
        ('assurance', {
            'values': ('patient__assurance__nom',),
            'label':  lambda r: _vide(r['patient__assurance__nom'], 'Sans assurance'),
            'cle':    lambda o: o.patient.assurance.nom if (o.patient and o.patient.assurance) else 'Sans assurance',
            'order':  ('patient__assurance__nom',),
        }),
        ('police', {
            'values': ('patient__numero_assurance',),
            'label':  lambda r: _vide(r['patient__numero_assurance'], 'Sans police'),
            'cle':    lambda o: _vide(o.patient.numero_assurance if o.patient else '', 'Sans police'),
            'order':  ('patient__numero_assurance',),
        }),
        ('date_annee', {
            'annotate': {'g_annee': TruncYear('date_heure')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'cle':    lambda o: str(_local(o.date_heure).year) if o.date_heure else 'Sans date',
            'order':  ('-date_heure',),
        }),
        ('date_trimestre', {
            'annotate': {'g_trim': TruncQuarter('date_heure')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'cle':    lambda o: _lib_trimestre(_local(o.date_heure)),
            'order':  ('-date_heure',),
        }),
        ('date_mois', {
            'annotate': {'g_mois': TruncMonth('date_heure')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'cle':    lambda o: _lib_mois(_local(o.date_heure)),
            'order':  ('-date_heure',),
        }),
        ('date_semaine', {
            'annotate': {'g_sem': TruncWeek('date_heure')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit faire de
            # même, sinon les deux chemins produisent des libellés différents et
            # les lignes ne retrouvent pas leur groupe.
            'cle':    lambda o: _lib_semaine(_debut_semaine(_local(o.date_heure))),
            'order':  ('-date_heure',),
        }),
        ('date_jour', {
            'annotate': {'g_jour': TruncDay('date_heure')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'cle':    lambda o: _lib_jour(_local(o.date_heure)),
            'order':  ('-date_heure',),
        }),
    ])

    # Diagnostic : un rendez-vous peut porter plusieurs pathologies, la fonction
    # renvoie donc une liste de libellés — la brique sait qu'un objet appartenant
    # à plusieurs groupes doit apparaître dans chacun. Pas de `values` : la valeur
    # vit dans un JSONField, le comptage passe par un parcours Python.
    noms_pathologies = {}

    def _diagnostics(rdv):
        if not noms_pathologies:
            from .models import Pathologie
            noms_pathologies.update(dict(Pathologie.objects.values_list('pk', 'nom')))
        return _pathologies_de(rdv, noms_pathologies) or ['Sans diagnostic']

    brut['diagnostic'] = {'cle': _diagnostics,
                          'filtre': lambda v: _filtre_diagnostic(v)}

    dims = OrderedDict()
    for identifiant, d in brut.items():
        dims[identifiant] = Dimension(
            cle=identifiant,
            libelle=LIBELLES_DIMENSIONS.get(identifiant, identifiant),
            valeur=d['cle'],
            values=d.get('values', ()),
            annotate=d.get('annotate'),
            label=d.get('label'),
            order=d.get('order', ()),
            filtre=d.get('filtre'),
            sous_menu=SOUS_MENUS_DIMENSIONS.get(identifiant),
        )
    return dims


_LIB_TYPE = {}
_LIB_STATUT = {}


def _init_libelles():
    """Libellés lisibles des champs à choix, résolus une seule fois."""
    from .models import RendezVous
    if not _LIB_TYPE:
        _LIB_TYPE.update(dict(RendezVous._meta.get_field('type_rdv').choices or []))
    if not _LIB_STATUT:
        _LIB_STATUT.update(dict(RendezVous._meta.get_field('statut').choices or []))


def _lib_trimestre(d):
    return f'T{(d.month - 1) // 3 + 1} {d.year}' if d else 'Sans date'


def _lib_mois(d):
    return f'{_MOIS[d.month - 1].capitalize()} {d.year}' if d else 'Sans date'


def _debut_semaine(d):
    """Lundi de la semaine de `d`, pour coller à la troncature faite en base."""
    from datetime import timedelta
    return d - timedelta(days=d.weekday()) if d else None


def _lib_semaine(d):
    return f'Semaine du {d.strftime("%d/%m/%Y")}' if d else 'Sans date'


def _lib_jour(d):
    return d.strftime('%d/%m/%Y') if d else 'Sans date'


# Dimension à part : un rendez-vous peut relever de plusieurs pathologies.
DIM_DIAGNOSTIC = 'diagnostic'

# Entrées de menu laissées volontairement inactives faute de champ métier
# identifié (« But », « Docteur référent ») — à câbler quand le champ sera connu.
DIMS_NON_CABLEES = ('but', 'referent')


def _pathologies_de(rdv, noms_par_pk):
    """Libellés des pathologies d'un rendez-vous, depuis le JSON du registre."""
    reg = getattr(rdv, 'registre_curatif', None)
    if reg is None:
        return []
    brut = (reg.donnees or {}).get('cur_diagnostic', [])
    if isinstance(brut, str):
        brut = [brut] if brut else []
    noms = [noms_par_pk.get(int(v)) for v in brut if str(v).strip().isdigit()]
    return sorted(n for n in noms if n)


def annoter_diagnostics(lignes):
    """Pose `diagnostic_libelle` sur chaque ligne, en une seule requête.

    `RegistreCuratif.diagnostic_display` interroge `Pathologie` à chaque appel :
    affichée dans une colonne du tableau, cette propriété provoquait une requête
    par ligne. On résout ici tous les identifiants d'un coup.
    """
    from .models import Pathologie

    ids_par_rdv, tous_ids = {}, set()
    for rdv in lignes:
        reg = getattr(rdv, 'registre_curatif', None)
        brut = (reg.donnees or {}).get('cur_diagnostic', []) if reg is not None else []
        if isinstance(brut, str):
            brut = [brut] if brut else []
        ids = [int(v) for v in brut if str(v).strip().isdigit()]
        ids_par_rdv[rdv.pk] = ids
        tous_ids.update(ids)

    noms = dict(Pathologie.objects.filter(pk__in=tous_ids).values_list('pk', 'nom')) if tous_ids else {}
    for rdv in lignes:
        libelles = sorted(n for n in (noms.get(i) for i in ids_par_rdv.get(rdv.pk, [])) if n)
        rdv.diagnostic_libelle = ', '.join(libelles)
    return lignes


def trier_pour_groupes(qs, groupes, aujourdhui=None):
    """Trie la requête selon les dimensions retenues.

    Le regroupement lui-même (arbre imbriqué, compteurs, pagination par groupe)
    est assuré par la brique commune `core.listing` : ne reste ici que le tri, qui
    dépend des dimensions déclarées dans ce module.
    """
    if not groupes:
        return qs
    dims = construire_dimensions(aujourdhui or date.today())
    tri = []
    for g in groupes:
        dim = dims.get(g)
        if not dim:
            continue
        for champ in dim.order:
            if champ not in tri:
                tri.append(champ)
    return qs.order_by(*tri, '-date_heure') if tri else qs


# ── Familles de filtres au format de la brique commune ──────────────────────
# Déclarées ici, appliquées et affichées par core.listing : les menus sont
# générés depuis cette déclaration, il n'y a plus de gabarit à écrire à la main.

def _appliquer_periode(qs, codes, contexte):
    """Période : un intervalle de dates explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = contexte.get('date_from') or ''
    date_to = contexte.get('date_to') or ''
    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_heure__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_heure__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
        return qs
    if FILTRE_TOUTES_PERIODES in codes:
        return qs
    if 'today' in codes:
        return qs.filter(date_heure__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_heure__date__gte=aujourdhui - timezone.timedelta(days=7),
                         date_heure__date__lte=aujourdhui)
    return qs


def _appliquer_mes_rdv(qs, codes, contexte):
    """« Mes rendez-vous » dépend de l'utilisateur connecté, donc du contexte."""
    if 'mine' in codes and contexte.get('user'):
        return qs.filter(medecin__user=contexte['user'])
    return qs


def _appliquer_visite_curative(qs, codes, contexte):
    """Type de visite curative : la référence est le code du registre (JSON)."""
    if not codes:
        return qs
    combine = Q()
    for code in codes:
        combine |= Q(registre_curatif__donnees__cur_type_visite=code[len(PREFIXE_VISITE_CURATIVE):])
    return qs.filter(combine)


def _valeurs_visite_cpn():
    from gynecologie.models import TypeVisite
    return [(t.filtre_code, t.nom, Q(cpn_type_visite=t))
            for t in TypeVisite.objects.filter(actif=True).order_by('nom')]


def _valeurs_visite_curative():
    from .models import TypeVisiteCurative
    return [(t.filtre_code, t.nom, Q()) for t in
            TypeVisiteCurative.objects.filter(actif=True).order_by('nom')]


def familles_rdv(contexte_gyneco=False):
    """Familles de filtres d'une liste de rendez-vous.

    En gynécologie, le type de visite est celui des CPN définis en configuration ;
    ailleurs, ce sont les types de rendez-vous génériques et le type de visite
    curative. Les listes de types sont lues en base : un type ajouté en
    configuration devient filtrable sans toucher au code.
    """
    from core.listing import Famille

    familles = [
        Famille('periode', 'Période', exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
            ('today',                   "Aujourd'hui",         Q()),
            ('semaine',                 '7 derniers jours',    Q()),
            (FILTRE_TOUTES_PERIODES,    'Toutes les périodes', Q()),
        ]),
        Famille('mine', 'Mes rendez-vous', applique=_appliquer_mes_rdv,
                valeurs=[('mine', 'Mes rendez-vous', Q())]),
    ]
    if contexte_gyneco:
        familles.append(Famille('visite', 'Type de visite', source=_valeurs_visite_cpn))
    else:
        familles.append(Famille('type', 'Type de rendez-vous', valeurs=[
            ('consultation',      'Rendez-vous de consultation', _FILTRES_TYPE['consultation']),
            ('suivi',             'Suivi rendez-vous',           _FILTRES_TYPE['suivi']),
            ('urgence_medicale',  'Urgence médicale',            _FILTRES_TYPE['urgence_medicale']),
            ('examen',            'Examen',                      _FILTRES_TYPE['examen']),
            ('vaccination',       'Vaccination',                 _FILTRES_TYPE['vaccination']),
        ]))
        familles.append(Famille('curatif', 'Type de visite curative',
                                source=_valeurs_visite_curative,
                                applique=_appliquer_visite_curative))
    familles += [
        Famille('urgence', 'Urgence', valeurs=[
            ('urgent',      'Rendez-vous urgent', _FILTRES_URGENCE['urgent']),
            ('tres_urgent', 'Très urgent',        _FILTRES_URGENCE['tres_urgent']),
        ]),
        Famille('etat', 'État', valeurs=[
            ('not_done',        'Pas fini',        _FILTRES_ETAT['not_done']),
            ('planifie',        'Planifié',        _FILTRES_ETAT['planifie']),
            ('confirme',        'Confirmé',        _FILTRES_ETAT['confirme']),
            ('en_attente',      'En attente',      _FILTRES_ETAT['en_attente']),
            ('en_consultation', 'En consultation', _FILTRES_ETAT['en_consultation']),
            ('termine',         'Terminé',         _FILTRES_ETAT['termine']),
            ('annule',          'Annulé',          _FILTRES_ETAT['annule']),
            ('absent',          'Absent',          _FILTRES_ETAT['absent']),
        ]),
    ]
    return familles


#: Dimensions réservées à un contexte : les CPN n'ont de sens qu'en gynécologie,
#: le type de rendez-vous générique et le curatif qu'en dehors.
DIMENSIONS_GYNECO_SEULEMENT = ('type_visite_cpn',)
DIMENSIONS_HORS_GYNECO = ('type_rdv', 'type_visite_curative')


def dimensions_menu(contexte_gyneco, aujourdhui=None):
    """Dimensions proposées au menu, selon le module."""
    exclues = DIMENSIONS_HORS_GYNECO if contexte_gyneco else DIMENSIONS_GYNECO_SEULEMENT
    dims = construire_dimensions(aujourdhui or date.today())
    return [d for cle, d in dims.items() if cle not in exclues]


# ── Filtres ciblés des dimensions stockées en JSON ──────────────────────────
# Sans eux, regrouper par diagnostic ou par type de visite curative obligeait à
# parcourir toute la sélection pour charger les lignes des groupes affichés. Ces
# deux fonctions retraduisent les libellés de groupe en condition de requête.

def _filtre_visite_curative(valeurs_brutes):
    """Rendez-vous dont le registre porte l'un des types de visite donnés."""
    from .models import TypeVisiteCurative
    libelles = {t[0] for t in valeurs_brutes}
    codes = list(TypeVisiteCurative.objects
                 .filter(nom__in=libelles).values_list('code', flat=True))

    condition = Q(registre_curatif__donnees__cur_type_visite__in=codes) if codes else Q()
    if 'Sans type de visite' in libelles:
        # Ni registre du tout, ni valeur renseignée dedans.
        condition |= (Q(registre_curatif__isnull=True)
                      | Q(registre_curatif__donnees__cur_type_visite__isnull=True)
                      | Q(registre_curatif__donnees__cur_type_visite=''))
    return condition if codes or 'Sans type de visite' in libelles else Q(pk__in=[])


def _filtre_diagnostic(valeurs_brutes):
    """Rendez-vous portant l'une des pathologies données.

    SQLite ne sait pas tester l'appartenance à un tableau JSON : on parcourt donc
    la table des registres — petite et sans jointure — pour en tirer les
    identifiants, plutôt que toute la sélection de rendez-vous.
    """
    from .models import Pathologie, RegistreCuratif
    libelles = {t[0] for t in valeurs_brutes}
    sans = 'Sans diagnostic' in libelles
    pks = {str(p) for p in Pathologie.objects
           .filter(nom__in=libelles).values_list('pk', flat=True)}

    retenus = []
    for reg in RegistreCuratif.objects.values('rdv_id', 'donnees'):
        brut = (reg['donnees'] or {}).get('cur_diagnostic', [])
        if isinstance(brut, str):
            brut = [brut] if brut else []
        codes = {str(v) for v in brut if str(v).strip().isdigit()}
        if (codes & pks) or (sans and not codes):
            retenus.append(reg['rdv_id'])

    condition = Q(pk__in=retenus)
    if sans:
        condition |= Q(registre_curatif__isnull=True)
    return condition


#: Chemins traversant une relation, utiles au filtrage personnalisé mais non
#: découvrables sans exposer tout le schéma. Le second élément est le groupe sous
#: lequel le champ est présenté.
CHAMPS_EXTRA = (
    ('patient__nom', 'Patient'),
    ('patient__prenoms', 'Patient'),
    ('patient__code_patient', 'Patient'),
    ('patient__sexe', 'Patient'),
    ('patient__telephone', 'Patient'),
    ('patient__date_naissance', 'Patient'),
)

#: Champs déjà couverts par une dimension déclarée : inutile de les proposer une
#: seconde fois dans « Ajouter un groupement personnalisé ».
CHAMPS_DEJA_GROUPABLES = (
    'statut', 'type_rdv', 'departement', 'patient', 'medecin',
    'type_consultation', 'cpn_type_visite', 'cur_type_visite', 'patient__sexe',
)


def champs_rdv():
    """Champs proposés au filtrage et au regroupement personnalisés.

    Les colonnes du modèle ne sont que la moitié du formulaire : tout ce qui est
    saisi dans les onglets CPN, accouchement, post-natale et curatif part dans le
    JSON d'un registre, sans colonne dédiée. Ces champs sont donc déclarés à part
    (cf. rdv_champs_registres) et ajoutés ici — sans quoi les menus ne
    proposeraient rien de ce que contiennent ces onglets.
    """
    from core.listing import champs_filtrables

    from .models import RendezVous
    from .rdv_champs_registres import champs_registres
    return (champs_filtrables(RendezVous, extra=CHAMPS_EXTRA, groupe='Rendez-vous')
            + champs_registres())


def dimensions_personnalisees(champs=None):
    """Dimensions générées pour « Ajouter un groupement personnalisé ».

    L'appelant qui a déjà la liste des champs la passe : la construire interroge
    la base, autant ne pas le faire deux fois par requête.
    """
    from core.listing import dimensions_auto
    return dimensions_auto(champs or champs_rdv(), exclure=CHAMPS_DEJA_GROUPABLES)
