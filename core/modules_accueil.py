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

# Domaines des boutons de filtre, dans l'ordre d'affichage.
DOMAINES = [
    ('cli', 'Clinique'),
    ('fin', 'Pharmacie & finances'),
    ('rh', 'Ressources humaines'),
    ('pil', 'Pilotage'),
]


def _module(cle, libelle, sous_titre, domaine, couleur, icone, url,
            acces=TOUJOURS, mots_cles=''):
    """Une entrée de `MODULES_ACCUEIL`.

    `url` est un nom de route Django, ou un chemin brut s'il commence par « / »
    ou vaut « # » (modules sans page pour l'instant). `mots_cles` élargit la
    recherche au-delà du libellé (ex. « Meo » se trouve aussi en tapant
    « hospitalisation »).
    """
    return {
        'cle': cle, 'libelle': libelle, 'sous_titre': sous_titre,
        'domaine': domaine, 'couleur': couleur, 'icone': icone,
        'url': url, 'acces': acces, 'mots_cles': mots_cles,
    }


# Tracés SVG au trait, viewBox 0 0 24 24, dessinés pour SEGHO-WALE.
MODULES_ACCUEIL = [
    _module('tableau_de_bord', 'Tableau de bord', 'Statistiques & KPIs', 'pil', '#C25100',
            'M12 14l4-4M3.3 19a9 9 0 1 1 17.4 0',
            'kpi_dashboard', mots_cles='kpi statistiques'),
    _module('patients', 'Patients', 'Dossiers patients', 'cli', '#1F7A4D',
            'M5 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0M2 21c0-4 3-6 7-6s7 2 7 6M19 8v6M16 11h6',
            'patients:list', acces='patients'),
    _module('docteurs', 'Docteurs', 'Corps médical', 'cli', '#00695C',
            'M8 7a4 4 0 1 0 8 0a4 4 0 1 0-8 0M5 21c0-4 3-7 7-7s7 3 7 7M12 15v4M10 17h4',
            'medecin_dashboard', acces='medecins', mots_cles='médecins'),
    _module('prestations', 'Prestations', 'Unités de soins', 'cli', '#3949AB',
            'M5 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M12 11v5M9.5 13.5h5',
            'services:list', acces='services', mots_cles='services'),
    _module('rendezvous', 'Rendez-vous', 'Agenda', 'cli', '#37474F',
            'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4M9 15l2 2 4-4',
            'patients:rdv_global', acces='rendezvous', mots_cles='rdv'),
    _module('ordonnances', 'Ordonnances', 'Prescriptions', 'cli', '#00796B',
            'M7 4h10a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 4V3h6v1M9 10h6M9 14h6M9 18h3',
            'ordonnance_list', acces='ordonnances'),
    _module('hospitalisation', 'Meo', 'Hospitalisations', 'cli', '#00796B',
            'M3 18V6M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5M5 11a2 2 0 1 0 4 0a2 2 0 1 0-4 0',
            'hospitalisation:list', acces='hospitalisation', mots_cles='hospitalisation'),
    _module('soins', 'Soins', 'Soins', 'cli', '#C2185B',
            'M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10zM12 9v5M9.5 11.5h5',
            'soins:list', acces='consultations', mots_cles='consultations'),
    _module('laboratoire', 'Laboratoire', 'Analyses', 'cli', '#00897B',
            'M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3M7.5 15h9',
            'laboratoire_list', acces='laboratoire', mots_cles='analyses examens'),
    _module('pharmacie', 'Pharmacie', 'Stock OK', 'fin', '#0277BD',
            'M10.5 20.5a5 5 0 0 1-7-7l6-6a5 5 0 0 1 7 7zM8.5 8.5l7 7',
            'pharmacie_accueil', acces='pharmacie', mots_cles='médicaments'),
    _module('assurance', 'Assurance', 'Couvertures santé', 'fin', '#1565C0',
            'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4',
            '#', acces='assurance'),
    _module('caisse', 'Caisse', 'À jour', 'fin', '#1565C0',
            'M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM2 10h20M6 15h4',
            'facturation:list', acces='caisse', mots_cles='factures facturation'),
    _module('comptabilite', 'Comptabilité', 'Ventes, écritures, états', 'fin', '#B26A00',
            'M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 18h8',
            'comptabilite:accueil', acces='facturation'),
    _module('gynecologie', 'Gynécologie', 'Consultations spécialisées', 'cli', '#1B4D47',
            'M7 9a5 5 0 1 0 10 0a5 5 0 1 0-10 0M12 14v7M9 18h6',
            'gynecologie_list', acces='gynecologie', mots_cles='cpn maternité'),
    _module('planning', 'Planning', 'Plannings hebdomadaires', 'rh', '#0277BD',
            'M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4M7 14h2M11 14h2M15 14h2M7 17h2M11 17h2',
            'planning_list', acces='planning'),
    _module('achats', 'Achats', 'Fournisseurs · Commandes', 'fin', '#C62828',
            'M7.5 20a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M15.5 20a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M2 3h3l2.5 12h11l2-8H6',
            'achats:dashboard', acces='achats', mots_cles='fournisseurs commandes'),
    _module('stock', 'Stock', 'Gestion des stocks', 'fin', '#8D3B2F',
            'M21 8l-9-5-9 5 9 5zM3 8v8l9 5 9-5V8M12 13v8',
            'stock_dashboard', acces='stock'),
    _module('employes', 'Employés', 'Personnel', 'rh', '#1565C0',
            'M5.5 8a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0M14.5 9a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M2 20c0-3.5 3-6 7-6s7 2.5 7 6M16 14c3 0 6 2 6 5',
            'ressources_humaines_list', acces='ressources_humaines', mots_cles='personnel rh'),
    _module('evaluation', 'Évaluation', 'Performance du personnel', 'rh', '#A86B00',
            'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
            '#', acces='evaluation'),
    _module('presence', 'Présence', 'Pointage & assiduité', 'rh', '#455A64',
            'M5 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0M2 21c0-4 3-6 7-6M13 17a4 4 0 1 0 8 0a4 4 0 1 0-8 0M17 15v2l1.5 1',
            'presence_pointage', acces='presence', mots_cles='pointage'),
    _module('conges', 'Congés & Absences', 'Demandes & planification', 'rh', '#C25100',
            'M12 3a9 9 0 0 1 9 9H3a9 9 0 0 1 9-9zM12 12v7a2 2 0 0 0 4 0',
            '/conges/', acces='conges'),
    _module('rapports', 'Rapports', 'Rapports personnalisés', 'pil', '#3949AB',
            'M4 20V10M10 20V4M16 20v-7M22 20H2',
            'rapports:hub', acces='rapports'),
    _module('guide', "Guide d'utilisation", "Mode d'emploi des modules", 'pil', '#1F7A4D',
            'M4 19V5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2zM20 19v2H6',
            'guide:hub', mots_cles='aide'),
    _module('journal', "Journal d'activité", 'Actions des utilisateurs', 'pil', '#1F7A4D',
            'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
            'journal:list', acces=SUPERUTILISATEUR, mots_cles='historique'),
    _module('parametres', 'Paramètres', 'Administration', 'pil', '#455A64',
            'M4 6h9M17 6h3M13 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0M4 12h3M11 12h9M7 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M4 18h10M18 18h2M14 18a2 2 0 1 0 4 0a2 2 0 1 0-4 0',
            '/admin/', acces='admin', mots_cles='administration réglages'),
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
