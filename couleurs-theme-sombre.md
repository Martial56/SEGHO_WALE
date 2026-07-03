# Couleurs du theme sombre - SEGHO-WALE

Inventaire genere automatiquement (grep + parsing) de toutes les couleurs utilisees
dans les regles CSS `[data-theme="dark"]` du projet (fichiers CSS + `<style>` inline
dans les templates). Le theme sombre est un toggle manuel JS (`html[data-theme="dark"]`,
bouton `#theme-toggle`, persiste dans `localStorage['segho-theme']`) - il n'y a pas de
media-query `prefers-color-scheme`. Total: **371 couleurs distinctes** relevees sur 105 fichiers.

---

## 1. Tokens officiels (source de verite)

Definis une seule fois dans `static/css/variables.css:76-86`, sous `html[data-theme="dark"]`.
Tous les autres fichiers *devraient* consommer ces variables au lieu de re-ecrire les couleurs.

```css
html[data-theme="dark"] {
    --surface:       #0d2035;   /* fond des cartes / panneaux */
    --surface-muted: #071e28;   /* fond de la page */
    --border:        rgba(255, 255, 255, 0.06);   /* bordures fines */
    --border-strong: rgba(255, 255, 255, 0.12);   /* bordures accentuees */
    --text:          #cce8f4;   /* texte principal */
    --text-muted:    rgba(255, 255, 255, 0.40);   /* texte secondaire */
    --topbar-bg:     #091d2e;   /* fond de la topbar */
    --topbar-border: rgba(255, 255, 255, 0.06);
}
```

Palette commune (identique clair/sombre, definie dans `:root`, `variables.css:6-32`) :

```css
--teal-950: #071e28;   --teal-900: #0d3040;   --teal-800: #0f4358;
--teal-700: #145770;   --teal-600: #1a6d8c;   --teal-500: #2188ab;  /* = --accent */
--teal-400: #34a8cc;   --teal-300: #6ecae3;   --teal-200: #aae1f2;
--teal-100: #d6f3fb;   --teal-50:  #eef9fd;

--color-success: #16a96b;  --color-warning: #e89a1a;
--color-danger:  #e84545;  --color-info:    #2d99db;
--color-violet:  #7b57c2;  --color-coral:   #e66144;
```

---

## 2. Couleurs partagees (utilisees dans 3 fichiers ou plus) — 116 couleurs

Ce sont les couleurs qui composent le vrai "systeme" visuel sombre du projet (cartes,
bordures, textes, badges de statut...). Beaucoup sont des variantes tres proches d'une
meme intention (ex: plusieurs bleus marine "fond de carte" legerement differents) —
marque `[DUPLICAT ?]` quand une couleur semble redondante avec un token officiel de la section 1.

- `#1a2535` — 20 fichiers / 27 usages, proprietes: background, border-left-color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/includes, templates/patients, templates/soins
  - exemples: templates/base.html:392, templates/gynecologie/list.html:27, templates/gynecologie/rdv_form.html:353, templates/gynecologie/registre_naissance.html:26, templates/hospitalisation/chambres/form.html:193, templates/hospitalisation/chambres/list.html:160 (+14 autres)
- `#6eddb0` — 20 fichiers / 27 usages, proprietes: background, color
  - modules: static/css, templates/base.html, templates/employer, templates/medecins, templates/ressources_humaines, templates/services, templates/soins
  - exemples: static/css/global.css:368, templates/base.html:299, templates/employer/base.html:117, templates/employer/dashboard.html:80, templates/employer/detail.html:256, templates/employer/list.html:104 (+14 autres)
- `#2e3f58` — 20 fichiers / 25 usages, proprietes: border-color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/includes, templates/patients, templates/soins
  - exemples: templates/base.html:392, templates/gynecologie/list.html:27, templates/gynecologie/rdv_form.html:353, templates/gynecologie/registre_naissance.html:26, templates/hospitalisation/chambres/form.html:208, templates/hospitalisation/chambres/list.html:160 (+14 autres)
- `#243044` — 19 fichiers / 22 usages, proprietes: --border, background, border-bottom-color, border-color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/laboratoire, templates/patients
  - exemples: templates/base.html:416, templates/gynecologie/base.html:8, templates/gynecologie/list.html:252, templates/hospitalisation/chambres/detail.html:7, templates/hospitalisation/chambres/form.html:7, templates/hospitalisation/chambres/list.html:12 (+13 autres)
- `#f09090` — 19 fichiers / 22 usages, proprietes: background, color
  - modules: static/css, templates/base.html, templates/employer, templates/medecins, templates/services, templates/soins
  - exemples: static/css/forms.css:350, static/css/global.css:369, templates/base.html:300, templates/employer/dashboard.html:201, templates/employer/detail.html:257, templates/employer/form.html:193 (+13 autres)
- `#7ecae0` — 17 fichiers / 28 usages, proprietes: color
  - modules: templates/medecins, templates/services, templates/soins
  - exemples: templates/medecins/base.html:162, templates/medecins/config/departement_detail.html:37, templates/medecins/config/departements_list.html:10, templates/medecins/config/specialite_detail.html:32, templates/services/categories/detail.html:68, templates/services/categories/list.html:134 (+11 autres)
- `#3a4a62` — 17 fichiers / 20 usages, proprietes: border-bottom-color, border-color
  - modules: templates/facturation, templates/gynecologie, templates/hospitalisation, templates/includes, templates/medecins, templates/patients, templates/pharmacie, templates/services, templates/soins
  - exemples: templates/facturation/list.html:13, templates/gynecologie/list.html:19, templates/gynecologie/registre_naissance.html:17, templates/hospitalisation/configuration/liste_admission/form.html:49, templates/hospitalisation/configuration/liste_service/form.html:40, templates/hospitalisation/form.html:245 (+11 autres)
- `#132033` — 17 fichiers / 19 usages, proprietes: --surface, background
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/laboratoire, templates/patients
  - exemples: templates/base.html:416, templates/gynecologie/base.html:8, templates/hospitalisation/chambres/detail.html:7, templates/hospitalisation/chambres/form.html:7, templates/hospitalisation/chambres/list.html:12, templates/hospitalisation/configuration/liste_admission/form.html:6 (+11 autres)
- `#d4e6f5` — 17 fichiers / 19 usages, proprietes: --text, color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/laboratoire, templates/patients
  - exemples: templates/base.html:389, templates/gynecologie/base.html:8, templates/hospitalisation/chambres/detail.html:7, templates/hospitalisation/chambres/form.html:7, templates/hospitalisation/chambres/list.html:12, templates/hospitalisation/configuration/liste_admission/form.html:6 (+11 autres)
- `rgba(255,255,255,0.06)`  → = --border (officiel) — 16 fichiers / 33 usages, proprietes: background, border-bottom-color, border-color, border-top-color
  - modules: static/css, templates/base.html, templates/core, templates/employer, templates/medecins, templates/patients, templates/ressources_humaines
  - exemples: static/css/forms.css:71, static/css/global.css:108, templates/base.html:269, templates/core/dashboard.html:127, templates/core/kpi_dashboard.html:196, templates/employer/base.html:119 (+10 autres)
- `rgba(33,136,171,0.2)` — 16 fichiers / 23 usages, proprietes: background, border-color, box-shadow
  - modules: static/css, templates/base.html, templates/core, templates/facturation, templates/gynecologie, templates/includes, templates/patients, templates/pharmacie
  - exemples: static/css/forms.css:205, static/css/global.css:236, templates/base.html:278, templates/core/dashboard.html:129, templates/core/kpi_dashboard.html:199, templates/facturation/list.html:9 (+10 autres)
- `#cce8f4`  → = --text (officiel) — 13 fichiers / 50 usages, proprietes: --text, --text-main, color
  - modules: static/css, templates/base.html, templates/core, templates/gynecologie, templates/hospitalisation, templates/patients, templates/services, templates/soins
  - exemples: static/css/forms.css:72, static/css/global.css:113, static/css/variables.css:73, templates/base.html:264, templates/core/dashboard.html:123, templates/core/kpi_dashboard.html:192 (+7 autres)
- `rgba(255,255,255,0.4)`  → = --text-muted (officiel) — 13 fichiers / 23 usages, proprietes: --pr-muted, --rh-muted, color
  - modules: static/css, templates/base.html, templates/employer, templates/gynecologie, templates/patients, templates/presence, templates/ressources_humaines
  - exemples: static/css/forms.css:119, static/css/global.css:290, templates/base.html:288, templates/employer/base.html:43, templates/gynecologie/list.html:252, templates/patients/list.html:235 (+7 autres)
- `#fff` — 13 fichiers / 18 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/employer, templates/hospitalisation, templates/presence, templates/ressources_humaines, templates/soins
  - exemples: static/css/global.css:494, templates/base.html:314, templates/employer/base.html:70, templates/employer/conge_list.html:127, templates/employer/list.html:204, templates/employer/registre.html:78 (+7 autres)
- `rgba(255,255,255,.45)` — 13 fichiers / 13 usages, proprietes: --text-muted
  - modules: templates/gynecologie, templates/hospitalisation
  - exemples: templates/gynecologie/base.html:8, templates/hospitalisation/chambres/detail.html:7, templates/hospitalisation/chambres/form.html:7, templates/hospitalisation/chambres/list.html:12, templates/hospitalisation/configuration/liste_admission/form.html:6, templates/hospitalisation/configuration/liste_admission/list.html:5 (+7 autres)
- `#091d2e`  → = --topbar-bg (officiel) — 12 fichiers / 25 usages, proprietes: --topbar-bg, background, border-color
  - modules: static/css, templates/base.html, templates/core, templates/patients, templates/services
  - exemples: static/css/forms.css:115, static/css/global.css:208, static/css/variables.css:73, templates/base.html:269, templates/core/dashboard.html:127, templates/core/kpi_dashboard.html:196 (+6 autres)
- `#c5d4e2` — 12 fichiers / 15 usages, proprietes: --text, color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/includes, templates/patients, templates/services, templates/soins
  - exemples: templates/base.html:393, templates/gynecologie/list.html:28, templates/hospitalisation/chambres/form.html:209, templates/hospitalisation/chambres/list.html:161, templates/hospitalisation/deces/form.html:209, templates/hospitalisation/deces/list.html:88 (+6 autres)
- `#071e28`  → = --surface-muted (officiel) — 12 fichiers / 13 usages, proprietes: --surface-muted, background
  - modules: static/css, templates/base.html, templates/core, templates/employer
  - exemples: static/css/variables.css:73, templates/base.html:264, templates/core/dashboard.html:126, templates/core/kpi_dashboard.html:195, templates/employer/annuaire.html:16, templates/employer/dashboard.html:24 (+6 autres)
- `rgba(255,255,255,.15)` — 11 fichiers / 21 usages, proprietes: border-bottom-color, border-color
  - modules: templates/base.html, templates/hospitalisation, templates/medecins, templates/soins
  - exemples: templates/base.html:388, templates/hospitalisation/chambres/form.html:204, templates/hospitalisation/deces/form.html:196, templates/hospitalisation/form.html:258, templates/medecins/base.html:187, templates/soins/detail.html:199 (+5 autres)
- `#2d3550` — 11 fichiers / 11 usages, proprietes: --border, border-bottom-color
  - modules: templates/services, templates/soins
  - exemples: templates/services/categories/list.html:61, templates/services/consommables/list.html:62, templates/services/includes/layout_css.html:19, templates/services/list.html:33, templates/services/types/list.html:61, templates/services/unites/categories/list.html:61 (+5 autres)
- `#fca5a5` — 11 fichiers / 11 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/deces/form.html:200, templates/hospitalisation/facturation/detail.html:52, templates/hospitalisation/facturation/edit.html:156, templates/hospitalisation/list.html:186, templates/soins/detail.html:200, templates/soins/facturation/detail.html:53 (+5 autres)
- `rgba(255,255,255,.06)` — 11 fichiers / 11 usages, proprietes: background, border-bottom-color, border-top-color
  - modules: templates/employer, templates/hospitalisation, templates/medecins, templates/soins
  - exemples: templates/employer/conge_list.html:109, templates/employer/detail.html:259, templates/hospitalisation/base.html:78, templates/medecins/base.html:125, templates/medecins/config/departements_list.html:22, templates/soins/detail.html:199 (+5 autres)
- `#0d2035`  → = --surface (officiel) — 10 fichiers / 46 usages, proprietes: --surface, background
  - modules: static/css, templates/base.html, templates/core, templates/gynecologie, templates/hospitalisation, templates/patients, templates/services
  - exemples: static/css/forms.css:69, static/css/global.css:190, static/css/variables.css:73, templates/base.html:272, templates/core/kpi_dashboard.html:208, templates/gynecologie/list.html:12 (+4 autres)
- `#1a3050` — 10 fichiers / 14 usages, proprietes: background, border-bottom-color, border-color
  - modules: templates/base.html, templates/gynecologie, templates/hospitalisation, templates/patients, templates/services
  - exemples: templates/base.html:418, templates/gynecologie/list.html:253, templates/hospitalisation/chambres/list.html:166, templates/hospitalisation/configuration/liste_admission/list.html:66, templates/hospitalisation/configuration/liste_service/list.html:62, templates/hospitalisation/deces/list.html:92 (+4 autres)
- `#28304a` — 10 fichiers / 12 usages, proprietes: background
  - modules: templates/gynecologie, templates/includes, templates/medecins, templates/patients, templates/services, templates/soins
  - exemples: templates/gynecologie/list.html:21, templates/gynecologie/registre_naissance_form.html:18, templates/gynecologie/registre_naissance.html:15, templates/includes/subheader.html:3, templates/medecins/base.html:93, templates/patients/list.html:275 (+4 autres)
- `rgba(255,255,255,0.1)` — 9 fichiers / 17 usages, proprietes: border-bottom-color, border-color, border-right-color
  - modules: static/css, templates/base.html, templates/employer, templates/gynecologie, templates/patients, templates/ressources_humaines
  - exemples: static/css/forms.css:197, static/css/global.css:111, templates/base.html:304, templates/employer/form.html:202, templates/employer/import.html:231, templates/employer/organigramme.html:194 (+3 autres)
- `#0f3050` — 9 fichiers / 13 usages, proprietes: background, border-left-color
  - modules: templates/gynecologie, templates/hospitalisation, templates/patients
  - exemples: templates/gynecologie/list.html:223, templates/hospitalisation/chambres/list.html:167, templates/hospitalisation/configuration/liste_admission/list.html:67, templates/hospitalisation/configuration/liste_service/list.html:63, templates/hospitalisation/deces/form.html:203, templates/hospitalisation/deces/list.html:93 (+3 autres)
- `rgba(255,255,255,0.04)` — 9 fichiers / 13 usages, proprietes: background, border-bottom-color
  - modules: static/css, templates/base.html, templates/core, templates/employer, templates/services
  - exemples: static/css/forms.css:266, static/css/global.css:353, templates/base.html:292, templates/core/kpi_dashboard.html:209, templates/employer/dashboard.html:182, templates/employer/detail.html:221 (+3 autres)
- `rgba(255,255,255,.02)` — 9 fichiers / 9 usages, proprietes: background
  - modules: templates/medecins, templates/presence, templates/services
  - exemples: templates/medecins/config/departement_detail.html:11, templates/medecins/config/specialite_detail.html:11, templates/presence/parametres.html:130, templates/services/categories/detail.html:118, templates/services/consommables/detail.html:122, templates/services/detail.html:154 (+3 autres)
- `rgba(255,255,255,.2)` — 9 fichiers / 9 usages, proprietes: border-bottom-color, border-color, color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/chambres/list.html:155, templates/hospitalisation/configuration/liste_admission/list.html:68, templates/hospitalisation/configuration/liste_service/list.html:64, templates/hospitalisation/list.html:169, templates/soins/detail.html:198, templates/soins/form.html:161 (+3 autres)
- `rgba(255,255,255,0.35)` — 8 fichiers / 19 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/employer, templates/ressources_humaines
  - exemples: static/css/forms.css:117, static/css/global.css:164, templates/base.html:271, templates/employer/dashboard.html:82, templates/employer/detail.html:127, templates/employer/import.html:231 (+2 autres)
- `rgba(255, 255, 255, .15)` — 8 fichiers / 11 usages, proprietes: border-bottom-color, border-color
  - modules: templates/services
  - exemples: templates/services/categories/list.html:282, templates/services/consommables/list.html:347, templates/services/includes/article_form_css.html:56, templates/services/includes/form_css.html:53, templates/services/includes/list_css.html:570, templates/services/types/list.html:270 (+2 autres)
- `#e87070` — 8 fichiers / 10 usages, proprietes: border-color, color
  - modules: static/css, templates/base.html, templates/core, templates/employer, templates/ressources_humaines
  - exemples: static/css/global.css:249, templates/base.html:282, templates/core/dashboard.html:132, templates/core/kpi_dashboard.html:202, templates/employer/base.html:89, templates/employer/conge_list.html:108 (+2 autres)
- `rgba(255,255,255,.3)` — 8 fichiers / 10 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins, templates/utilisateur
  - exemples: templates/hospitalisation/base.html:78, templates/hospitalisation/deces/form.html:201, templates/hospitalisation/form.html:90, templates/soins/detail.html:198, templates/soins/form.html:161, templates/soins/procedure/detail.html:98 (+2 autres)
- `rgba(255,255,255,0.05)` — 8 fichiers / 9 usages, proprietes: background, border-bottom-color
  - modules: templates/employer
  - exemples: templates/employer/annuaire.html:16, templates/employer/dashboard.html:24, templates/employer/detail.html:24, templates/employer/form.html:23, templates/employer/import.html:24, templates/employer/list.html:24 (+2 autres)
- `rgba(33,136,171,.2)` — 8 fichiers / 9 usages, proprietes: background
  - modules: templates/base.html, templates/hospitalisation, templates/medecins
  - exemples: templates/base.html:394, templates/hospitalisation/chambres/form.html:210, templates/hospitalisation/chambres/list.html:162, templates/hospitalisation/deces/form.html:210, templates/hospitalisation/deces/list.html:89, templates/hospitalisation/form.html:262 (+2 autres)
- `rgba(232,69,69,.2)` — 8 fichiers / 8 usages, proprietes: background
  - modules: templates/medecins, templates/services, templates/soins
  - exemples: templates/medecins/base.html:166, templates/medecins/config/departement_detail.html:28, templates/services/consommables/detail.html:72, templates/services/detail.html:104, templates/services/types/detail.html:64, templates/services/unites/detail.html:74 (+2 autres)
- `rgba(255,255,255,0.12)`  → = --border-strong (officiel) — 8 fichiers / 8 usages, proprietes: background, border-color, border-right-color
  - modules: static/css, templates/base.html, templates/core, templates/employer, templates/patients, templates/ressources_humaines
  - exemples: static/css/forms.css:118, static/css/global.css:310, templates/base.html:298, templates/core/dashboard.html:147, templates/core/kpi_dashboard.html:227, templates/employer/base.html:119 (+2 autres)
- `rgba(255,255,255,0.45)` — 7 fichiers / 10 usages, proprietes: --text-muted, color
  - modules: static/css, templates/base.html, templates/gynecologie, templates/laboratoire, templates/patients, templates/planning
  - exemples: static/css/forms.css:33, templates/base.html:319, templates/gynecologie/list.html:16, templates/laboratoire/list.html:15, templates/patients/list.html:241, templates/patients/rendez_vous.html:16 (+1 autres)
- `#f0c060` — 7 fichiers / 9 usages, proprietes: color
  - modules: templates/base.html, templates/employer, templates/ressources_humaines
  - exemples: templates/base.html:342, templates/employer/base.html:118, templates/employer/conge_list.html:106, templates/employer/dashboard.html:81, templates/employer/detail.html:255, templates/employer/list.html:105 (+1 autres)
- `rgba(255, 255, 255, 0.04)` — 7 fichiers / 9 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/categories/list.html:66, templates/services/consommables/list.html:67, templates/services/includes/layout_css.html:449, templates/services/list.html:38, templates/services/types/list.html:66, templates/services/unites/categories/list.html:66 (+1 autres)
- `rgba(33,136,171,.18)` — 7 fichiers / 9 usages, proprietes: background
  - modules: templates/medecins, templates/services
  - exemples: templates/medecins/base.html:153, templates/medecins/config/departements_list.html:10, templates/services/categories/detail.html:68, templates/services/consommables/detail.html:73, templates/services/detail.html:105, templates/services/unites/categories/detail.html:141 (+1 autres)
- `#4a5a78` — 7 fichiers / 7 usages, proprietes: border-color
  - modules: templates/services
  - exemples: templates/services/categories/list.html:126, templates/services/consommables/list.html:146, templates/services/includes/form_css.html:288, templates/services/list.html:15, templates/services/types/list.html:111, templates/services/unites/categories/list.html:150 (+1 autres)
- `rgba(255,255,255,.05)` — 7 fichiers / 7 usages, proprietes: background
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/chambres/form.html:203, templates/hospitalisation/chambres/list.html:159, templates/hospitalisation/configuration/liste_admission/list.html:70, templates/hospitalisation/configuration/liste_service/list.html:66, templates/hospitalisation/deces/form.html:204, templates/hospitalisation/list.html:171 (+1 autres)
- `#fbbf24` — 6 fichiers / 12 usages, proprietes: color
  - modules: templates/services
  - exemples: templates/services/categories/list.html:276, templates/services/consommables/list.html:341, templates/services/includes/list_css.html:564, templates/services/types/list.html:264, templates/services/unites/categories/list.html:276, templates/services/unites/list.html:286
- `#7aaec7` — 6 fichiers / 11 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/core, templates/hospitalisation, templates/services
  - exemples: static/css/global.css:110, templates/base.html:281, templates/core/dashboard.html:131, templates/core/kpi_dashboard.html:201, templates/hospitalisation/base.html:77, templates/services/includes/layout_css.html:134
- `#070e05` — 6 fichiers / 8 usages, proprietes: --md-surface, --st-surface, background
  - modules: templates/medecins, templates/stock
  - exemples: templates/medecins/form.html:15, templates/medecins/list.html:15, templates/stock/base.html:15, templates/stock/fournisseurs/form.html:13, templates/stock/mouvements/list.html:13, templates/stock/produits/form.html:13
- `rgba(255,255,255,0.15)` — 6 fichiers / 8 usages, proprietes: background, border-bottom-color
  - modules: static/css, templates/base.html, templates/employer, templates/planning
  - exemples: static/css/global.css:139, templates/base.html:354, templates/employer/base.html:163, templates/planning/bureaux.html:102, templates/planning/hebdomadaire.html:134, templates/planning/par_medecin.html:22
- `rgba(255,255,255,0.3)` — 6 fichiers / 8 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/employer
  - exemples: static/css/global.css:275, templates/base.html:285, templates/employer/form.html:202, templates/employer/import.html:95, templates/employer/list.html:128, templates/employer/organigramme.html:200
- `rgba(232,69,69,0.15)` — 6 fichiers / 7 usages, proprietes: background
  - modules: static/css, templates/base.html, templates/core, templates/employer
  - exemples: static/css/global.css:249, templates/base.html:282, templates/core/dashboard.html:132, templates/core/kpi_dashboard.html:202, templates/employer/dashboard.html:293, templates/employer/import.html:218
- `rgba(255,255,255,.04)` — 6 fichiers / 7 usages, proprietes: background
  - modules: templates/hospitalisation, templates/medecins, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:169, templates/medecins/base.html:126, templates/soins/facturation/detail.html:170, templates/soins/includes/layout_css.html:210, templates/soins/list.html:13, templates/soins/procedure/list.html:12
- `#3d2e00` — 6 fichiers / 6 usages, proprietes: background
  - modules: templates/planning
  - exemples: templates/planning/bureaux.html:59, templates/planning/dashboard.html:64, templates/planning/liste.html:61, templates/planning/mensuel.html:53, templates/planning/par_medecin.html:41, templates/planning/stats.html:129
- `#ffd666` — 6 fichiers / 6 usages, proprietes: color
  - modules: templates/planning
  - exemples: templates/planning/bureaux.html:59, templates/planning/dashboard.html:64, templates/planning/liste.html:61, templates/planning/mensuel.html:53, templates/planning/par_medecin.html:41, templates/planning/stats.html:129
- `rgba(0,0,0,0.2)` — 6 fichiers / 6 usages, proprietes: box-shadow
  - modules: templates/employer
  - exemples: templates/employer/dashboard.html:24, templates/employer/detail.html:24, templates/employer/form.html:23, templates/employer/import.html:24, templates/employer/list.html:24, templates/employer/organigramme.html:24
- `rgba(22,169,107,.2)` — 6 fichiers / 6 usages, proprietes: background
  - modules: templates/medecins, templates/services
  - exemples: templates/medecins/base.html:165, templates/medecins/config/departement_detail.html:27, templates/services/consommables/detail.html:70, templates/services/detail.html:102, templates/services/types/detail.html:62, templates/services/unites/detail.html:72
- `rgba(220,38,38,.15)` — 6 fichiers / 6 usages, proprietes: background
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:52, templates/soins/detail.html:200, templates/soins/facturation/detail.html:53, templates/soins/form.html:163, templates/soins/procedure/detail.html:101, templates/soins/procedure/form.html:93
- `rgba(220,38,38,.35)` — 6 fichiers / 6 usages, proprietes: border-color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:52, templates/soins/detail.html:200, templates/soins/facturation/detail.html:53, templates/soins/form.html:163, templates/soins/procedure/detail.html:101, templates/soins/procedure/form.html:93
- `rgba(255, 193, 7, .1)` — 6 fichiers / 6 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/categories/list.html:276, templates/services/consommables/list.html:341, templates/services/includes/list_css.html:564, templates/services/types/list.html:264, templates/services/unites/categories/list.html:276, templates/services/unites/list.html:286
- `rgba(255, 193, 7, .3)` — 6 fichiers / 6 usages, proprietes: border-color
  - modules: templates/services
  - exemples: templates/services/categories/list.html:276, templates/services/consommables/list.html:341, templates/services/includes/list_css.html:564, templates/services/types/list.html:264, templates/services/unites/categories/list.html:276, templates/services/unites/list.html:286
- `rgba(33,136,171,.15)` — 6 fichiers / 6 usages, proprietes: background
  - modules: static/css, templates/base.html, templates/hospitalisation, templates/medecins, templates/services
  - exemples: static/css/global.css:274, templates/base.html:284, templates/hospitalisation/base.html:77, templates/medecins/config/departement_detail.html:37, templates/medecins/config/specialite_detail.html:32, templates/services/unites/categories/detail.html:37
- `rgba(255,255,255,0.08)` — 5 fichiers / 14 usages, proprietes: background, border-bottom-color, border-color
  - modules: static/css, templates/base.html, templates/medecins, templates/patients
  - exemples: static/css/forms.css:262, static/css/global.css:38, templates/base.html:272, templates/medecins/base.html:24, templates/patients/list.html:252
- `#93c5fd` — 5 fichiers / 7 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:50, templates/hospitalisation/list.html:165, templates/soins/facturation/detail.html:51, templates/soins/includes/statut_css.html:92, templates/soins/procedure/list.html:44
- `rgba(255,255,255,0.2)` — 5 fichiers / 7 usages, proprietes: border-color, color
  - modules: static/css, templates/base.html, templates/employer, templates/ressources_humaines
  - exemples: static/css/forms.css:322, templates/base.html:321, templates/employer/base.html:152, templates/employer/list.html:217, templates/ressources_humaines/base.html:271
- `rgba(0,0,0,0.4)` — 5 fichiers / 6 usages, proprietes: box-shadow
  - modules: static/css, templates/base.html, templates/core, templates/services
  - exemples: static/css/global.css:154, templates/base.html:269, templates/core/dashboard.html:127, templates/core/kpi_dashboard.html:196, templates/services/base.html:161
- `#0a1e2e` — 5 fichiers / 5 usages, proprietes: background
  - modules: static/css, templates/presence, templates/services, templates/soins
  - exemples: static/css/global.css:108, templates/presence/base.html:101, templates/services/base.html:67, templates/services/includes/layout_css.html:124, templates/soins/includes/layout_css.html:86
- `#2a3548` — 5 fichiers / 5 usages, proprietes: background
  - modules: templates/services, templates/soins
  - exemples: templates/services/categories/detail.html:70, templates/services/detail.html:106, templates/services/types/detail.html:65, templates/soins/list.html:170, templates/soins/procedure/list.html:66
- `#6c85a0` — 5 fichiers / 5 usages, proprietes: --text-muted, color, fill
  - modules: templates/services, templates/soins
  - exemples: templates/services/consommables/list.html:158, templates/services/includes/form_css.html:629, templates/services/includes/layout_css.html:19, templates/services/list.html:188, templates/soins/includes/layout_css.html:14
- `#8a9ab0` — 5 fichiers / 5 usages, proprietes: color
  - modules: templates/services, templates/soins
  - exemples: templates/services/categories/detail.html:70, templates/services/detail.html:106, templates/services/types/detail.html:65, templates/soins/list.html:170, templates/soins/procedure/list.html:66
- `rgba(255,255,255,.03)` — 5 fichiers / 5 usages, proprietes: background
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:241, templates/hospitalisation/form.html:45, templates/soins/detail.html:172, templates/soins/facturation/detail.html:242, templates/soins/includes/form_css.html:331
- `rgba(255,255,255,.08)` — 5 fichiers / 5 usages, proprietes: background, border-bottom-color, border-color
  - modules: templates/employer, templates/hospitalisation, templates/medecins, templates/soins
  - exemples: templates/employer/annuaire.html:23, templates/hospitalisation/base.html:69, templates/hospitalisation/deces/form.html:199, templates/medecins/config/departements_list.html:16, templates/soins/includes/layout_css.html:89
- `rgba(255,255,255,.1)` — 5 fichiers / 5 usages, proprietes: background, border-bottom-color, border-color, border-right-color
  - modules: templates/employer, templates/hospitalisation, templates/soins
  - exemples: templates/employer/annuaire.html:118, templates/hospitalisation/detail.html:435, templates/soins/form.html:139, templates/soins/includes/layout_css.html:90, templates/soins/includes/statut_css.html:36
- `rgba(255,255,255,.4)` — 5 fichiers / 5 usages, proprietes: --md-muted, --st-muted, color
  - modules: templates/employer, templates/medecins, templates/stock
  - exemples: templates/employer/conge_list.html:109, templates/employer/detail.html:259, templates/medecins/form.html:15, templates/medecins/list.html:15, templates/stock/base.html:15
- `rgba(33,136,171,0.3)` — 5 fichiers / 5 usages, proprietes: background, border-color
  - modules: static/css, templates/base.html, templates/gynecologie, templates/includes, templates/patients
  - exemples: static/css/global.css:483, templates/base.html:335, templates/gynecologie/list.html:29, templates/includes/subheader.html:201, templates/patients/list.html:283
- `rgba(33,136,171,0.12)` — 4 fichiers / 12 usages, proprietes: background
  - modules: static/css, templates/base.html, templates/core
  - exemples: static/css/global.css:207, templates/base.html:274, templates/core/dashboard.html:129, templates/core/kpi_dashboard.html:199
- `#e2c16a` — 4 fichiers / 7 usages, proprietes: background, color
  - modules: templates/soins
  - exemples: templates/soins/detail.html:155, templates/soins/includes/statut_css.html:126, templates/soins/list.html:96, templates/soins/procedure/list.html:46
- `#7ac4a7` — 4 fichiers / 6 usages, proprietes: color
  - modules: templates/soins
  - exemples: templates/soins/form.html:140, templates/soins/includes/layout_css.html:89, templates/soins/includes/statut_css.html:37, templates/soins/list.html:46
- `rgba(26,92,74,.25)` — 4 fichiers / 6 usages, proprietes: background
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/list.html:167, templates/soins/includes/statut_css.html:128, templates/soins/list.html:110, templates/soins/procedure/list.html:47
- `#b8dff0` — 4 fichiers / 5 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/core
  - exemples: static/css/global.css:353, templates/base.html:292, templates/core/dashboard.html:137, templates/core/kpi_dashboard.html:218
- `rgba(176,125,0,.2)` — 4 fichiers / 5 usages, proprietes: background
  - modules: templates/soins
  - exemples: templates/soins/detail.html:155, templates/soins/includes/statut_css.html:126, templates/soins/list.html:168, templates/soins/procedure/list.html:46
- `rgba(38,83,128,0.1)` — 4 fichiers / 5 usages, proprietes: background
  - modules: templates/employer
  - exemples: templates/employer/dashboard.html:162, templates/employer/form.html:142, templates/employer/import.html:57, templates/employer/list.html:148
- `rgba(38,83,128,0.15)` — 4 fichiers / 5 usages, proprietes: background
  - modules: templates/employer
  - exemples: templates/employer/detail.html:53, templates/employer/form.html:56, templates/employer/list.html:246, templates/employer/organigramme.html:183
- `#4a6a80` — 4 fichiers / 4 usages, proprietes: color, fill
  - modules: templates/hospitalisation, templates/medecins, templates/services
  - exemples: templates/hospitalisation/chambres/form.html:198, templates/medecins/config/departement_detail.html:39, templates/medecins/config/specialite_detail.html:34, templates/services/detail.html:57
- `#4a7a90` — 4 fichiers / 4 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/core
  - exemples: static/css/global.css:206, templates/base.html:273, templates/core/dashboard.html:133, templates/core/kpi_dashboard.html:203
- `rgba(22, 169, 107, 0.2)` — 4 fichiers / 4 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/consommables/list.html:203, templates/services/includes/list_css.html:631, templates/services/list.html:257, templates/services/types/list.html:140
- `rgba(232, 69, 69, 0.2)` — 4 fichiers / 4 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/consommables/list.html:208, templates/services/includes/list_css.html:636, templates/services/list.html:262, templates/services/types/list.html:145
- `rgba(255,255,255,.25)` — 4 fichiers / 4 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/configuration/liste_admission/form.html:51, templates/hospitalisation/configuration/liste_service/form.html:42, templates/hospitalisation/deces/form.html:198, templates/soins/procedure/form.html:92
- `rgba(255,255,255,.35)` — 4 fichiers / 4 usages, proprietes: color
  - modules: templates/employer, templates/soins, templates/utilisateur
  - exemples: templates/employer/annuaire.html:30, templates/soins/form.html:139, templates/soins/includes/statut_css.html:36, templates/utilisateur/mon_compte.html:28
- `rgba(33, 136, 171, 0.15)` — 4 fichiers / 4 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/categories/list.html:157, templates/services/consommables/list.html:213, templates/services/list.html:319, templates/services/unites/list.html:162
- `rgba(33,136,171,0.25)` — 4 fichiers / 4 usages, proprietes: background, border-top-color
  - modules: static/css, templates/gynecologie, templates/includes, templates/patients
  - exemples: static/css/forms.css:272, templates/gynecologie/list.html:30, templates/includes/subheader.html:202, templates/patients/list.html:284
- `rgba(255,255,255,0.18)` — 3 fichiers / 5 usages, proprietes: border-bottom-color, color
  - modules: static/css, templates/employer
  - exemples: static/css/forms.css:35, static/css/global.css:466, templates/employer/organigramme.html:213
- `rgba(38,83,128,0.2)` — 3 fichiers / 5 usages, proprietes: background
  - modules: templates/employer
  - exemples: templates/employer/dashboard.html:79, templates/employer/detail.html:105, templates/employer/import.html:205
- `#181c28` — 3 fichiers / 4 usages, proprietes: --bg, background
  - modules: templates/services, templates/soins
  - exemples: templates/services/includes/layout_css.html:19, templates/soins/form.html:38, templates/soins/includes/layout_css.html:14
- `rgba(255, 255, 255, 0.06)` — 3 fichiers / 4 usages, proprietes: --border, --topbar-border, border-bottom, border-bottom-color
  - modules: static/css, templates/services
  - exemples: static/css/variables.css:73, templates/services/base.html:67, templates/services/includes/layout_css.html:124
- `rgba(33, 136, 171, .12)` — 3 fichiers / 4 usages, proprietes: background
  - modules: templates/services
  - exemples: templates/services/includes/form_css.html:647, templates/services/includes/list_css.html:594, templates/services/unites/list.html:136
- `rgba(33,136,171,0.06)` — 3 fichiers / 4 usages, proprietes: background
  - modules: static/css, templates/base.html, templates/core
  - exemples: static/css/global.css:354, templates/base.html:293, templates/core/kpi_dashboard.html:211
- `rgba(33,136,171,0.1)` — 3 fichiers / 4 usages, proprietes: background
  - modules: static/css, templates/base.html
  - exemples: static/css/forms.css:204, static/css/global.css:113, templates/base.html:335
- `#2a3a50` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/medecins, templates/services
  - exemples: templates/medecins/config/departement_detail.html:39, templates/medecins/config/specialite_detail.html:34, templates/services/detail.html:53
- `#3d0010` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/planning
  - exemples: templates/planning/bureaux.html:29, templates/planning/modifier.html:111, templates/planning/stats.html:121
- `#4a8aaa` — 3 fichiers / 3 usages, proprietes: border-bottom-color, border-color
  - modules: static/css, templates/services
  - exemples: static/css/global.css:113, templates/services/includes/article_form_css.html:191, templates/services/includes/layout_css.html:148
- `#6fcf97` — 3 fichiers / 3 usages, proprietes: color
  - modules: templates/hospitalisation
  - exemples: templates/hospitalisation/chambres/detail.html:107, templates/hospitalisation/chambres/form.html:194, templates/hospitalisation/chambres/list.html:169
- `#80c8ef` — 3 fichiers / 3 usages, proprietes: color
  - modules: static/css, templates/base.html, templates/employer
  - exemples: static/css/global.css:371, templates/base.html:302, templates/employer/detail.html:258
- `#86efac` — 3 fichiers / 3 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:51, templates/soins/facturation/detail.html:52, templates/soins/includes/statut_css.html:94
- `#bcd5a8` — 3 fichiers / 3 usages, proprietes: --md-text, --st-text
  - modules: templates/medecins, templates/stock
  - exemples: templates/medecins/form.html:15, templates/medecins/list.html:15, templates/stock/base.html:15
- `#d1d5db` — 3 fichiers / 3 usages, proprietes: color
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:49, templates/soins/facturation/detail.html:50, templates/soins/includes/statut_css.html:121
- `rgba(107,114,128,.2)` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/hospitalisation, templates/soins
  - exemples: templates/hospitalisation/facturation/detail.html:49, templates/soins/facturation/detail.html:50, templates/soins/includes/statut_css.html:121
- `rgba(154,184,138,.18)` — 3 fichiers / 3 usages, proprietes: --md-border, --st-border
  - modules: templates/medecins, templates/stock
  - exemples: templates/medecins/form.html:15, templates/medecins/list.html:15, templates/stock/base.html:15
- `rgba(22,169,107,0.12)` — 3 fichiers / 3 usages, proprietes: background
  - modules: static/css, templates/base.html, templates/employer
  - exemples: static/css/global.css:368, templates/base.html:299, templates/employer/dashboard.html:317
- `rgba(232,154,26,0.18)` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/employer, templates/ressources_humaines
  - exemples: templates/employer/base.html:118, templates/employer/dashboard.html:202, templates/ressources_humaines/base.html:217
- `rgba(232,154,26,0.3)` — 3 fichiers / 3 usages, proprietes: border-color
  - modules: templates/employer, templates/ressources_humaines
  - exemples: templates/employer/base.html:118, templates/employer/dashboard.html:202, templates/ressources_humaines/base.html:217
- `rgba(255,255,255,0.03)` — 3 fichiers / 3 usages, proprietes: background
  - modules: static/css, templates/base.html
  - exemples: static/css/forms.css:262, static/css/global.css:351, templates/base.html:290
- `rgba(255,255,255,0.07)` — 3 fichiers / 3 usages, proprietes: --border, background
  - modules: static/css, templates/core
  - exemples: static/css/forms.css:117, templates/core/dashboard.html:123, templates/core/kpi_dashboard.html:192
- `rgba(33,136,171,.25)` — 3 fichiers / 3 usages, proprietes: background, border-color
  - modules: templates/hospitalisation, templates/medecins
  - exemples: templates/hospitalisation/chambres/list.html:164, templates/hospitalisation/list.html:176, templates/medecins/base.html:186
- `rgba(33,136,171,.3)` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/hospitalisation
  - exemples: templates/hospitalisation/chambres/list.html:163, templates/hospitalisation/deces/list.html:90, templates/hospitalisation/list.html:175
- `rgba(33,136,171,0.5)` — 3 fichiers / 3 usages, proprietes: border-color
  - modules: templates/gynecologie, templates/includes, templates/patients
  - exemples: templates/gynecologie/list.html:30, templates/includes/subheader.html:202, templates/patients/list.html:284
- `rgba(38,83,128,0.08)` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/employer
  - exemples: templates/employer/dashboard.html:268, templates/employer/detail.html:174, templates/employer/list.html:169
- `rgba(38,83,128,0.18)` — 3 fichiers / 3 usages, proprietes: background
  - modules: templates/employer
  - exemples: templates/employer/dashboard.html:138, templates/employer/list.html:54, templates/employer/organigramme.html:75

---

## 3. Palette semantique des badges de statut (recurrente sur ~20-40 templates)

Meme intention (etat metier), mais codee avec des variantes differentes selon les fichiers —
point de vigilance si vous unifiez le design system.

| Sens | Couleurs vues (fond / texte) | Modules typiques |
|---|---|---|
| Info / en attente (bleu) | `rgba(29,78,216,.18)` / `#93c5fd` | hospitalisation, soins |
| En cours (ambre) | `rgba(176,125,0,.2)` / `#e2c16a` | soins |
| Brouillon (ambre fonce) | `#3d2e00` / `#ffd666` (aussi `#f0c060`) | planning, base.html |
| Annule / erreur (rouge) | `rgba(185,28,28,.18)`, `rgba(220,38,38,.15)` / `#fca5a5`, `#f09090` | hospitalisation, soins, medecins |
| Paye / termine (vert) | `rgba(22,163,74,.15)`, `rgba(21,128,61,.2)` / `#86efac`, `#6eddb0` | hospitalisation, soins, services |
| Actif | `rgba(22,169,107,0.2)` / `#6eddb0` | services, employer |
| Inactif | `rgba(232,69,69,0.2)` / `#f09090` | services, employer |

⚠️ Risque repere : plusieurs pages (`presence/*.html`, certains formulaires `stock/*`) utilisent
le rouge `#c0392b` en dur pour les etats "danger", **sans variante pour le theme sombre** —
contraste probablement mauvais une fois le mode sombre active sur ces pages.

---

## 4. Couleurs specifiques a un module (1-2 fichiers) — 255 couleurs

Couleurs qui n'apparaissent que dans un module precis (souvent du CSS copie-colle plutot
que des variables partagees). Regroupees par module pour retrouver facilement "ou c'est utilise".

### static/css

- `rgba(255, 255, 255, 0.12)` — --border-strong — `html[data-theme="dark"]` — static/css/variables.css:73
- `rgba(255, 255, 255, 0.40)` — --text-muted — `html[data-theme="dark"]` — static/css/variables.css:73
- `rgba(255,255,255,0.02)` — background — `html[data-theme="dark"] .art-tabs-nav` — static/css/forms.css:143
- `rgba(255,255,255,0.6)` — color — `html[data-theme="dark"] .o-nav-link` — static/css/global.css:112
- `rgba(33,136,171,0.08)` — background — `html[data-theme="dark"] .btn-tfoot-add` — static/css/forms.css:272
- `rgba(33,136,171,0.22)` — background — `html[data-theme="dark"] .o-page-count` — static/css/global.css:434

### static/css + templates/base.html

- `#f0c070` — color — `html[data-theme="dark"] .alert-warning` — static/css/global.css:370, templates/base.html:301
- `rgba(232,154,26,0.12)` — background — `html[data-theme="dark"] .alert-warning` — static/css/global.css:370, templates/base.html:301
- `rgba(232,69,69,0.12)` — background — `html[data-theme="dark"] .alert-error` — static/css/global.css:369, templates/base.html:300
- `rgba(255,255,255,0.55)` — color — `html[data-theme="dark"] .form-group label` — static/css/global.css:407, templates/base.html:303
- `rgba(45,153,219,0.12)` — background — `html[data-theme="dark"] .alert-info` — static/css/global.css:371, templates/base.html:302

### static/css + templates/core

- `rgba(33,136,171,0.15)` — background — `html[data-theme="dark"] .o-filter-tag` — static/css/global.css:483, templates/core/kpi_dashboard.html:198

### static/css + templates/employer

- `rgba(232,69,69,0.1)` — background — `html[data-theme="dark"] .f-errors-summary` — static/css/forms.css:350, templates/employer/form.html:193
- `rgba(232,69,69,0.3)` — border-color — `html[data-theme="dark"] .f-errors-summary` — static/css/forms.css:350, templates/employer/dashboard.html:201
- `rgba(255,255,255,0.5)` — color — `html[data-theme="dark"] .o-nav-grid` — static/css/global.css:109, templates/employer/detail.html:234

### templates/base.html

- `#38b2d0` — border-bottom-color — `html[data-theme="dark"] .ts-wrapper.focus .ts-control` — templates/base.html:391
- `rgba(22,169,107,0.2)` — background — `html[data-theme="dark"] .badge-prescrit` — templates/base.html:343
- `rgba(232,154,26,0.2)` — background — `html[data-theme="dark"] .badge-brouillon` — templates/base.html:342

### templates/core

- `#5a8aaa` — --text-muted — `html[data-theme="dark"]` — templates/core/dashboard.html:123, templates/core/kpi_dashboard.html:192
- `#3a6a80` — color — `html[data-theme="dark"] .section-label` — templates/core/dashboard.html:140
- `#3d6e82` — color — `html[data-theme="dark"] .module-sub` — templates/core/dashboard.html:138
- `rgba(33,136,171,0.07)` — background — `html[data-theme="dark"] .module-card:hover` — templates/core/dashboard.html:139

### templates/employer

- `rgba(38,83,128,.15)` — background — `html[data-theme="dark"] .ann-service-tag` — templates/employer/annuaire.html:70, templates/employer/annuaire.html:86, templates/employer/annuaire.html:116, templates/employer/list.html:203
- `rgba(38,83,128,0.3)` — border-color, color — `html[data-theme="dark"] .rh-count-badge` — templates/employer/list.html:54, templates/employer/list.html:215, templates/employer/organigramme.html:75
- `#0b1828` — --rh-surface, background — `html[data-theme="dark"]` — templates/employer/base.html:43, templates/employer/conge_list.html:15
- `#b5d0e8` — --rh-text, color — `html[data-theme="dark"] .o-nav-link.active` — templates/employer/base.html:17, templates/employer/base.html:43
- `rgba(232,69,69,0.25)` — border-color — `html[data-theme="dark"] .rh-doc-badge` — templates/employer/dashboard.html:293, templates/employer/import.html:218
- `rgba(255,255,255,.12)` — background, border-color — `html[data-theme="dark"] .vue-btn.active` — templates/employer/annuaire.html:35, templates/employer/detail.html:259
- `rgba(255,255,255,0.28)` — color — `html[data-theme="dark"] .rh-name-cell .mat` — templates/employer/list.html:188, templates/employer/organigramme.html:212
- `rgba(38,83,128,0.07)` — background — `html[data-theme="dark"] .rh-exp-table tbody tr:hover` — templates/employer/dashboard.html:184, templates/employer/import.html:192
- `rgba(38,83,128,0.12)` — background — `html[data-theme="dark"] .btn-rh-template:hover` — templates/employer/import.html:93, templates/employer/import.html:117
- `rgba(38,83,128,0.25)` — color — `html[data-theme="dark"] .rh-empty-inline i` — templates/employer/dashboard.html:303, templates/employer/organigramme.html:211
- `#070e1c` — --rh-bg — `html[data-theme="dark"]` — templates/employer/base.html:43
- `#4d87be` — --primary — `html[data-theme="dark"]` — templates/employer/base.html:14
- `#5dd4a0` — color — `html[data-theme="dark"] .badge-cg.approuve` — templates/employer/conge_list.html:105
- `#7dabd4` — color — `html[data-theme="dark"] .badge-cg.en_cours` — templates/employer/conge_list.html:104
- `#f0dd80` — color — `html[data-theme="dark"] .badge-days-yellow` — templates/employer/dashboard.html:203
- `rgba(201,122,0,.15)` — background — `html[data-theme="dark"] .badge-cg.valide_service` — templates/employer/conge_list.html:106
- `rgba(22,169,107,.15)` — background — `html[data-theme="dark"] .badge-cg.approuve` — templates/employer/conge_list.html:105
- `rgba(22,169,107,.18)` — background — `html[data-theme="dark"] .cg-b-approuve` — templates/employer/detail.html:256
- `rgba(22,169,107,.3)` — border-color — `html[data-theme="dark"] .cg-b-approuve` — templates/employer/detail.html:256
- `rgba(22,169,107,0.15)` — background — `html[data-theme="dark"] .rh-stat-card.actif   .rh-stat-icon` — templates/employer/dashboard.html:80
- `rgba(22,169,107,0.25)` — border-color — `html[data-theme="dark"] .rh-all-good` — templates/employer/dashboard.html:317
- `rgba(220,53,69,.15)` — background — `html[data-theme="dark"] .badge-cg.refuse` — templates/employer/conge_list.html:108
- `rgba(232,154,26,.18)` — background — `html[data-theme="dark"] .cg-b-demande` — templates/employer/detail.html:255
- `rgba(232,154,26,.3)` — border-color — `html[data-theme="dark"] .cg-b-demande` — templates/employer/detail.html:255
- `rgba(232,154,26,0.15)` — background — `html[data-theme="dark"] .rh-stat-card.suspendu .rh-stat-icon` — templates/employer/dashboard.html:81
- `rgba(232,210,26,0.18)` — background — `html[data-theme="dark"] .badge-days-yellow` — templates/employer/dashboard.html:203
- `rgba(232,210,26,0.3)` — border-color — `html[data-theme="dark"] .badge-days-yellow` — templates/employer/dashboard.html:203
- `rgba(232,69,69,.18)` — background — `html[data-theme="dark"] .cg-b-refuse` — templates/employer/detail.html:257
- `rgba(232,69,69,.3)` — border-color — `html[data-theme="dark"] .cg-b-refuse` — templates/employer/detail.html:257
- `rgba(232,69,69,0.18)` — background — `html[data-theme="dark"] .badge-days-red` — templates/employer/dashboard.html:201
- `rgba(255,255,255,0.25)` — color — `html[data-theme="dark"] .rh-empty-inline p` — templates/employer/dashboard.html:304
- `rgba(38,83,128,.08)` — background — `html[data-theme="dark"] .org-service-header` — templates/employer/annuaire.html:82
- `rgba(38,83,128,.12)` — background — `html[data-theme="dark"] .o-nav-link.active` — templates/employer/base.html:17
- `rgba(38,83,128,.18)` — background — `html[data-theme="dark"] .ann-count` — templates/employer/annuaire.html:122
- `rgba(38,83,128,.3)` — border-color — `html[data-theme="dark"] .ann-count` — templates/employer/annuaire.html:122
- `rgba(38,83,128,0.06)` — background — `html[data-theme="dark"] .rh-file-zone` — templates/employer/import.html:113
- `rgba(38,83,128,0.14)` — background — `html[data-theme="dark"] .rh-docs-missing-item:hover` — templates/employer/dashboard.html:269
- `rgba(45,153,219,.18)` — background — `html[data-theme="dark"] .cg-b-en_cours` — templates/employer/detail.html:258
- `rgba(45,153,219,.3)` — border-color — `html[data-theme="dark"] .cg-b-en_cours` — templates/employer/detail.html:258
- `rgba(77,135,190,.15)` — background — `html[data-theme="dark"] .badge-cg.en_cours` — templates/employer/conge_list.html:104
- `rgba(77,135,190,0.08)` — background — `html[data-theme="dark"] .cg-table tbody tr:hover` — templates/employer/conge_list.html:76
- `rgba(77,135,190,0.1)` — background — `html[data-theme="dark"] .reg-table tbody tr:hover` — templates/employer/registre.html:57
- `rgba(77,135,190,0.18)` — --rh-border — `html[data-theme="dark"]` — templates/employer/base.html:43

### templates/employer + templates/ressources_humaines

- `#c0392b` — background, border-color — `html[data-theme="dark"] .btn-danger-sm:hover` — templates/employer/base.html:90, templates/ressources_humaines/base.html:156, templates/ressources_humaines/base.html:156
- `rgba(22,169,107,0.18)` — background — `html[data-theme="dark"] .badge-actif` — templates/employer/base.html:117, templates/ressources_humaines/base.html:216
- `rgba(22,169,107,0.3)` — border-color — `html[data-theme="dark"] .badge-actif` — templates/employer/base.html:117, templates/ressources_humaines/base.html:216
- `rgba(255,255,255,0.38)` — color — `html[data-theme="dark"] .rh-field .lbl` — templates/employer/base.html:150, templates/ressources_humaines/base.html:269

### templates/gynecologie

- `#151e2a` — background — `html[data-theme="dark"] .o-cal-day.empty` — templates/gynecologie/registre_naissance.html:252
- `#1e2d3d` — background — `html[data-theme="dark"] .o-cal-dow` — templates/gynecologie/registre_naissance.html:251
- `#2a3448` — border-bottom-color — `html[data-theme="dark"] .f-field` — templates/gynecologie/registre_naissance_form.html:15

### templates/gynecologie + templates/patients

- `#a0c8e0` — color — `html[data-theme="dark"] .pagination-pages a` — templates/gynecologie/list.html:222, templates/patients/list.html:248, templates/patients/list.html:254
- `#0f1b2b` — background — `html[data-theme="dark"] .patho-ms-search` — templates/gynecologie/rdv_form.html:354, templates/patients/rendez_vous_form.html:380
- `#1a3a50` — background — `html[data-theme="dark"] .pk-avatar` — templates/gynecologie/list.html:17, templates/patients/list.html:247
- `rgba(33,136,171,0.18)` — background — `html[data-theme="dark"] .patho-ms-item:hover` — templates/gynecologie/rdv_form.html:356, templates/patients/rendez_vous_form.html:382

### templates/gynecologie + templates/soins

- `rgba(0,0,0,0.3)` — box-shadow — `html[data-theme="dark"] .f-card` — templates/gynecologie/registre_naissance_form.html:14, templates/soins/form.html:12

### templates/hospitalisation

- `#0d1f32` — background — `html[data-theme="dark"] .saf-add-bar` — templates/hospitalisation/detail.html:431, templates/hospitalisation/detail.html:435, templates/hospitalisation/detail.html:437, templates/hospitalisation/detail.html:438
- `#0f2035` — background — `html[data-theme="dark"] .saf-tbl th` — templates/hospitalisation/detail.html:429, templates/hospitalisation/form.html:252, templates/hospitalisation/form.html:761
- `#0f1e30` — background — `html[data-theme="dark"] .det-card-title` — templates/hospitalisation/chambres/detail.html:64, templates/hospitalisation/deces/detail.html:58
- `#1a2d42` — background — `html[data-theme="dark"] .abtn-neutral` — templates/hospitalisation/chambres/detail.html:109, templates/hospitalisation/deces/detail.html:88
- `#1f3550` — background — `html[data-theme="dark"] .abtn-neutral:hover` — templates/hospitalisation/chambres/detail.html:110, templates/hospitalisation/deces/detail.html:89
- `#3d3d99` — background — `html[data-theme="dark"] .pip-step.active` — templates/hospitalisation/deces/form.html:202, templates/hospitalisation/form.html:92
- `#6ecdc2` — color — `html[data-theme="dark"] .stat-icon.teal` — templates/hospitalisation/list.html:167, templates/hospitalisation/list.html:185
- `#f48787` — color — `html[data-theme="dark"] .statut-btn.active.occupe` — templates/hospitalisation/chambres/form.html:195, templates/hospitalisation/chambres/list.html:170
- `rgba(21,136,171,.2)` — background — `html[data-theme="dark"] .equip-card.active .equip-icon` — templates/hospitalisation/chambres/form.html:200, templates/hospitalisation/form.html:998
- `rgba(29,78,216,.18)` — background — `html[data-theme="dark"] .stat-icon.blue` — templates/hospitalisation/list.html:165, templates/hospitalisation/list.html:183
- `rgba(33,136,171,.5)` — border-color — `html[data-theme="dark"] .o-filter-tag` — templates/hospitalisation/chambres/list.html:164, templates/hospitalisation/list.html:176
- `#0a2535` — background — `html[data-theme="dark"] .equip-card.active` — templates/hospitalisation/chambres/form.html:199
- `#0c1e30` — background — `html[data-theme="dark"] .saf-tbl tbody tr:hover td` — templates/hospitalisation/detail.html:430
- `#0d1f30` — background — `html[data-theme="dark"] .fc-auto-info` — templates/hospitalisation/deces/form.html:193
- `#0f2e48` — background — `html[data-theme="dark"] .pip-step.done` — templates/hospitalisation/detail.html:427
- `#1588ab` — border-color — `html[data-theme="dark"] .ev-note` — templates/hospitalisation/form.html:761
- `#1a2a3e` — background — `html[data-theme="dark"] .pip-step` — templates/hospitalisation/detail.html:426
- `#1e2d40` — background — `html[data-theme="dark"] .chip-none` — templates/hospitalisation/detail.html:432
- `#1e2d42` — background — `html[data-theme="dark"] .pip-step` — templates/hospitalisation/form.html:90
- `#6b7280` — color — `html[data-theme="dark"] .equip-non` — templates/hospitalisation/chambres/detail.html:108
- `#7a9ab5` — color — `html[data-theme="dark"] .salle-badge` — templates/hospitalisation/chambres/form.html:191
- `#7fd4ea` — color — `html[data-theme="dark"] .pip-step.done` — templates/hospitalisation/form.html:91
- `#9aa8b5` — color — `html[data-theme="dark"] .chip-none` — templates/hospitalisation/detail.html:432
- `#a8dff0` — color — `html[data-theme="dark"] .soins-tag` — templates/hospitalisation/form.html:998
- `#c4b5fd` — color — `html[data-theme="dark"] .badge-confirme` — templates/hospitalisation/list.html:182
- `rgba(107,114,128,.1)` — background — `html[data-theme="dark"] .equip-non` — templates/hospitalisation/chambres/detail.html:108
- `rgba(107,114,128,.18)` — background — `html[data-theme="dark"] .stat-icon.gray` — templates/hospitalisation/list.html:168
- `rgba(111,207,151,.12)` — background — `html[data-theme="dark"] .badge-dispo` — templates/hospitalisation/chambres/list.html:169
- `rgba(123,28,28,.3)` — background — `html[data-theme="dark"] .statut-btn.active.occupe` — templates/hospitalisation/chambres/form.html:195
- `rgba(14,67,88,.3)` — background — `html[data-theme="dark"] .dur-card` — templates/hospitalisation/detail.html:425
- `rgba(153,27,27,.15)` — background — `html[data-theme="dark"] .fc-code-badge` — templates/hospitalisation/deces/form.html:200
- `rgba(185,28,28,.18)` — background — `html[data-theme="dark"] .badge-annule` — templates/hospitalisation/list.html:186
- `rgba(22,163,74,.08)` — background — `html[data-theme="dark"] .saf-row-facture td` — templates/hospitalisation/form.html:1356
- `rgba(244,135,135,.12)` — background — `html[data-theme="dark"] .badge-occupe` — templates/hospitalisation/chambres/list.html:170
- `rgba(252,165,165,.3)` — border-color — `html[data-theme="dark"] .fc-code-badge` — templates/hospitalisation/deces/form.html:200
- `rgba(255,255,255,.28)` — color — `html[data-theme="dark"] .pip-step` — templates/hospitalisation/detail.html:426
- `rgba(26,107,60,.25)` — background — `html[data-theme="dark"] .equip-oui` — templates/hospitalisation/chambres/detail.html:107
- `rgba(26,107,60,.3)` — background — `html[data-theme="dark"] .statut-btn.active.dispo` — templates/hospitalisation/chambres/form.html:194
- `rgba(26,92,74,.22)` — background — `html[data-theme="dark"] .badge-termine` — templates/hospitalisation/list.html:185
- `rgba(33,136,171,.1)` — background — `html[data-theme="dark"] .o-nav-drop-item:hover` — templates/hospitalisation/base.html:76
- `rgba(56,178,208,.3)` — border-color — `html[data-theme="dark"] .soins-tag` — templates/hospitalisation/form.html:998
- `rgba(6,95,70,.22)` — background — `html[data-theme="dark"] .badge-decharge` — templates/hospitalisation/list.html:184
- `rgba(6,95,70,.25)` — background — `html[data-theme="dark"] .stat-icon.green` — templates/hospitalisation/list.html:166
- `rgba(91,33,182,.18)` — background — `html[data-theme="dark"] .badge-confirme` — templates/hospitalisation/list.html:182

### templates/hospitalisation + templates/medecins

- `rgba(33,136,171,.12)` — background — `html[data-theme="dark"] .src-chip` — templates/hospitalisation/detail.html:433, templates/medecins/base.html:186

### templates/hospitalisation + templates/services

- `rgba(0,0,0,.4)` — box-shadow — `html[data-theme="dark"] .o-nav-dropdown` — templates/hospitalisation/base.html:69, templates/services/includes/io_styles.html:54

### templates/hospitalisation + templates/soins

- `rgba(255,255,255,.025)` — background — `html[data-theme="dark"] .fac-ro-table tbody td` — templates/hospitalisation/facturation/detail.html:135, templates/hospitalisation/facturation/detail.html:136, templates/soins/facturation/detail.html:136, templates/soins/facturation/detail.html:137
- `#6ee7b7` — color — `html[data-theme="dark"] .stat-icon.green` — templates/hospitalisation/list.html:166, templates/hospitalisation/list.html:184, templates/soins/includes/statut_css.html:90
- `#9ca3af` — background, color — `html[data-theme="dark"] .stat-icon.gray` — templates/hospitalisation/list.html:168, templates/soins/includes/statut_css.html:123
- `rgba(107,114,128,.4)` — border-color — `html[data-theme="dark"] .fac-chip-brouillon` — templates/hospitalisation/facturation/detail.html:49, templates/soins/facturation/detail.html:50
- `rgba(22,163,74,.15)` — background — `html[data-theme="dark"] .fac-chip-payee` — templates/hospitalisation/facturation/detail.html:51, templates/soins/facturation/detail.html:52
- `rgba(22,163,74,.35)` — border-color — `html[data-theme="dark"] .fac-chip-payee` — templates/hospitalisation/facturation/detail.html:51, templates/soins/facturation/detail.html:52
- `rgba(220,38,38,.12)` — background — `html[data-theme="dark"] .fac-alert-error` — templates/hospitalisation/facturation/edit.html:156, templates/soins/facturation/edit.html:157
- `rgba(220,38,38,.3)` — border-color — `html[data-theme="dark"] .fac-alert-error` — templates/hospitalisation/facturation/edit.html:156, templates/soins/facturation/edit.html:157
- `rgba(34,137,107,.07)` — background — `html[data-theme="dark"] .fac-lignes-table tbody tr:hover td` — templates/hospitalisation/facturation/edit.html:103, templates/soins/facturation/edit.html:104
- `rgba(37,99,235,.15)` — background — `html[data-theme="dark"] .fac-chip-emise` — templates/hospitalisation/facturation/detail.html:50, templates/soins/facturation/detail.html:51
- `rgba(37,99,235,.35)` — border-color — `html[data-theme="dark"] .fac-chip-emise` — templates/hospitalisation/facturation/detail.html:50, templates/soins/facturation/detail.html:51

### templates/laboratoire + templates/patients

- `#0b1929` — --bg — `html[data-theme="dark"]` — templates/laboratoire/list.html:15, templates/patients/rendez_vous.html:16

### templates/medecins

- `#2dd4bf` — color — `html[data-theme="dark"] .page-icon` — templates/medecins/config/specialites_list.html:10, templates/medecins/config/specialites_list.html:16, templates/medecins/config/specialites_list.html:19
- `rgba(13,148,136,.2)` — background — `html[data-theme="dark"] .page-icon` — templates/medecins/config/specialites_list.html:10, templates/medecins/config/specialites_list.html:16, templates/medecins/config/specialites_list.html:19
- `#4a90d9` — border-color — `html[data-theme="dark"] .o-card:hover` — templates/medecins/base.html:152
- `rgba(34,113,177,0.1)` — background — `html[data-theme="dark"] .o-nav-dropdown-menu a:hover` — templates/medecins/base.html:26

### templates/medecins + templates/soins

- `rgba(255,255,255,.18)` — border-bottom-color, border-color — `html[data-theme="dark"] .md-input` — templates/medecins/form.html:68, templates/soins/form.html:51

### templates/planning

- `#ff8a80` — color — `html[data-theme="dark"] .alert-error` — templates/planning/bureaux.html:29, templates/planning/modifier.html:111, templates/planning/modifier.html:142
- `#0a0820` — --bg — `html[data-theme="dark"]` — templates/planning/base.html:43
- `#100c2e` — --surface — `html[data-theme="dark"]` — templates/planning/base.html:43
- `#1a2717` — background — `html[data-theme="dark"] .med-modal` — templates/planning/modifier.html:78
- `#2a2600` — background — `html[data-theme="dark"] .td-cell.search-match` — templates/planning/hebdomadaire.html:79
- `#8f7de0` — --primary — `html[data-theme="dark"]` — templates/planning/base.html:14
- `#b3a8ed` — color — `html[data-theme="dark"] .o-nav-link.active` — templates/planning/base.html:17
- `#b71c1c` — border-color — `html[data-theme="dark"] .alert-error` — templates/planning/bureaux.html:29
- `#d5d0f5` — --text — `html[data-theme="dark"]` — templates/planning/base.html:43
- `#f9a825` — outline-color — `html[data-theme="dark"] .td-cell.search-match` — templates/planning/hebdomadaire.html:79
- `#ffab40` — color — `html[data-theme="dark"] .pl-alerte-btn:hover` — templates/planning/base.html:142
- `#ffd180` — color — `html[data-theme="dark"] .pl-alerte-btn` — templates/planning/base.html:141
- `rgba(143,125,224,0.18)` — --border — `html[data-theme="dark"]` — templates/planning/base.html:43
- `rgba(192,57,43,0.2)` — background — `html[data-theme="dark"] .chip-x:hover` — templates/planning/modifier.html:142
- `rgba(74,103,65,0.25)` — box-shadow — `html[data-theme="dark"] .db-week-card.current` — templates/planning/dashboard.html:32
- `rgba(88,67,190,.12)` — background — `html[data-theme="dark"] .o-nav-link.active` — templates/planning/base.html:17

### templates/presence

- `rgba(14,107,137,.1)` — background — `html[data-theme="dark"] .week-pill` — templates/presence/parametres.html:48, templates/presence/parametres.html:141
- `#091c28` — --pr-surface — `html[data-theme="dark"]` — templates/presence/base.html:35
- `#30a8cc` — --primary — `html[data-theme="dark"]` — templates/presence/base.html:16
- `#70cee2` — color — `html[data-theme="dark"] .o-nav-link.active` — templates/presence/base.html:19
- `#b0e4f2` — --pr-text — `html[data-theme="dark"]` — templates/presence/base.html:35
- `rgba(14,107,137,.04)` — background — `html[data-theme="dark"] .pm-table tbody tr:nth-child(even)` — templates/presence/parametres.html:124
- `rgba(14,107,137,.07)` — background — `html[data-theme="dark"] .pm-table tbody tr:hover` — templates/presence/parametres.html:122
- `rgba(14,107,137,.12)` — background — `html[data-theme="dark"] .o-nav-link.active` — templates/presence/base.html:19
- `rgba(48,168,204,0.18)` — --pr-border — `html[data-theme="dark"]` — templates/presence/base.html:35

### templates/ressources_humaines

- `#0b1209` — --rh-bg — `html[data-theme="dark"]` — templates/ressources_humaines/base.html:31
- `#0e1428` — background — `html[data-theme="dark"] .rh-input` — templates/ressources_humaines/base.html:291
- `#111c0e` — --rh-surface — `html[data-theme="dark"]` — templates/ressources_humaines/base.html:31
- `#c0d9b0` — --rh-text — `html[data-theme="dark"]` — templates/ressources_humaines/base.html:31
- `rgba(107,128,217,0.18)` — box-shadow — `html[data-theme="dark"] .rh-input:focus` — templates/ressources_humaines/base.html:296
- `rgba(122,170,98,0.18)` — --rh-border — `html[data-theme="dark"]` — templates/ressources_humaines/base.html:31

### templates/services

- `#2d3f58` — background, border-color — `html[data-theme="dark"] .io-nav-menu` — templates/services/base.html:161, templates/services/base.html:168, templates/services/includes/io_styles.html:54, templates/services/includes/io_styles.html:61 (+3 autres usages)
- `rgba(255, 255, 255, .1)` — border-color — `html[data-theme="dark"] .config-search` — templates/services/includes/list_css.html:539, templates/services/includes/list_css.html:549, templates/services/includes/list_css.html:603, templates/services/includes/list_css.html:614 (+2 autres usages)
- `rgba(255, 255, 255, .35)` — color — `html[data-theme="dark"] .config-count` — templates/services/includes/list_css.html:545, templates/services/includes/list_css.html:554, templates/services/includes/list_css.html:579, templates/services/includes/list_css.html:603 (+2 autres usages)
- `rgba(33, 136, 171, .15)` — background, box-shadow — `html[data-theme="dark"] .art-type-chip:has(input:checked)` — templates/services/includes/article_form_css.html:191, templates/services/includes/article_form_css.html:297, templates/services/includes/list_css.html:598, templates/services/includes/list_css.html:609 (+1 autres usages)
- `#c8d8e8` — color — `html[data-theme="dark"] .io-nav-row` — templates/services/base.html:169, templates/services/base.html:170, templates/services/includes/io_styles.html:62, templates/services/includes/io_styles.html:202
- `rgba(255, 255, 255, .03)` — background — `html[data-theme="dark"] .art-photo-zone` — templates/services/includes/article_form_css.html:292, templates/services/includes/article_form_css.html:514, templates/services/includes/list_css.html:579, templates/services/includes/list_css.html:668
- `#1a2640` — background — `html[data-theme="dark"] .io-nav-menu` — templates/services/base.html:161, templates/services/includes/io_styles.html:54, templates/services/includes/io_styles.html:200
- `#243450` — background — `html[data-theme="dark"] .io-nav-item:hover` — templates/services/base.html:171, templates/services/includes/io_styles.html:63, templates/services/includes/io_styles.html:217
- `#7ec8e3` — color — `html[data-theme="dark"] .io-nav-item:hover` — templates/services/base.html:171, templates/services/includes/io_styles.html:63, templates/services/includes/io_styles.html:216
- `#111e30` — background — `html[data-theme="dark"] .io-modal-header` — templates/services/includes/io_styles.html:202, templates/services/includes/io_styles.html:207
- `#3a4a5e` — background — `html[data-theme="dark"] .o-avatar` — templates/services/consommables/list.html:154, templates/services/list.html:184
- `#6a8aaa` — color — `html[data-theme="dark"] .io-section-label` — templates/services/base.html:167, templates/services/includes/io_styles.html:60
- `#fb923c` — color — `html[data-theme="dark"] .det-badge-warn` — templates/services/consommables/detail.html:74, templates/services/consommables/list.html:218
- `rgba(255, 255, 255, .04)` — background, border-bottom-color — `html[data-theme="dark"] .o-btn-secondary:hover` — templates/services/includes/form_css.html:288, templates/services/includes/list_css.html:585
- `rgba(255, 255, 255, .07)` — background, border-bottom-color — `html[data-theme="dark"] .config-table thead th` — templates/services/includes/list_css.html:579, templates/services/includes/list_css.html:681
- `rgba(255, 255, 255, .08)` — border-bottom-color, border-top-color — `html[data-theme="dark"] .drawer-header` — templates/services/includes/list_css.html:668, templates/services/includes/list_css.html:693
- `rgba(255, 255, 255, .2)` — color — `html[data-theme="dark"] .field-ul::placeholder` — templates/services/includes/form_css.html:62, templates/services/includes/form_css.html:625
- `rgba(255, 255, 255, .6)` — color — `html[data-theme="dark"] .btn-modal-cancel` — templates/services/includes/list_css.html:658, templates/services/includes/list_css.html:697
- `rgba(255, 255, 255, 0.1)` — border-right-color — `html[data-theme="dark"] .module-nav-brand` — templates/services/base.html:72, templates/services/includes/layout_css.html:139
- `#0a2a14` — background — `html[data-theme="dark"] .io-fmt-xlsx` — templates/services/base.html:175
- `#0a2a18` — background — `html[data-theme="dark"] .io-fmt-csv` — templates/services/base.html:174
- `#1a5a30` — border-color — `html[data-theme="dark"] .io-fmt-xlsx` — templates/services/base.html:175
- `#1a5a3a` — border-color — `html[data-theme="dark"] .io-fmt-csv` — templates/services/base.html:174
- `#1e3050` — background — `html[data-theme="dark"] .io-file-label:hover` — templates/services/includes/io_styles.html:215
- `#2d4a68` — border-color — `html[data-theme="dark"] .io-file-label` — templates/services/includes/io_styles.html:211
- `#2d5a80` — border-color — `html[data-theme="dark"] .io-filename` — templates/services/includes/io_styles.html:216
- `#3a2800` — background — `html[data-theme="dark"] .io-fmt-json` — templates/services/base.html:173
- `#3a5070` — border-color — `html[data-theme="dark"] .io-btn-cancel` — templates/services/includes/io_styles.html:217
- `#4a90b8` — border-color — `html[data-theme="dark"] .io-file-label:hover` — templates/services/includes/io_styles.html:215
- `#5a80a0` — color — `html[data-theme="dark"] .io-nav-item i` — templates/services/base.html:172
- `#6ecfa0` — color — `html[data-theme="dark"] .io-fmt-csv` — templates/services/base.html:174
- `#7a5800` — border-color — `html[data-theme="dark"] .io-fmt-json` — templates/services/base.html:173
- `#82c89a` — color — `html[data-theme="dark"] .io-fmt-xlsx` — templates/services/base.html:175
- `#8ab0d0` — color — `html[data-theme="dark"] .io-file-label` — templates/services/includes/io_styles.html:211
- `#a8c0d8` — color — `html[data-theme="dark"] .io-btn-cancel` — templates/services/includes/io_styles.html:217
- `#dc2626` — border-left-color — `html[data-theme="dark"] .f-danger` — templates/services/includes/form_css.html:380
- `#f5c97a` — color — `html[data-theme="dark"] .io-fmt-json` — templates/services/base.html:173
- `rgba(0, 0, 0, .4)` — box-shadow — `html[data-theme="dark"] .ss-dropdown` — templates/services/includes/form_css.html:633
- `rgba(194, 65, 12, 0.2)` — background — `html[data-theme="dark"] .badge-stock-low` — templates/services/consommables/list.html:218
- `rgba(255, 255, 255, .06)` — background — `html[data-theme="dark"] .vue-toggle` — templates/services/includes/list_css.html:549
- `rgba(255, 255, 255, .4)` — color — `html[data-theme="dark"] .drawer-close` — templates/services/includes/list_css.html:677
- `rgba(255, 255, 255, .5)` — color — `html[data-theme="dark"] .modal-msg` — templates/services/includes/list_css.html:654
- `rgba(255, 255, 255, 0.08)` — background — `html[data-theme="dark"] .o-nav-grid:hover` — templates/services/includes/layout_css.html:134
- `rgba(255, 255, 255, 0.5)` — color — `html[data-theme="dark"] .o-nav-grid` — templates/services/includes/layout_css.html:130
- `rgba(255, 255, 255, 0.6)` — color — `html[data-theme="dark"] .o-nav-link` — templates/services/includes/layout_css.html:144
- `rgba(33, 136, 171, .06)` — background — `html[data-theme="dark"] .config-table tbody tr:hover` — templates/services/includes/list_css.html:590
- `rgba(33, 136, 171, .08)` — background — `html[data-theme="dark"] .art-photo-zone:hover` — templates/services/includes/article_form_css.html:297
- `rgba(33, 136, 171, .1)` — background — `html[data-theme="dark"] .col-picker-item:hover` — templates/services/includes/list_css.html:623
- `rgba(33, 136, 171, .2)` — background — `html[data-theme="dark"] .f-code-badge` — templates/services/includes/form_css.html:307
- `rgba(33, 136, 171, .25)` — background — `html[data-theme="dark"] .vue-btn.active` — templates/services/includes/list_css.html:559
- `rgba(33, 136, 171, 0.1)` — background — `html[data-theme="dark"] .o-nav-link.active` — templates/services/includes/layout_css.html:148

### templates/services + templates/soins

- `#1a2133` — background — `html[data-theme="dark"] .filters-panel` — templates/services/list.html:62, templates/soins/procedure/list.html:13
- `#21283a` — --surface — `html[data-theme="dark"]` — templates/services/includes/layout_css.html:19, templates/soins/includes/layout_css.html:14
- `rgba(194,65,12,.2)` — background — `html[data-theme="dark"] .det-badge-warn` — templates/services/consommables/detail.html:74, templates/soins/includes/statut_css.html:93

### templates/soins

- `rgba(20,87,112,.2)` — background — `html[data-theme="dark"] .stat-icon.blue` — templates/soins/list.html:169, templates/soins/procedure/list.html:65
- `rgba(34,137,107,.3)` — background — `html[data-theme="dark"] .pipeline-step.done .step-num` — templates/soins/form.html:140, templates/soins/includes/statut_css.html:37
- `#3b82f6` — background — `html[data-theme="dark"] .badge-en-attente::before` — templates/soins/includes/statut_css.html:125
- `#4aaa87` — border-bottom-color — `html[data-theme="dark"] .o-nav-link.active` — templates/soins/includes/layout_css.html:92
- `#cbd5e1` — color — `html[data-theme="dark"] .stp-step[data-val="brouillon"].stp-active` — templates/soins/includes/statut_css.html:91
- `#fdba74` — color — `html[data-theme="dark"] .stp-step[data-val="en_cours"].stp-active` — templates/soins/includes/statut_css.html:93
- `rgba(100,116,139,.22)` — background — `html[data-theme="dark"] .stp-step[data-val="brouillon"].stp-active` — templates/soins/includes/statut_css.html:91
- `rgba(176,125,0,.25)` — background — `html[data-theme="dark"] .badge-paye-terminer .part-cours` — templates/soins/list.html:96
- `rgba(176,125,0,.4)` — border-color — `html[data-theme="dark"] .det-alerte` — templates/soins/detail.html:155
- `rgba(185,28,28,.22)` — background — `html[data-theme="dark"] .stp-annule.stp-active` — templates/soins/includes/statut_css.html:95
- `rgba(21,128,61,.2)` — background — `html[data-theme="dark"] .stp-step[data-val="termine"].stp-active` — templates/soins/includes/statut_css.html:94
- `rgba(255,255,255,.5)` — color — `html[data-theme="dark"] .o-nav-grid` — templates/soins/includes/layout_css.html:88
- `rgba(255,255,255,.6)` — color — `html[data-theme="dark"] .o-nav-link` — templates/soins/includes/layout_css.html:91
- `rgba(26,92,74,.3)` — background — `html[data-theme="dark"] .badge-paye-terminer .part-terme` — templates/soins/list.html:95
- `rgba(29,78,216,.2)` — background — `html[data-theme="dark"] .badge-programme` — templates/soins/procedure/list.html:44
- `rgba(29,78,216,.22)` — background — `html[data-theme="dark"] .stp-step[data-val="en_attente_de_paiement"...` — templates/soins/includes/statut_css.html:92
- `rgba(34,137,107,.1)` — background — `html[data-theme="dark"] .o-nav-link.active` — templates/soins/includes/layout_css.html:92
- `rgba(34,137,107,.2)` — background — `html[data-theme="dark"] .o-dd-item:hover` — templates/soins/list.html:46
- `rgba(34,137,107,.25)` — background — `html[data-theme="dark"] .o-dd-item.active` — templates/soins/list.html:47
- `rgba(5,150,105,.18)` — background — `html[data-theme="dark"] .stp-step.stp-done` — templates/soins/includes/statut_css.html:90
- `rgba(59,130,246,.2)` — background — `html[data-theme="dark"] .badge-en-attente` — templates/soins/includes/statut_css.html:124

### templates/stock

- `#90caf9` — color — `html[data-theme="dark"] .st-info-box` — templates/stock/transfert/form.html:39
- `rgba(154,184,138,.08)` — background — `html[data-theme="dark"] .st-nav-link:hover` — templates/stock/base.html:54
- `rgba(154,184,138,.1)` — background — `html[data-theme="dark"] .st-nav-link.active` — templates/stock/base.html:55
- `rgba(45,153,219,.12)` — background — `html[data-theme="dark"] .st-info-box` — templates/stock/transfert/form.html:39

### templates/utilisateur

- `#0f1f0b` — background — `html[data-theme="dark"] .cpt-card` — templates/utilisateur/mon_compte.html:17
- `#d0e8c0` — color — `html[data-theme="dark"] .cpt-input` — templates/utilisateur/mon_compte.html:34
- `rgba(154,184,138,.12)` — border-bottom-color — `html[data-theme="dark"] .cpt-card-head` — templates/utilisateur/mon_compte.html:22
- `rgba(154,184,138,.15)` — border-color — `html[data-theme="dark"] .cpt-card` — templates/utilisateur/mon_compte.html:17
- `rgba(154,184,138,.25)` — border-bottom-color — `html[data-theme="dark"] .cpt-input` — templates/utilisateur/mon_compte.html:34

---

## Constats generaux

1. **Pas de media-query `prefers-color-scheme: dark`** : le mode sombre depend entierement
   du toggle JS + `localStorage`, jamais de la preference systeme.
2. **Forte duplication des "bleus marine" de fond de carte** : `#0d2035`, `#0f3050`, `#1a2535`,
   `#132033`, `#151e2a`, `#1a3050`, `#28304a`, `#2a3548`... sont tous des variations d'un meme
   "fond de panneau sombre", au lieu de tous consommer `var(--surface)`.
3. **Meme chose pour les bordures** : de nombreuses variantes de `rgba(255,255,255,0.0X)` avec
   des alpha legerement differents (0.02 a 0.15) pour la meme intention visuelle.
4. Les ~100 fichiers `templates/**/*.html` qui redefinissent ces couleurs en inline `<style>`
   sont la source principale de la derive — `static/css/global.css` et `static/css/forms.css`
   couvrent deja une bonne partie des composants communs (cartes, tableaux, formulaires).
