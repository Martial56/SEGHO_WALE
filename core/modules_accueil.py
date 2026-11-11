"""Tuiles du lanceur de modules de la page d'accueil.

La page d'accueil ne décrit plus ses tuiles à la main : elle boucle sur
`tuiles_accueil()`, qui part de la liste `MODULES_ACCUEIL` ci-dessous et y
ajoute ce qui dépend de la personne connectée et de la base :

* l'**accès** — chaque module reprend exactement la règle de l'ancien gabarit
  (`'code' in accessible_codes`, toujours visible, ou superutilisateur
  seulement). Un module masqué pour un rôle le reste ;
* le **sous-titre** — fixe, ou bâti sur un compteur de `_get_dashboard_stats()`
  (core/views.py). Le compteur est isolé dans `stat` pour que le script de la
  page puisse le rafraîchir toutes les 30 secondes (attribut `data-stat`) ;
* la **pastille** — un travail en attente pour cette personne (voir
  core/pastilles.py), ou les alertes de stock pour la pharmacie, ou les
  plannings non lus. Absente quand il n'y a rien : c'est le silence des autres
  tuiles qui lui donne son sens ;
* l'**URL** — celle de la pastille quand elle existe, puisqu'elle mène à la
  liste déjà filtrée sur ce qu'elle a compté.

L'ordre de la liste est l'ordre d'affichage.
"""

from django.urls import reverse

# Règles d'accès qui ne passent pas par un code de module.
TOUJOURS = None
SUPERUTILISATEUR = '__superutilisateur__'

# Modules dont la pastille vient de core/pastilles.py (clé = code de module).
CODES_PASTILLES = ('hospitalisation', 'consultations', 'caisse')

def _module(cle, libelle, sous_titre, couleur, image, url,
            acces=TOUJOURS, mots_cles='', recadrage='', style=''):
    """Une entrée de `MODULES_ACCUEIL`.

    `image` est un chemin sous static/. `recadrage` : '' montre l'image
    entière (illustrations détourées ou déjà rondes), 'carre' recadre une
    image opaque en carré arrondi, 'zoom' ne garde que le centre d'une image
    large. `couleur` borde la tuile au survol, en vue « Liste ».

    `style` est du CSS posé tel quel sur la balise `<img>` de cette tuile-là,
    comme on l'écrivait à la main dans l'ancien gabarit. Il s'applique après
    `accueil.css`, donc il l'écrase : c'est de quoi régler une image au cas par
    cas sans toucher au CSS commun ni aux autres tuiles. Exemple :
    `style='width:110%;height:110%;border-radius:50%;'`. À laisser vide quand
    le rendu par défaut convient, et sans guillemets dedans (Django les
    échapperait).

    `url` est un nom de route Django, ou un chemin brut s'il commence par « / »
    ou vaut « # » (modules sans page pour l'instant). `mots_cles` élargit la
    recherche au-delà du libellé (ex. « Meo » se trouve aussi en tapant
    « hospitalisation »).
    """
    return {
        'cle': cle, 'libelle': libelle, 'sous_titre': sous_titre,
        'couleur': couleur, 'image': image, 'recadrage': recadrage,
        'style': style,
        'url': url, 'acces': acces, 'mots_cles': mots_cles,
    }


MODULES_ACCUEIL = [
    _module('tableau_de_bord', 'Tableau de bord', 'Statistiques & KPIs', '#C25100',
            'img/speedometer.png', 'kpi_dashboard', mots_cles='kpi statistiques'),
    _module('patients', 'Patients', 'Dossiers patients', '#1F7A4D',
            'img/dspa.png', 'patients:list', acces='patients'),
    _module('docteurs', 'Docteurs', 'Corps médical', '#00695C',
            'img/logchir.png', 'medecin_dashboard', acces='medecins', mots_cles='médecins'),
    _module('prestations', 'Prestations', 'Unités de soins', '#3949AB',
            'img/ser1.png', 'services:list', acces='services', mots_cles='services'),
    _module('rendezvous', 'Rendez-vous', 'Agenda', '#37474F',
            'img/stetoscop.png', 'patients:rdv_global', acces='rendezvous', mots_cles='rdv'),
    _module('ordonnances', 'Ordonnances', 'Prescriptions', '#00796B',
            'img/ord.png', 'ordonnance_list', acces='ordonnances'),
    _module('hospitalisation', 'Meo', 'Hospitalisations', '#00796B',
            'img/hosp.png', 'hospitalisation:list', acces='hospitalisation',
            mots_cles='hospitalisation'),
    _module('soins', 'Soins', 'Soins', '#C2185B',
            'img/soin.png', 'soins:list', acces='consultations', mots_cles='consultations'),
    _module('laboratoire', 'Laboratoire', 'Analyses', '#00897B',
            'img/lab.png', 'laboratoire_list', acces='laboratoire', mots_cles='analyses examens'),
    _module('pharmacie', 'Pharmacie', 'Stock OK', '#0277BD',
            'img/phar.png', 'pharmacie_accueil', acces='pharmacie', mots_cles='médicaments'),
    _module('assurance', 'Assurance', 'Couvertures santé', '#1565C0',
            'img/ass.png', '#', acces='assurance'),
    _module('caisse', 'Caisse', 'À jour', '#1565C0',
            'img/sans-contact.png', 'facturation:list', acces='caisse',
            mots_cles='factures facturation'),
    _module('comptabilite', 'Comptabilité', 'Ventes, écritures, états', '#B26A00',
            'img/compp.png', 'comptabilite:accueil', acces='facturation', recadrage='carre'),
    _module('gynecologie', 'Gynécologie', 'Consultations spécialisées', '#1B4D47',
            'img/gyn.png', 'gynecologie_list', acces='gynecologie', mots_cles='cpn maternité'),
    _module('planning', 'Planning', 'Plannings hebdomadaires', '#0277BD',
            'img/calllll.jpg', 'planning_list', acces='planning', recadrage='zoom'),
    _module('achats', 'Achats', 'Fournisseurs · Commandes', '#C62828',
            'img/cart33.jpg', 'achats:dashboard', acces='achats',
            mots_cles='fournisseurs commandes',
            style='width:140%;height:150%;object-fit:cover;border-radius:16px;'),
    _module('stock', 'Stock', 'Gestion des stocks', '#8D3B2F',
            'img/stockk.jpg', 'stock_dashboard', acces='stock', recadrage='carre'),
    _module('employes', 'Employés', 'Personnel', '#1565C0',
            'img/emp.png', 'ressources_humaines_list', acces='ressources_humaines',
            mots_cles='personnel rh'),
    _module('evaluation', 'Évaluation', 'Performance du personnel', '#A86B00',
            'img/etoil.png', '#', acces='evaluation'),
    _module('presence', 'Présence', 'Pointage & assiduité', '#455A64',
            'img/pres.png', 'presence_pointage', acces='presence', mots_cles='pointage',
            recadrage='carre'),
    _module('conges', 'Congés & Absences', 'Demandes & planification', '#C25100',
            'img/beach.png', '/conges/', acces='conges'),
    _module('rapports', 'Rapports', 'Rapports personnalisés', '#3949AB',
            'img/visual-data.png', 'rapports:hub', acces='rapports'),
    _module('guide', "Guide d'utilisation", "Mode d'emploi des modules", '#1F7A4D',
            'img/guide.png', 'guide:hub', mots_cles='aide'),
    _module('journal', "Journal d'activité", 'Actions des utilisateurs', '#1F7A4D',
            'img/logs.png', 'journal:list', acces=SUPERUTILISATEUR, mots_cles='historique'),
    _module('parametres', 'Paramètres', 'Administration', '#455A64',
            'img/para.png', '/admin/', acces='admin', mots_cles='administration réglages'),
]


def _accessible(module, user, accessible_codes):
    acces = module['acces']
    if acces is TOUJOURS:
        return True
    if acces == SUPERUTILISATEUR:
        return bool(user and user.is_superuser)
    return acces in accessible_codes


def _resoudre_url(url):
    if url == '#' or url.startswith('/'):
        return url
    return reverse(url)


def _sous_titre_compteur(stat, valeur, suite):
    """Sous-titre « <compteur> suite », le compteur rafraîchi par le script."""
    return {'stat': stat, 'valeur': valeur, 'suite': suite}


def tuiles_accueil(user, accessible_codes, stats, pastilles,
                   plannings_non_vus=0, can_manage_rh_presence=False):
    """Tuiles à afficher pour `user`, dans l'ordre de `MODULES_ACCUEIL`.

    Chaque tuile est le module enrichi de :
    * `href` — URL finale ;
    * `sous_titre` — texte simple, ou dict `{stat, valeur, suite}` ;
    * `sous_titre_dynamique` — marqueur pour les sous-titres que le script
      réécrit en entier (« Stock OK » ↔ « N alertes », « À jour » ↔ « N
      impayée(s) ») ;
    * `sous_titre_accent` — sous-titre mis en évidence (plannings non lus) ;
    * `pastille` — `{cle, total, libelle, teinte}` ou None. Les pastilles que
      le script rafraîchit (Meo, Soins, Caisse, Pharmacie) sont toujours
      présentes, avec `total` à 0 quand rien n'attend : le gabarit les masque,
      et le rafraîchissement peut ainsi les faire apparaître sans recharger.
    """
    tuiles = []
    for module in MODULES_ACCUEIL:
        if not _accessible(module, user, accessible_codes):
            continue

        tuile = dict(module)
        tuile['href'] = _resoudre_url(module['url'])
        tuile['sous_titre_dynamique'] = ''
        tuile['sous_titre_accent'] = False
        tuile['pastille'] = None

        # Pastille « à traiter » (core/pastilles.py) : elle prend aussi l'URL,
        # qui ouvre la liste déjà filtrée sur ce qu'elle a compté.
        code_pastille = module['acces']
        if code_pastille in CODES_PASTILLES:
            entree = pastilles.get(code_pastille)
            tuile['pastille'] = {
                'cle': code_pastille, 'total': entree['total'] if entree else 0,
                'libelle': entree['libelle'] if entree else 'à traiter',
                'teinte': 'rouge',
            }
            if entree:
                tuile['href'] = entree['url']

        cle = module['cle']
        if cle == 'patients':
            tuile['sous_titre'] = _sous_titre_compteur('patients_total', stats['patients_total'], ' enregistrés')
        elif cle == 'rendezvous':
            tuile['sous_titre'] = _sous_titre_compteur('rdv_today', stats['rdv_today'], ' du jour')
        elif cle == 'hospitalisation':
            tuile['sous_titre'] = _sous_titre_compteur('hospitalisations', stats['hospitalisations'], ' en cours')
        elif cle == 'soins':
            tuile['sous_titre'] = _sous_titre_compteur('soins_aujourd_hui', stats['soins_aujourd_hui'], " aujourd'hui")
        elif cle == 'laboratoire':
            tuile['sous_titre'] = _sous_titre_compteur('analyses_pending', stats['analyses_pending'], ' en attente')
        elif cle == 'employes':
            tuile['sous_titre'] = _sous_titre_compteur('employes_actifs', stats['employes_actifs'], ' actifs')
        elif cle == 'pharmacie':
            tuile['sous_titre_dynamique'] = 'pharmacie'
            alertes = stats['medicaments_alerte']
            if alertes > 0:
                tuile['sous_titre'] = _sous_titre_compteur('medicaments_alerte', alertes, ' alertes')
            tuile['pastille'] = {
                'cle': 'pharmacie', 'total': alertes,
                'libelle': "produit(s) sous le seuil d'alerte", 'teinte': 'orange',
            }
        elif cle == 'caisse':
            tuile['sous_titre_dynamique'] = 'factures'
            if stats['factures_impayees'] > 0:
                tuile['sous_titre'] = _sous_titre_compteur('factures_impayees', stats['factures_impayees'], ' impayée(s)')
        elif cle == 'planning' and plannings_non_vus:
            pluriel = 'x' if plannings_non_vus > 1 else ''
            tuile['sous_titre'] = f'{plannings_non_vus} nouveau{pluriel}'
            tuile['sous_titre_accent'] = True
            tuile['pastille'] = {
                'cle': 'planning', 'total': plannings_non_vus,
                'libelle': 'planning(s) non consulté(s)', 'teinte': 'rouge',
            }
        elif cle == 'presence' and can_manage_rh_presence:
            tuile['href'] = reverse('presence_registre')

        tuiles.append(tuile)
    return tuiles
