"""Déclaration de la liste des factures pour la brique core.listing.

Cette page avait son propre menu de filtres écrit à la main dans le gabarit :
trois critères, un seul niveau, aucun regroupement, et des compteurs qui ne
savaient rien dire d'autre que le total. Elle rejoint ici la mécanique commune
aux autres modules — on déclare *quoi* filtrer et *quoi* regrouper, core.listing
fait le reste.

Deux familles parlent du contenu de la facture, et il ne faut pas les confondre :

* **Type de facture** interroge `type_facture`, la nature déduite et enregistrée.
  Une facture qui mêle plusieurs natures y répond « Mixte », et à rien d'autre.
* **Contient des actes de** interroge les lignes. La même facture mixte y répond
  à *chacune* des natures qu'elle contient. C'est la famille qui sert à retrouver
  « tout ce qui touche au laboratoire », maintenant que la colonne Type a quitté
  le tableau.

Les familles qui passent par les paiements (caisse, mode de règlement) sont
écrites en sous-requête `pk__in` et non en jointure : une facture réglée en deux
fois sortirait deux fois d'une jointure, et core.listing n'appelle jamais
`distinct()` — ses compteurs verraient double.
"""

from datetime import date, datetime as dt, timedelta

from django.db.models import F, Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('numero', 'patient__nom', 'patient__prenoms',
                    'patient__code_patient')

#: Libellé du groupe des factures qu'aucun encaissement n'a touchées.
SANS_CAISSE = 'Non encaissée'


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période d'émission : un intervalle explicite l'emporte sur les raccourcis."""
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


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')

#: La liste s'ouvrait déjà sur les factures du jour : la caisse travaille sur la
#: journée en cours, et charger tout l'historique à l'arrivée n'aide personne.
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


def _natures_contenues():
    """Natures qu'une facture peut contenir, lues sur ses lignes.

    La condition passe par les lignes et non par `type_facture` : une facture
    mixte doit répondre à chacune des natures qu'elle porte, sans quoi une
    consultation facturée avec une radio deviendrait introuvable sous
    « Consultation ».
    """
    from .models import CATEGORIE_VERS_TYPE, Facture, LigneFacture

    libelles = dict(Facture.TYPE)
    valeurs = []
    for code, _ in Facture.TYPE:
        categories = sorted(cat for cat, nature in CATEGORIE_VERS_TYPE.items()
                            if nature == code)
        if not categories:
            continue               # « Mixte » et « Autre » ne sont pas des natures d'acte
        valeurs.append((
            f'contient_{code}', libelles[code],
            Q(pk__in=LigneFacture.objects
              .filter(article__categorie__code__in=categories)
              .values('facture_id')),
        ))
    return valeurs


def _caisses():
    """Caisses actives, plus les factures qu'aucun encaissement n'a touchées."""
    from .models import Caisse, Paiement

    valeurs = [
        (f'caisse_{caisse.pk}', caisse.nom,
         Q(pk__in=Paiement.objects.filter(caisse_id=caisse.pk).values('facture_id')))
        for caisse in Caisse.objects.filter(actif=True).order_by('nom')
    ]
    valeurs.append((
        'caisse_aucune', SANS_CAISSE,
        ~Q(pk__in=Paiement.objects.filter(caisse__isnull=False).values('facture_id')),
    ))
    return valeurs


def _modes_de_paiement():
    """Modes par lesquels une facture a effectivement été réglée."""
    from .models import Paiement

    return [
        (f'mode_{code}', libelle,
         Q(pk__in=Paiement.objects.filter(mode_paiement=code).values('facture_id')))
        for code, libelle in Paiement.MODE
    ]


def familles_factures():
    """Familles de filtres de la liste des factures."""
    from core.listing import Famille
    from .models import Facture

    return [
        Famille('periode', "Période d'émission", exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('statut', 'État', valeurs=[
            (f'statut_{code}', libelle, Q(statut=code)) for code, libelle in Facture.STATUT
        ]),
        Famille('type', 'Type de facture', valeurs=[
            (f'type_{code}', libelle, Q(type_facture=code)) for code, libelle in Facture.TYPE
        ]),
        Famille('contient', 'Contient des actes de', source=_natures_contenues),
        Famille('caisse', 'Caisse', source=_caisses),
        Famille('mode', 'Mode de règlement', source=_modes_de_paiement),
        # `montant_paye` peut dépasser `montant_total` (un trop-perçu) : « soldée »
        # se teste donc en `gte`, sinon une facture payée en trop passerait pour
        # partiellement réglée.
        Famille('reglement', 'Règlement', valeurs=[
            ('regl_soldee',  'Soldée',
             Q(montant_paye__gte=F('montant_total'))),
            ('regl_partiel', 'Partiellement réglée',
             Q(montant_paye__gt=0) & Q(montant_paye__lt=F('montant_total'))),
            ('regl_rien',    'Rien réglé',
             Q(montant_paye__lte=0) & Q(montant_total__gt=0)),
        ]),
        Famille('genre', 'Genre du patient', valeurs=[
            ('genre_M', 'Masculin', Q(patient__sexe='M')),
            ('genre_F', 'Féminin',  Q(patient__sexe='F')),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def _nom_complet(nom, prenoms):
    return f"{(nom or '').upper()} {prenoms or ''}".strip()


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = "Date d'émission"


def _caisses_de(facture):
    """Caisses ayant encaissé cette facture — il peut y en avoir plusieurs.

    Un règlement en deux fois, une avance à l'accueil puis le solde à la caisse
    centrale : la facture relève alors des deux, et doit apparaître sous chacune.
    C'est ce que core.listing appelle une dimension multivaluée.
    """
    noms = sorted({p.caisse.nom for p in facture.paiements.all() if p.caisse_id})
    return noms or [SANS_CAISSE]


def _filtre_caisse(valeurs_brutes):
    """Factures encaissées par l'une des caisses nommées.

    Une dimension non agrégeable en base doit fournir sa propre condition : c'est
    elle qui permet de ne recharger que les lignes des groupes affichés.
    """
    from .models import Paiement

    libelles = {t[0] for t in valeurs_brutes}
    condition = Q(pk__in=Paiement.objects.filter(caisse__nom__in=libelles).values('facture_id'))
    if SANS_CAISSE in libelles:
        condition |= ~Q(pk__in=Paiement.objects.filter(caisse__isnull=False).values('facture_id'))
    return condition


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Facture

    lib_statut = dict(Facture.STATUT)
    lib_type = dict(Facture.TYPE)

    brut = [
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date_emission')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date_emission).year) if o.date_emission else 'Sans date',
            'order':  ('-date_emission',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_emission')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date_emission)),
            'order':  ('-date_emission',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_emission')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date_emission)),
            'order':  ('-date_emission',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_emission')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date_emission))),
            'order':  ('-date_emission',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_emission')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date_emission)),
            'order':  ('-date_emission',),
        }),
        ('patient', 'Patient', None, {
            'values': ('patient__nom', 'patient__prenoms'),
            'label':  lambda r: _vide(_nom_complet(r['patient__nom'], r['patient__prenoms']), 'Sans patient'),
            'valeur': lambda o: _vide(_nom_complet(o.patient.nom, o.patient.prenoms) if o.patient_id else '',
                                      'Sans patient'),
            'order':  ('patient__nom', 'patient__prenoms'),
        }),
        ('type', 'Type de facture', None, {
            'values': ('type_facture',),
            'label':  lambda r: lib_type.get(r['type_facture']) or 'Non précisé',
            'valeur': lambda o: lib_type.get(o.type_facture) or 'Non précisé',
            'order':  ('type_facture',),
        }),
        ('statut', 'État', None, {
            'values': ('statut',),
            'label':  lambda r: lib_statut.get(r['statut']) or 'Non précisé',
            'valeur': lambda o: lib_statut.get(o.statut) or 'Non précisé',
            'order':  ('statut',),
        }),
        # Pas de `values` : la caisse se lit sur les paiements, et une facture
        # peut relever de plusieurs groupes. Les compteurs se calculent alors en
        # Python, sur la même source que les en-têtes.
        ('caisse', 'Caisse', None, {
            'valeur': _caisses_de,
            'filtre': _filtre_caisse,
            'order':  ('-date_emission',),
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


#: Colonnes triables. `reste` porte sur l'annotation posée par la vue :
#: `solde_restant` est une propriété Python, que la base ne sait pas trier.
TRIS = {
    'numero':   ('numero',),
    'patient':  ('patient__nom', 'patient__prenoms'),
    'date':     ('date_emission',),
    'total':    ('montant_total',),
    'paye':     ('montant_paye',),
    'reste':    ('reste',),
    'statut':   ('statut',),
}
