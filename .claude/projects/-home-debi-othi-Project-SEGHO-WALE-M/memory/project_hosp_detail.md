---
name: hosp-detail-template
description: Template detail.html pour la vue détail d'une hospitalisation (pipeline fetch, onglets, SAF ajax)
metadata:
  type: project
---

Ajout du template enrichi hospitalisation/detail.html (accessible via /hospitalisation/<pk>/).

**Fichiers créés/modifiés :**
- `templates/hospitalisation/detail.html` — template complet (pipeline, actions fetch, onglets, encart durée, modale référé, toasts)
- `hospitalisation/views.py` — 3 nouvelles fonctions : `hospitalisation_detail`, `saf_ajouter_ligne`, `hosp_save_decharge`
- `hospitalisation/urls.py` — 3 nouvelles routes : `detail` (`/<pk>/`), `saf_ajouter`, `save_decharge`

**Why:** Refonte UI de la page de détail pour une navigation fluide — les transitions de statut passent toutes en fetch (pas de rechargement), le pipeline s'anime en place, le formulaire de décharge se sauvegarde sans écraser les SAF/checklists.

**How to apply:**
- La vue edit (`form.html`) reste intacte pour l'édition complète des données.
- Le bouton "Modifier" dans `detail.html` renvoie vers `hospitalisation:edit`.
- La vue `hospitalisation_detail` est séparée de `hospitalisation_edit` : aucun risque de suppression accidentelle de SAF manuels par soumission partielle.
- `saf_ajouter_ligne` retourne `facture_statut` en code brut (pas `get_statut_display`), ce qui alimente correctement `chipFac()` côté JS.
