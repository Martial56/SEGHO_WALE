"""Déclaration de la liste des chambres pour la brique core.listing.

Pas de famille « Période » ici : une chambre n'a pas de date, elle existe. La
liste s'ouvre donc sur l'ensemble du parc, et « Effacer » y ramène.

Chambre est un ModeleCentre : le cloisonnement est assuré par son manager, cette
déclaration n'a pas à s'en soucier.
"""

from django.db.models import Q


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('nom', 'salle_no', 'description')

#: Le parc entier au premier affichage.
FILTRES_DEFAUT = ()


def familles_chambres():
    """Familles de filtres de la liste des chambres."""
    from core.listing import Famille
    from .models import Chambre

    return [
        Famille('disponibilite', 'Disponibilité', valeurs=[
            ('dispo',  'Disponible', Q(statut=True)),
            ('occupe', 'Occupée',    Q(statut=False)),
        ]),
        Famille('type', 'Type de chambre', valeurs=[
            (f'type_{code}', libelle, Q(type_chambre=code))
            for code, libelle in Chambre.TYPE
        ]),
        Famille('genre', 'Genre admis', valeurs=[
            (f'genre_{code}', libelle, Q(genre=code))
            for code, libelle in Chambre.GENRE
        ]),
        Famille('standing', 'Standing', valeurs=[
            ('prive',     'Chambre privée',  Q(prive=True)),
            ('non_prive', 'Chambre commune', Q(prive=False)),
        ]),
        # Les équipements se cumulent en OU à l'intérieur de la famille : cocher
        # « Climatisation » et « Télévision » montre les chambres qui ont l'un ou
        # l'autre. Croiser deux exigences se fait en cochant dans deux familles.
        Famille('confort', 'Confort', valeurs=[
            ('clim',      'Climatisation',        Q(climatisation=True)),
            ('tv',        'Télévision',           Q(television=True)),
            ('internet',  'Accès Internet',       Q(acces_internet=True)),
            ('bains',     'Salle de bains privée', Q(salle_bains_privee=True)),
            ('telephone', 'Téléphone',            Q(telephone_chambre=True)),
        ]),
        Famille('equipement', 'Équipement', valeurs=[
            ('frigo',     'Réfrigérateur',   Q(refrigerateur=True)),
            ('micro',     'Four micro-onde', Q(four_micro_onde=True)),
            ('lit_visit', 'Lit de visiteur', Q(lit_visiteur=True)),
            ('danger',    'Danger biologique', Q(danger_biologique=True)),
        ]),
        Famille('capacite', 'Capacité', valeurs=[
            ('lit_1',    '1 lit',           Q(nombre_lits=1)),
            ('lit_2',    '2 lits',          Q(nombre_lits=2)),
            ('lit_3p',   '3 lits ou plus',  Q(nombre_lits__gte=3)),
        ]),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Chambre

    lib_type = dict(Chambre.TYPE)
    lib_genre = dict(Chambre.GENRE)

    def booleen(champ, oui, non):
        """Dimension d'un champ oui/non : le libellé doit être identique des deux
        côtés, sinon l'en-tête de groupe ne retrouve pas ses lignes."""
        return {
            'values': (champ,),
            'label':  lambda r: oui if r[champ] else non,
            'valeur': lambda o: oui if getattr(o, champ) else non,
            'order':  (champ,),
        }

    brut = [
        ('statut', 'Disponibilité', None, booleen('statut', 'Disponible', 'Occupée')),
        ('type', 'Type de chambre', None, {
            'values': ('type_chambre',),
            'label':  lambda r: lib_type.get(r['type_chambre']) or 'Non précisé',
            'valeur': lambda o: lib_type.get(o.type_chambre) or 'Non précisé',
            'order':  ('type_chambre',),
        }),
        ('genre', 'Genre admis', None, {
            'values': ('genre',),
            'label':  lambda r: lib_genre.get(r['genre']) or 'Non précisé',
            'valeur': lambda o: lib_genre.get(o.genre) or 'Non précisé',
            'order':  ('genre',),
        }),
        ('prive', 'Standing', None, booleen('prive', 'Chambre privée', 'Chambre commune')),
        ('nombre_lits', 'Nombre de lits', None, {
            'values': ('nombre_lits',),
            'label':  lambda r: f"{r['nombre_lits']} lit{'s' if r['nombre_lits'] > 1 else ''}",
            'valeur': lambda o: f"{o.nombre_lits} lit{'s' if o.nombre_lits > 1 else ''}",
            'order':  ('nombre_lits',),
        }),
        ('climatisation', 'Climatisation', None, booleen('climatisation', 'Climatisée', 'Non climatisée')),
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}
