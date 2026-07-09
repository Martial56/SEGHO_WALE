# Rechargements inutiles à remplacer par de l'AJAX

Backlog de pages/boutons qui font un rechargement complet de page pour une
action qui pourrait rester sur place (filtre, recherche, pagination,
changement de statut...). À traiter plus tard, module par module, en
copiant le pattern déjà en place sur `hospitalisation`.

## Référence : le pattern déjà implémenté

**Filtres / recherche / pagination / vue** — voir `hospitalisation/list.html` :
- `templates/hospitalisation/list.html` — page principale, IDs stables
  (`#subheader-controls`, `#list-results`, `#page-count`) qui servent de
  cibles de remplacement.
- `templates/hospitalisation/includes/_list_controls.html` — partial
  (tags de filtre, dropdown Filtres, pagination, boutons de vue).
- `templates/hospitalisation/includes/_list_results.html` — partial
  (stats + tableau/kanban).
- `hospitalisation/views.py` → `hospitalisation_list()` — même contexte
  Django rendu deux fois : page complète si requête normale, JSON
  `{controls_html, results_html, total}` via `render_to_string()` si
  header `X-Requested-With: XMLHttpRequest`.
- JS dans `list.html` (`refreshList()`, `currentParams()`) : fetch → swap
  `innerHTML` des deux conteneurs → `history.pushState()` (URL
  partageable, bouton précédent du navigateur fonctionnel via `popstate`).

**Boutons de transition de statut (Confirmer/Décharger/Clôturer/Annuler...)**
— voir `hospitalisation/detail.html` :
- `doTransition(url, extra)` — fetch POST avec CSRF + `X-Requested-With`,
  la vue renvoie un JSON d'état (`_etat_payload()` dans `views.py`).
- Au retour : `updateBadge()`, `updatePipeline()`, `renderActionBar()`,
  etc. re-rendent chaque petit bout du DOM à partir du JSON — pas de
  `innerHTML` géant, chaque fonction sait quel élément mettre à jour.
- Si la vue renvoie `{'reload': true}`, on fait un vrai
  `window.location.reload()` (cas où l'état a trop changé pour un rendu
  JS partiel, ex. après une annulation).

## Comment le refaire proprement sur un autre module

### A. Page liste (filtres / recherche / pagination / vue)

1. Repérer le formulaire GET et les fonctions JS qui font
   `form.submit()` ou `window.location.href = ...`.
2. Découper le template en 2 partials réutilisables : un pour les
   contrôles (filtres actifs, dropdown, pagination, boutons de vue), un
   pour les résultats (stats + tableau/kanban). Les deux doivent
   fonctionner à l'identique que ce soit inclus dans la page complète ou
   rendu seul en JSON.
3. Dans la vue : construire le `context` une seule fois, puis brancher
   sur `X-Requested-With` — JSON avec les deux fragments rendus via
   `render_to_string(..., context, request=request)` sinon rendu complet.
4. Supprimer tout `.submit()`/`window.location` dans le JS, les remplacer
   par un `fetch()` vers la même URL + les query params courants, puis
   remplacer les deux conteneurs par `innerHTML` et faire
   `history.pushState`.
5. Pagination : passer les liens en `data-page="N"` + délégation
   d'événement sur `.o-pag-btn` (pas de listener direct, les éléments
   sont recréés à chaque swap).
6. Ajouter un handler `popstate` pour que précédent/suivant du navigateur
   marche (relire `location.search`, refaire le fetch).
7. **Piège à éviter** : les commentaires Django `{# ... #}` ne supportent
   PAS plusieurs lignes — ils s'affichent en brut sur la page si on les
   étale sur 2+ lignes. Toujours une seule ligne, ou utiliser
   `{% comment %}...{% endcomment %}` pour du multi-lignes.

### B. Bouton de transition de statut / modal de confirmation

1. Vérifier si la vue a déjà un payload d'état réutilisable (comme
   `_etat_payload()`/`_boutons_extra()` côté hospitalisation) — sinon
   en créer un petit, centralisé, qui calcule tout ce que le bouton/badge
   a besoin de savoir (visible/enabled/raison_blocage...).
2. Le formulaire POST classique devient un `fetch()` avec CSRF token +
   header `X-Requested-With`, la vue renvoie le JSON d'état si c'est une
   requête AJAX (sinon comportement actuel inchangé — garder la
   compatibilité formulaire classique en repli).
3. Écrire UNE fonction JS de mise à jour par petit bout d'UI concerné
   (badge de statut, bouton lui-même, pipeline...) plutôt qu'un seul gros
   `innerHTML` — plus facile à maintenir et à débugger.
4. Pour les modals qui *ressemblent* déjà à de l'AJAX mais soumettent en
   vrai (ex. `achats/commandes/detail.html`, `facturation/detail.html`) :
   il suffit de changer le `<form method="post">` en bouton + fetch, le
   HTML du modal ne change pas.

## Backlog — pages liste (filtres/recherche/pagination)

Priorité suggérée (du plus rentable au moins urgent) :

1. **`facturation/list.html`** — recherche déjà en AJAX, mais quelqu'un a
   explicitement laissé les filtres statut/type en rechargement complet
   (commentaire "rechargement — intentionnel"). Pagination aussi à
   reprendre. Travail à moitié fait, facile à terminer.
2. **`patients/list.html`** et **`gynecologie/list.html`** — la recherche
   fait déjà un fetch + swap HTML, mais la pagination reste en liens
   classiques `<a href="?page=...">`. Passer au pattern JSON+fragments.
3. **`laboratoire/list.html`** — filtre statut + recherche + pagination +
   toggle vue, tout en rechargement complet.
4. **`stock/produits/list.html`** — filtres type/catégorie/statut en
   `onchange="this.form.submit()"`, pagination classique.
5. **`employer/list.html`** — filtres service/statut en
   `onchange="this.form.submit()"`.
6. **`soins/list.html`** — pagination + filtre en rechargement complet.
7. **`achats/besoins|commandes|fournisseurs|proformas/list.html`** —
   listes plus petites, priorité plus faible.
8. **`rapports/historique.html`** — filtre GET simple, pas de pagination
   vue trouvée.

À vérifier manuellement (pas de pattern de rechargement détecté dans le
`list.html` inspecté, mais l'app a d'autres vues paginées) :
`pharmacie/*`, `caisse/list.html`, `consultations/list.html`.

## Backlog — boutons de workflow (rechargement pour un changement de statut)

**Priorité haute (actions fréquentes au quotidien) :**
- `soins/detail.html` — bouton "Administrer" (formulaire classique)
- `soins/procedure/detail.html` — "Terminer" / "Annuler" une procédure
- `facturation/detail.html` — "Valider" une facture, et le modal "Payer"
  (ressemble à de l'AJAX mais soumet un vrai formulaire)
- `laboratoire/detail_demande.html` — "Envoyer au labo"

**Priorité moyenne :**
- `achats/commandes/detail.html` et `achats/proformas/detail.html` —
  modals "Valider"/"Rejeter" (même symptôme : UI de modal moderne, mais
  soumission classique en dessous)
- `conges/detail.html` — transitions de statut de congé + modal annuler
- `planning/hebdomadaire.html` — "Publier"/"Supprimer"/"Dupliquer" +
  2 modals
- `stock/fiches/detail.html`, `stock/fiches/valider.html`,
  `stock/dotation/detail.html`, `stock/commandes/detail.html` —
  boutons "Envoyer"/"Valider" un document

**Priorité basse (actions rares/admin, même anti-pattern) :**
- `planning/bureaux.html` — boutons "Monter"/"Descendre" pour réordonner
- Suppressions en ligne dans des tableaux : `medecins/list.html`,
  `employer/list.html` (rh_supprimer), `pharmacie/inventaire_list.html`,
  `patients/pathologie_list.html`, `patients/typevisite_list.html`,
  `employer/detail.html` (documents/infos employé),
  `services/categories/form.html`, `services/unites/form.html`,
  `services/unites/categories/form.html`
- `achats/besoins/list.html` — action "envoyer_achats" en ligne dans le
  tableau (même famille que les suppressions en ligne, mais pour un
  changement de statut)

Rien trouvé côté tri de colonnes par lien (`?sort=`) ni édition en ligne
cellule par cellule.
