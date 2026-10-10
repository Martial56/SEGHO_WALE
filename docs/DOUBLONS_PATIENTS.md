# Doublons patients — contexte, décisions et plan de travail

> Document de passation pour Claude Code (VS Code). Il résume une longue
> discussion menée sur claude.ai : ce qui a été essayé, ce qui a échoué, ce qui
> a été validé, et ce qu'il reste à faire. **À lire en entier avant de toucher
> au code.** Les échanges avec l'utilisateur se font en français, phrases
> courtes, une étape à la fois : il valide chaque étape avant la suivante.

---

## 1. Objectif

Dans le projet Django **SEGHO-WALÉ** (gestion de centre de santé, Côte d'Ivoire) :

1. **Empêcher** la création de fiches patients en double (formulaire, import Excel, passerelle HPRIM).
2. **Détecter** les doublons déjà présents en base.
3. Offrir un **menu « Doublons »** dans le module Patients pour les traiter : fusionner, déclarer « pas un doublon », masquer.
4. **Ne jamais perdre de données** : une fusion déplace les liens, ne supprime rien, est journalisée et annulable.

Le projet de dev actuel sert de **base de test propre** pour implémenter tout cela.

---

## 2. Historique (pour ne pas refaire les mêmes erreurs)

1. Point de départ : la bibliothèque Kotlin *duplicate-finder* (similarité par
   n-grammes sur de longs textes). Jugée inadaptée telle quelle à des fiches
   courtes et structurées ; on n'en a gardé que l'idée de « similarité de chaînes ».
2. Une première version de `patients/doublons.py` a été écrite (score pondéré
   champ par champ), avec un script `tester_doublons_excel.py` qui lit un
   Excel de patients et produit un rapport Excel.
3. **Premier rapport sur 48 091 patients : échec complet.** 877 142 paires,
   un groupe unique de 37 579 patients classé « quasi certain ». Causes :
   - **Dates fausses.** L'import calcule la date de naissance à partir de l'âge
     et du jour de l'import (« 34 ans » importé le 30/09/2026 → né le
     30/09/1992). 89 % des fiches avaient donc le même jour/mois, ce qui
     produisait de fausses « mêmes dates » et de fausses « fautes de frappe
     sur l'année ».
   - **Noms trop tolérants.** KOUASSI, KOFFI, YAO, AMOIN, AYA… reviennent des
     milliers de fois ; la moyenne Jaro-Winkler rendait « KOFFI AYA BELINA » et
     « KOFFI AYA MADELEINE » proches à 93 %.
   - **Regroupement en chaîne** (union-find : A~B et B~C ⇒ A,B,C ensemble).
   - **Tests trompeurs** : la simulation ne mesurait que le rappel, jamais
     les fausses alertes.
4. **L'utilisateur a corrigé lui-même** `doublons.py` et le script (version v2,
   qui fait foi — voir §4). Résultats v2 sur le fichier Excel :
   - 942 groupes quasi certains (926 de 2 fiches, 16 de 3), 958 fiches en trop (2 %).
   - **Précision vérifiée à la main : 306 Oui / 0 Non / 2 « En partie » sur 308 groupes**,
     dont 254 dans la tranche la plus difficile (85–89 %).
   - Simulation : 596/600 faux doublons retrouvés (les 4 manqués sont des
     artefacts du générateur de variantes, ex. « KAUUAKOU »).
   - « À vérifier » : 38/38 Oui, dont 19 entre 65 et 68 % → cette zone
     contient beaucoup de vrais doublons (à confirmer sur un échantillon au hasard).
5. Un ancien patch (`doublons_patients.zip` / `.patch`) avait été proposé
   (formulaire, vue JSON de vérification en direct, commande de détection,
   tests). **Il est obsolète** : il embarque l'ancien `doublons.py`. On peut
   s'en inspirer pour l'intégration (formulaire, endpoint, gabarit), mais avec
   le `doublons.py` v2 de l'utilisateur.

---

## 3. État du projet dev (analysé, rien modifié)

- **47 813 patients**, tous dans le centre 1.
- **89 % des dates de naissance au 01/10** (dernier import fait un 1er octobre ;
  au fichier précédent c'était le 30/09). La « date par défaut » change à chaque import.
- `patients/doublons.py` **n'est pas encore dans le projet**.
- Avec l'algorithme v2 de l'utilisateur, sur cette base :
  - **935 groupes quasi certains**, **7 564 paires à vérifier**, 0 groupe avec sexes différents.
  - Données rattachées aux 935 groupes : 539 groupes sans aucune donnée,
    341 où une seule fiche a des données, **55 où au moins deux fiches en ont**
    (seuls cas qui demandent vraiment de déplacer des lignes).
  - Analyse complète : ~110 s en Python pur.

### 3.1 Tables liées à `Patient` (13 FK, relevées par introspection Django)

| Modèle | Champ | on_delete | Lignes en base dev |
|---|---|---|---|
| patients.RendezVous | patient | CASCADE | 12 000 |
| patients.Naissance | mere | CASCADE | 0 |
| consultations.Consultation | patient | CASCADE | 0 |
| consultations.Ordonnance | patient | SET_NULL | 0 |
| pharmacie.VentePharmacie | patient | SET_NULL | 0 |
| laboratoire.AnalyseLaboratoire | patient | CASCADE | 0 |
| laboratoire.DemandeExamen | patient | CASCADE | 4 500 |
| laboratoire.ExamenImagerie | patient | CASCADE | 0 |
| hospitalisation.Hospitalisation | patient | CASCADE | 0 |
| hospitalisation.RegistreDeces | patient | PROTECT | 0 |
| facturation.Facture | patient | CASCADE | 8 088 |
| soins.Soin | patient | CASCADE | 5 000 |
| soins.ProcedureSoin | patient | CASCADE | 9 261 |

⇒ **Ne jamais supprimer une fiche patient** : 10 cascades détruiraient l'historique.

Références « cachées » (pas de FK) :
- `core.LogActivite` : relation générique (`content_type` + `object_id`). L'historique doit suivre la fusion.
- `blockchain_bridge` : `code_patient` en texte, preuve déjà ancrée → **ne jamais réécrire**.
- `laboratoire/hprim/integration.py` : retrouve le patient par `code_patient`, puis par `nom__iexact` + `prenoms__iexact`.

**Aucune contrainte d'unicité** ne porte sur le patient dans les tables liées :
déplacer les lignes ne crée pas de conflit (à confirmer par un test).

### 3.2 D'où viennent les doublons (code actuel)

- `patients/forms.py`, `PatientForm.clean()` : refuse seulement si nom, prénoms,
  date **et** téléphone sont strictement identiques. Une faute suffit à passer.
- `patients/views.py` : import Excel en tâche de fond (`_executer_import_patients`).
  - `_parse_age_to_date(v, today)` calcule la date depuis l'âge et **le jour de l'import**.
  - Rapprochement par `_cle_identite` = (date exacte, nom normalisé, prénoms normalisés)
    ⇒ un réimport un autre jour ne reconnaît plus personne.
  - Si le nom complet n'a qu'un mot, `prenoms = nom` (« KOFFI » → nom KOFFI, prénoms KOFFI).
- HPRIM : correspondance exacte sur nom/prénoms.

### 3.3 Points techniques utiles

- `Patient(ModeleCentre)` : `objects` est filtré sur le centre actif
  (thread-local, `core.middleware`), `all_objects` non filtré. Dans un fil
  d'exécution ou une commande, filtrer explicitement par centre.
- `date_naissance = DateField(db_index=True)`, `code_patient` unique tous centres confondus.
- `ancien_identifiant` : CharField(50), une seule valeur → ne suffit pas à
  garder la trace des codes fusionnés.
- Journal : `core.views.log_event(instance, user, message, type='note', ...)`.
- Tests : `python manage.py test patients` (suite existante ~80 tests, ~3 min).

---

## 4. L'algorithme de référence (version v2 de l'utilisateur)

Fichiers fournis par l'utilisateur (ils font foi) : `doublons.py` et
`tester_doublons_excel.py`. À placer respectivement dans `patients/doublons.py`
et à la racine du projet (ou `scripts/`).

### Score sur 100

| Critère | Points |
|---|---|
| Nom + prénoms | 50 × similarité |
| Date de naissance | 30 × similarité |
| Même téléphone (principal ou secondaire, tout format, normalisé sur 10 chiffres) | +15 |
| Sexe identique / différent | +5 / −15 |
| Garde-fou : similarité des noms < 0,75 | score plafonné à 64 |

Seuils (réglables dans `settings.py`) : **≥ 85 blocage**, **65–84 avertissement**.

### Noms
Normalisation (majuscules, sans accents, apostrophes supprimées), clé
phonétique adaptée aux noms ivoiriens (Kouassi/Kwassi, N'Guessan/Guessan,
Yao/Yaho, Christelle/Cristel), Jaro-Winkler. Comparaison par ensembles de mots
(indifférente à l'ordre) ; **un mot sans équivalent (< 0,85) est écrasé (score³)**,
ce qui sépare les membres d'une même famille ; prénom manquant ×0,93 ; on
prend le meilleur entre « champ par champ » et « tout mélangé ×0,97 ».

### Dates
- Date exacte = 1,0 ; jour/mois inversés = 0,85 ; une seule composante différente = 0,75/0,6…
- **Date approximative** (âge converti ou jour/mois « par défaut ») : on ne
  compare que l'année → ≤ 200 j : 0,6 ; ≤ 400 j : 0,35 ; sinon 0.
- Aujourd'hui, les dates par défaut viennent de `DOUBLONS_PATIENTS_DATES_PAR_DEFAUT`
  (défaut `[(1, 1)]`) côté app, et sont **détectées automatiquement** côté script
  (jour/mois porté par ≥ 2 % des fiches). Voir étape 1 : on remplace cela par un champ.

### Regroupement (script)
Sans effet de chaîne : on fusionne deux groupes seulement si **chaque** fiche
ressemble à **chaque** autre (≥ 85), 8 fiches max. Les liens refusés vont
dans « À vérifier ». Fiche « ★ à garder » suggérée : la plus complète, puis la plus ancienne.

### Problèmes connus de l'algorithme, à traiter
1. **Jumeaux** : N'GORAN KOUASSI N'DA JEAN NATHANAEL / N'GORAN KOUAME N'DA JEAN
   EMMANUEL, même jour, même téléphone → 93 % ⇒ seraient **bloqués**. Règle à
   ajouter : si **chaque** fiche a au moins un prénom sans équivalent dans
   l'autre, plafonner sous le seuil de blocage (confirmation au lieu de blocage).
2. **Performance** de `_preselection` dans l'app : un `OR` large (année ±1,
   `icontains` sur 3 lettres, téléphone) ramène des milliers de fiches sur
   48 000 → trop lent pour une vérification en direct. À resserrer (clés
   combinées, comme `_cles()` du script) et à mesurer.
3. Un nom complet d'un seul mot donne `prenoms = nom` à l'import : à garder en tête.

---

## 5. Décisions prises avec l'utilisateur

### Prévention à la création
- **Pendant la saisie** : dès que nom/date/téléphone changent, un encadré
  « Ce patient existe peut-être déjà » liste les fiches proches avec un bouton
  **Ouvrir cette fiche** (endpoint JSON + JS, déclenchement avec un délai de 500 ms).
- **À l'enregistrement** :
  - ≥ 85 : création refusée, message « Ouvrez la fiche existante » ;
    seul un administrateur peut forcer, avec case à cocher + raison obligatoire, tracé au journal.
  - 65–84 : case « J'ai vérifié, c'est une autre personne » obligatoire.
  - < 65 : création normale.
  - En **modification** d'une fiche : jamais de blocage (deux fiches déjà en double doivent rester modifiables), confirmation seulement.
- Recherche aussi par **téléphone seul** (« 3 patients ont déjà ce numéro »).
- Même logique pour l'**import Excel** (avec mode simulation) et **HPRIM**.

### Menu « Doublons » (module Patients)
- Liste des doublons détectés, du plus sûr au moins sûr (Quasi certain / À vérifier).
- Clic ⇒ **les deux fiches côte à côte**, avec sous chacune le nombre de
  données rattachées (« 3 rendez-vous, 2 factures… »).
- **Trois actions seulement** :
  1. **Fusionner** : choix de la fiche à garder ; pour chaque champ (nom,
     prénoms, date, sexe, téléphone, assurance…), choix gauche/droite ou
     correction manuelle ; tous les liens de l'autre fiche sont déplacés.
  2. **Pas un doublon** : la paire est mémorisée et ne réapparaît plus (jumeaux, homonymes).
  3. **Masquer** : uniquement pour une fiche **sans aucune donnée rattachée** ; sinon c'est une fusion.
- « Transférer » = « fusionner » : on déplace tout d'un coup. Le transfert
  sélectif (choisir quel RDV déplacer) est reporté.
- Permission dédiée (ex. `patients.fusionner_patient`).
- La détection est calculée en arrière-plan (commande / tâche) et stockée,
  pas recalculée à chaque affichage (48 000 fiches ≈ 2 min).

### Règles de fusion (sans conflit, sans perte)
1. **On change le propriétaire** des lignes liées (UPDATE `patient_id`), on ne copie et ne supprime rien.
2. Liste des liens obtenue **par introspection Django** (toutes les FK/OneToOne
   vers `Patient`) ⇒ les futurs modules sont couverts. **Un test doit échouer**
   si une nouvelle FK vers `Patient` apparaît sans être prise en compte.
3. **Une seule transaction** (`transaction.atomic`) : tout ou rien.
4. **Comptage avant/après** par table ; si le total diffère, rollback.
5. **Journal de fusion** (nouveau modèle) : copie complète de la fiche
   absorbée (JSON), liste exacte des lignes déplacées (table + pk), utilisateur,
   date, choix de champs ⇒ **annulation possible**.
6. La fiche absorbée n'est **pas supprimée** : marquée « fusionnée dans X »,
   exclue des listes et recherches ; son **ancien code redirige** vers la fiche gardée.
7. `LogActivite` (générique) : déplacer aussi l'historique. Blockchain : ne pas toucher.
8. Allergies et antécédents : **concaténés**, jamais écrasés. Champs vides de
   la fiche gardée complétés par l'autre.
9. Cas particuliers (décidés avec l'utilisateur) :
   - **Sexe différent** : pas de refus ; avertissement rouge, l'utilisateur
     **doit choisir** le sexe (pas de valeur par défaut), tracé au journal.
   - **Deux centres** : ne se présente pas (on ne voit que le centre actif) ;
     garder un contrôle technique qui refuse si les centres diffèrent.
   - **Hospitalisation en cours sur les deux** : l'écran demande laquelle reste
     active ; l'autre est clôturée « annulée (doublon) » (pas supprimée), lit libéré.
   - **Décès sur une fiche** : avertissement fort, confirmation obligatoire (la fiche gardée deviendra décédée).
   - **RDV en double** (même jour, même médecin) : signalés, proposition d'en annuler un.
   - **Factures/paiements** : tout est conservé, rien n'est recalculé.
   - Photo, documents : tout est gardé.

---

## 6. Plan de travail (une étape à la fois, validée par l'utilisateur)

### Étape 1 — Marquer les dates approximatives *(prochaine étape, validée en principe)*
But : ne plus deviner les dates par défaut.
- Ajouter à `Patient` un booléen `date_naissance_approx` (défaut `False`), avec migration.
- Migration de données : cocher les fiches dont le jour/mois est porté par une
  part anormale de la base (aujourd'hui **01/10**, 89 %, + éventuellement 30/09
  et 01/01). Ne pas modifier les dates elles-mêmes. Afficher le nombre de fiches marquées.
- Import Excel : quand la date vient d'un âge (`_parse_age_to_date`), mettre
  `date_naissance_approx=True`. Le rapprochement à l'import ne doit plus
  dépendre de la date exacte pour ces fiches.
- Placer `patients/doublons.py` (v2) dans le projet et lui faire utiliser ce
  champ (`date_precise = not date_naissance_approx`) au lieu de `DATES_PAR_DEFAUT`.
- Formulaire : décocher automatiquement si l'utilisateur saisit une vraie date.
- Tests : migration, import (date approx), score avec date approx.

### Étape 2 — Prévention à la création
Formulaire + endpoint JSON de vérification en direct + gabarit (encadré et
cases de confirmation), règle jumeaux, présélection resserrée et chronométrée
sur la base dev (objectif : < 300 ms par appel), import Excel et HPRIM
branchés sur `chercher_doublons`. Tests : blocage, confirmation, admin qui
force, modification non bloquée, jumeaux, API.

### Étape 3 — Détection stockée
Modèle(s) pour les paires/groupes détectés et pour les paires « pas un
doublon » ; commande de recalcul (reprend `_cles()` / `regrouper()` du script) ;
recalcul ciblé quand une fiche est créée ou modifiée.

### Étape 4 — Menu « Doublons » et fusion
Liste, écran côte à côte, actions Fusionner / Pas un doublon / Masquer,
aperçu (« cette fusion va déplacer 3 RDV et 2 factures »), journal de fusion,
annulation, redirection de l'ancien code. Tests : chaque FK déplacée,
comptage, rollback en cas d'erreur, annulation, test « nouvelle FK non gérée ».

### Étape 5 — Nettoyage de la base
D'abord en simulation, puis un lot de 20 groupes vérifiés, puis le reste par lots.

---

## 7. Règles de conduite pour Claude Code

- **Sauvegarder `db.sqlite3`** avant toute migration ou fusion (convention du
  projet : `db.sqlite3.avant-<action>-AAAAMMJJ-HHMM`).
- Une étape à la fois ; expliquer en quelques phrases simples ce qui va être
  fait, attendre l'accord, puis faire et lancer les tests.
- Ne pas réimporter le fichier Excel tant que l'étape 1 n'est pas faite (sinon
  nouvelles dates par défaut et doublons en masse).
- Respecter le cloisonnement par centre (`objects` vs `all_objects`).
- L'algorithme v2 de l'utilisateur fait foi : le modifier seulement pour les
  points listés au §4 « Problèmes connus », en le disant.
- Lire `CLAUDE.md` du projet pour les conventions générales.
