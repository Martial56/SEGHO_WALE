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

### Étape 1 — Marquer les dates approximatives *(faite, 13/10/2026)*
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

### Étape 2 — Prévention à la création *(faite, 12/10/2026)*
Formulaire + endpoint JSON de vérification en direct + fenêtre modale des
dossiers ressemblants, règle « prénoms différents de part et d'autre »
(plafond à 84 : confirmation, jamais blocage — le logiciel ne suppose rien sur
la raison), présélection resserrée et chronométrée, import Excel et HPRIM
branchés sur `chercher_doublons`, date de naissance obligatoire à la création
seulement.

Mesures sur la base dev (47 813 fiches) :

| | |
|---|---|
| Recherche d'un doublon à la saisie | 7 920 ms → **215 ms** |
| Couples quasi certains (≥ 85) retrouvés par la présélection SQL | **938 / 938 — 100 %** |
| Idem, contre l'ancien filet large, sur 2 226 fiches | **1 876 / 1 876 — 100 %** |
| Couples « à vérifier » (65–84), contre l'ancien filet large | **1 196 / 1 214 — 98,5 %** |

Les 18 couples perdus sont tous entre 65 et 70, au plancher de la bande
« à vérifier » ; 15 situations distinctes, dont une seule vraie (voir la clé
phonétique en étape 3).

### Étape 3 — Détection stockée *(faite, 13/10/2026)*
`ClePhonetique`, `DoublonPaire`, `PaireEcartee`, `ChoixFicheGardee` ; commande
`recalculer_doublons` ; recalcul ciblé après chaque enregistrement. Les
groupes ne sont pas stockés : ils se recomposent à la lecture (905 groupes en
143 ms), ce qui évite de les réconcilier avec les décisions humaines à chaque
passage.

**Le verrou est un `flock` de fichier, pas un verrou de processus.** Le
passage de nuit tourne sous crontab, gunicorn sert les enregistrements depuis
plusieurs workers : un `threading.Lock` n'en protégeait qu'un. Exclusif pour
le passage complet, partagé pour le recalcul ciblé — plusieurs ciblés peuvent
donc tourner ensemble, aucun pendant un passage complet. `flock` se relâche
tout seul quand le processus meurt, là où une ligne en base resterait posée
après un arrêt brutal.

Mesures sur la base dev (47 813 fiches) :

| | |
|---|---|
| Clés phonétiques | 129 490 lignes, 2,71 par fiche |
| Recherche à l'écran | médiane 179 ms, 9ᵉ décile 264 ms (inchangée par la clé sonore) |
| Passage complet | 9,5 min, 939 paires certaines et 7 626 à vérifier |
| Rattrapage des clés absentes | 55 ms quand il n'y a rien à faire |
| Rappel | +65 paires rapprochées par la clé sonore, 0 perdue, toutes en « à vérifier » |

Reste à traiter plus tard : la recherche dépasse 300 ms sur les noms très
courants (jusqu'à 2 823 candidats présélectionnés). Le défaut est antérieur à
la clé sonore, qui n'y change rien.

**À traiter dans cette étape — clé phonétique indexée.** La présélection, en
SQL comme en mémoire, rapproche des **mots exacts**. Une variante d'écriture
accompagnée d'un téléphone différent passe donc à travers, alors que le score
la reconnaîtrait : mesuré le 12/10/2026 sur la base dev,

```
70 | PAT202639804  N'GESSAN N'DRISCA PRISCA  (≈2008, F, 0564635675)
   | PAT202641602  N'GUESSAN PRSICA          (≈2008, F, 0171374134)
```

que l'utilisateur tient pour la même personne. `cle_phonetique()` sait déjà
rapprocher ces deux graphies — elle n'intervient qu'au scoring, trop tard,
puisque la paire n'est jamais présentée.

Le travail : un champ phonétique stocké et indexé sur `Patient`, rempli à
l'enregistrement et par une migration de données, puis une famille de clés de
plus dans `_preselection()` et dans `cles_blocage()`. Ensuite **refaire la
mesure du rappel** (voir les chiffres de l'étape 2 ci-dessus) : c'est elle
qui dira ce que la clé phonétique rattrape, et ce qu'elle coûte en candidats
présélectionnés.

### Étape 4a — Menu « Doublons », sans fusion *(faite, 13/10/2026)*
Liste des groupes (filtre « Quasi certain » par défaut), écran côte à côte avec
les différences surlignées, et trois décisions réversibles : « pas un doublon »,
« masquer », « garder celle-ci ». Onglet des créations forcées et des saisies
poursuivies, retrouvées par un **code** sur `LogActivite` — jamais par le texte
du message, qui se reformule. Bouton « Recalculer maintenant » avec la jauge.

**Une fiche masquée disparaît partout** : `Patient.objects` l'écarte, donc la
liste, la recherche et toutes les listes déroulantes avec elle. Elle reste
ouvrable par son adresse directe, pour qui détient `patients.gerer_doublons`,
avec un bandeau et le lien vers la fiche gardée. Elle ne reçoit plus rien :
l'import et la passerelle HPRIM suivent `doublon_de` / `fusionne_dans` et
rattachent à la fiche gardée — ou refusent et le signalent, plutôt que de
ranger au mauvais endroit.

« Vide » ne suffit pas à masquer : si la fiche porte une information absente de
l'autre (allergies, antécédents, assurance, contact d'urgence, photo, second
téléphone), l'écran renvoie vers la fusion. Et masquer se fait toujours depuis
un groupe, en notant de quelle fiche c'est le doublon.

La suggestion « ★ à garder » préfère désormais la fiche **qui porte le plus de
données**, puis la plus complète, puis la plus ancienne : c'est autant de
lignes en moins à déplacer le jour de la fusion.

#### Retouches d'affichage *(13/10/2026)*
La liste est une grille de cartes, quatre par rangée. Chaque fiche y porte sa
date de naissance (ou « ≈ année ») et son téléphone — avec le nom seul, on ne
peut pas juger —, ce qui diffère d'une fiche à l'autre est surligné comme à la
saisie, et la raison du rapprochement est écrite au bas de la carte. Une
différence n'en est une qu'entre deux valeurs **renseignées** : un champ vide
d'un côté ne contredit rien.

Le surlignage se fait **mot à mot**, sur la carte comme dans le tableau : entre
« ASSENA ELIAQUIM » et « ASSENA ELIAKIM », seul le second mot s'allume. Le
rapprochement porte sur la forme normalisée — « Kôné » et « KONE » sont le même
mot — mais c'est l'écriture d'origine qui s'affiche.

La raison dit **« même nom »** seulement quand les deux fiches s'écrivent
exactement pareil (accents, apostrophes et espaces mis à part), sinon **« nom
presque identique »** : le seuil ne distingue pas BALO de BALLO, et l'annoncer
comme le même nom serait affirmer ce qu'on n'a pas mesuré. `scorer` range le
verdict dans `details['noms_identiques']`, et l'écran le **relit sur les
fiches** au moment de l'affichage — ainsi la phrase est juste tout de suite,
sans attendre le prochain recalcul.

**Action rapide.** Quand un groupe de deux n'a rien à lire — aucune donnée
rattachée d'un côté, et pas un champ que l'autre n'ait déjà — la carte propose
« Masquer le doublon », avec une confirmation sur place. C'est le cas de plus
de huit groupes sur dix ; les ouvrir un par un ferait des centaines d'écrans.
Le masquage part en AJAX, la carte s'efface, le compte **et** la pagination se
corrigent sur place (« 1–48 sur 903 » devient « 1–47 sur 902 »), et une
banderole de succès annonce la décision avec son « Annuler ». La fiche annoncée est lue dans l'adresse
(`?masque=`), pas gardée en session : la banderole se tait d'elle-même dès que
la fiche est redevenue visible.

**L'écran de comparaison** met le tableau en premier, chaque colonne sous sa
fiche, et les données rattachées y tiennent leurs propres lignes (une par
table, plus un total) : c'est souvent là que se décide la fiche à garder. Les
champs vides des deux côtés se replient derrière « Afficher les N champs
vides » — sans quoi quatorze lignes de tirets repoussaient les comptes sous la
ligne de flottaison. Les actions sont rassemblées dans une barre collante en
bas : « Garder PAT… », « Masquer PAT… », « Pas un doublon » avec sa raison, et
« Fusionner », encore grisé. Quand « Masquer » est bloqué, la raison est
**écrite sous le bouton** : un bouton gris sans explication se lit comme une
panne, et le survol n'existe pas sur une tablette.

Au passage, `.content` est repassé en `overflow: visible` sur ces pages. Le
style global le déclare `overflow-y: auto` pour toute l'application, ce qui en
fait un conteneur de défilement : à l'intérieur, `position: sticky` ne
s'accroche à rien, puisque c'est la fenêtre qui défile. Rien ne bouge — il n'a
jamais de hauteur contrainte — mais le sous-en-tête et la barre d'actions
tiennent enfin ce qu'ils annoncent.

### Étape 4b — La fusion *(faite, 13/10/2026)*
Moteur dans `patients/fusion.py`, écran dans `patients/fusion_vues.py`, journal
dans `FusionPatient`. Permission séparée : **`fusionner_patients`** — masquer
se défait d'un clic, fusionner déplace des factures.

**Le déplacement.** `UPDATE patient_id` par `queryset.update()`, jamais par
`save()` : aucun signal ne se redéclenche, rien n'est ré-ancré côté blockchain,
et `date_modification` ne bouge pas sur des lignes qu'on n'a pas modifiées. Une
seule transaction, comptage avant/après table par table, et `FusionIncoherente`
si un chiffre ne tombe pas juste — la transaction retombe. Les tables viennent
de l'introspection ; trois chemins lui échappent et sont traités à part :
`LogActivite` (lien générique, déplacé), les quatre registres (ils pendent d'un
rendez-vous et suivent le leur), et `PaireEcartee` (**reportée** sur la fiche
gardée, pas déplacée).

**Les champs.** Choix gauche/droite ou correction à la main, ligne par ligne.
Vides de la fiche gardée complétés par l'autre ; allergies et antécédents
**additionnés** ligne à ligne, sans répéter ce qui est déjà dit ; `sexe`
contradictoire → **aucune valeur par défaut**, choix obligatoire, bandeau rouge.
La date de naissance emporte sa case « approximative » — la prendre sans elle
ferait d'une estimation une date certaine. La photo se choisit sans que le
fichier de l'autre soit jamais supprimé : la fiche absorbée reste en base, et
son image avec.

**Les cas particuliers.** Deux centres → refus. Décès → confirmation
obligatoire. Deux hospitalisations en cours → l'écran demande laquelle reste
active, l'autre passe en « annulée (doublon) » avec sa note ; le lit se libère
de lui-même, l'occupation se lisant sur le statut. Rendez-vous le même jour
avec le même médecin → signalés, avec une case **décochée par défaut** qui
passe celui de la fiche absorbée en « annulé (doublon) » ; la case est
interdite — et le dit — si une consultation ou un registre y est rattaché.

**L'annulation.** Le journal garde la copie complète de la fiche absorbée, les
identifiants exacts des lignes déplacées, les choix de champs et les effets.
Elle est **refusée tant qu'une fusion plus récente touche l'une des deux
fiches**, et dit laquelle annuler d'abord. Elle ne rend que ce qui est encore
là et encore à la fiche gardée, et **énumère ce qu'elle n'a pas pu rendre**
plutôt que de laisser croire que tout est revenu : une ligne supprimée depuis,
ou une hospitalisation dont le lit a été repris par quelqu'un d'autre.

**Ce que l'écran empêche.** « Fusionner » reste grisé tant qu'un choix
obligatoire manque — le sexe, l'hospitalisation qui reste active, la
confirmation d'un décès —, avec la raison écrite à côté (« Choisissez le
sexe. »). Le serveur refuse de toute façon ; l'écran le dit avant, pour qu'on
ne valide pas un formulaire qui va revenir en erreur. Le bouton de sortie dit
**« Abandonner »**, pas « Annuler » : « annuler » est réservé à défaire une
fusion déjà faite.

**L'ancienne adresse.** Une fiche **fusionnée** ouverte par son ancien lien
redirige vers la fiche gardée, même pour qui n'a pas `gerer_doublons` : son
contenu est allé quelque part. Une fiche seulement **masquée** reste
introuvable (404) pour les mêmes personnes, comme à l'étape 4a : il n'y avait
rien dedans, et rien n'a bougé. Qui détient `gerer_doublons` voit les deux, avec
leur bandeau.

**Les anciens repères.** Le **code** de la fiche absorbée et son **ancien
identifiant** ramènent la fiche gardée — dans la liste des patients comme dans
le sélecteur de patient des autres écrans. Voir `patients/resolution.py` :
correspondance exacte sur ces deux colonnes, chaîne `fusionne_dans` remontée
(un groupe de trois se fusionne en deux fois), et rien pour une fiche seulement
**masquée** — son contenu n'est allé nulle part. Au passage,
`ancien_identifiant` entre dans les colonnes de recherche de la liste : il n'y
était pas, et les dossiers venus de l'ancien logiciel s'y cherchent encore par
leur ancien numéro.

**Verrou et relevé.** Verrou **partagé** pendant la fusion, comme le recalcul
ciblé : jamais de fusion pendant un passage complet. Les paires de la fiche
absorbée quittent le relevé dans la transaction, pour que le groupe disparaisse
tout de suite ; le recalcul ciblé de la fiche gardée part ensuite en fond, et
celui des deux fiches après une annulation.

**Mesuré sur une copie de la vraie base** (BALO PAT202625408 → BALLO
PAT202625409) : fusion **87 ms**, 4 lignes déplacées (1 facture, 3 rendez-vous),
comptes justes table par table (Facture 1+1=2, DemandeExamen 1+0=1, RendezVous
0+3=3, ProcedureSoin 3+0=3, Soin 1+0=1, fiche absorbée à 0) ; annulation
**157 ms**, rien de non rendu. Comparaison des deux vidages SQL complets
(262 703 lignes) : **12 lignes de différence**, toutes attendues — la paire
25408≈25409 recalculée à l'identique (même score, nouvel identifiant et
nouvelle date de calcul), la ligne de journal de la fusion annulée, et les
compteurs `sqlite_sequence`.

#### Correctif — la fusion refusée à tort *(14/10/2026)*

Signalé sur OUATTARA / OUATTARRA JEANS CHRIST ELI SHAMA : « La fusion n'a pas
eu lieu. L'historique ne se retrouve pas en entier. »

Le journal automatique de `core/audit.py` écrit une trace `LogActivite` à
chaque `save()` fait dans une requête. La fusion en fait deux, et les deux
tombaient mal :

* `_appliquer_les_champs` enregistre la fiche gardée dès qu'un champ est
  repris — la trace naissait **entre** le comptage d'avant et sa vérification,
  d'où un historique en trop et une transaction qui retombe. La fusion ne
  ratait donc que si un champ changeait réellement ;
* `absorbee.save(['fusionne_dans'])` écrivait une trace **sur la fiche
  absorbée**, après la vérification : personne ne la voyait, et elle restait
  sur une fiche qui n'est plus consultable.

Les deux sauvegardes passent désormais par `_sauver_sans_trace()`, qui pose
`_skip_auto_log` — la porte que `core.audit` prévoit pour l'appelant qui écrit
lui-même une trace plus juste. Une trace unique est posée sur la fiche gardée
**après** la vérification des comptes (code `patient.fusion`), et l'annulation
pose la sienne (code `patient.fusion.annulee`). Quatre tests, qui passent par
l'écran : sans utilisateur connecté, le signal ne se déclenche pas et le bug
est invisible.

### Correctif — nom ou prénom, la raison le dit *(14/10/2026)*

« nom presque identique » s'affichait aussi quand le nom était le même et que
seul le prénom changeait — ASSENA **ELIAQUIM** / ASSENA **ELIAKIM**, SOMDA
**CHIRST** / SOMDA **CHRIST**. La phrase désignait le mauvais champ, juste à
côté du mot surligné qui disait le contraire.

`memes_noms()` ne répond que pour l'ensemble des deux champs. `memes_champs()`
les compare séparément, et `raisons()` distingue quatre cas :

| Nom | Prénoms | Phrase |
|---|---|---|
| même écriture | même écriture | même nom |
| même écriture | diffère | prénom presque identique |
| diffère | même écriture | nom presque identique |
| diffère | diffère | nom et prénom presque identiques |

Comme pour « même nom », l'écriture est **relue sur les fiches** à l'affichage
(`doublons_groupes._raisons_du_groupe`) : la phrase se corrige sans attendre
le recalcul suivant, y compris sur les 8 513 paires déjà relevées. Les
`details` rangés en base portent désormais `nom_identique` et
`prenoms_identiques` ; une paire d'avant qui ne les a pas garde l'ancienne
phrase plutôt qu'une devinette.

Captures : `docs/captures/doublons/raisons-{clair,sombre}.png`,
`raisons-nom-et-prenom.png`.

### Correctif — le cloisonnement du menu *(14/10/2026)*

`_centre_id()` retombait, faute de centre actif, sur **le centre de la
première paire venue** :

```python
from .models import DoublonPaire
return DoublonPaire.all_objects.values_list('centre_id', flat=True).first()
```

Un compte rattaché à Toumbokro mais sans centre sélectionné ouvrait donc le
relevé de Yamoussoukro — noms, dates de naissance et téléphones côte à côte,
et de quoi masquer ou fusionner. L'écran rapproche les fiches en entier : il
n'y a pas de demi-fuite possible ici.

Le repli est supprimé. Tout passe désormais par
**`patients/doublons_acces.py`** :

| Outil | Ce qu'il fait |
|---|---|
| `exige_un_centre` | Décorateur posé sur chaque vue du menu. Sans centre actif : écran « Choisissez un centre. » en GET, `403` en POST, `409` en AJAX. Un super-utilisateur ne fait pas exception. |
| `fiches_du_centre(request)` | `Patient.all_objects` filtré sur le centre actif — masquées et fusionnées comprises, puisqu'on les traite ici. |
| `fiche_du_centre(request, pk)` | Une fiche, ou `404` : l'adresse directe ne contourne rien. |
| `fiches_du_groupe(request, cle)` | Les fiches d'une clé, **toutes** du centre actif ; il en manque une et la clé est refusée en entier. La clé voyage dans l'adresse, elle ne prouve rien. |

Couvert : liste, comparaison, écarter, reprendre, garder, masquer,
réafficher, journal des créations forcées (et sa recherche), onglet des
fusions (et sa recherche), écran de fusion, annulation d'une fusion,
recalcul. La trace de « saisie poursuivie » (`doublons_journaliser`) ne se
pose plus non plus sur une fiche d'un autre centre.

Tests : `TestLeCloisonnementDuMenuDoublons`,
`TestLeMenuDoublonsSansCentreActif`, `TestLeCloisonnementDeLaFusion` — un
compte de Toumbokro essaie chaque chemin, y compris les adresses directes.
`BaseDoublons` rattache désormais son agent à son centre, comme dans la vie.

Captures : `docs/captures/doublons/sans-centre-{clair,sombre}.png` et
`cloisonnement-toumbokro.png`.

### Étape 4c — Le menu aux couleurs du projet *(faite, 14/10/2026)*

L'écran des doublons possédait ses propres `.o-subheader`, `.o-search-bar`,
`.o-btn` et `.o-pag-btn` : voisins de ceux des autres listes, mais pas
identiques. Ces composants n'appartenaient d'ailleurs à personne — ils
vivaient dans `patients/list.html`, et chaque module qui voulait la même tête
en recopiait sa version.

Ils sont extraits dans **`templates/includes/listing/composants.html`** :
sous-en-tête collant, titre et pastille de compte, barre de recherche, boutons
de contrôle, menus déroulants, pagination haute et basse, bascule
cartes/tableau, tableau, onglets. `patients/list.html` et
`doublons/base_doublons.html` incluent le même partiel : les deux écrans se
ressemblent par construction, et une correction les sert tous les deux.

Le menu suit en plus le reste du gabarit des listes :

* deux lignes de sous-en-tête — titre et recherche, puis onglets et contrôles ;
* onglets `.tab-nav` / `.tab-btn`, ceux de la fiche patient ;
* filtres dans un menu `.o-dd-panel.lst-menu`, comme « Filtres » des patients,
  au lieu des pastilles maison ;
* une **vue tableau** en plus des cartes, avec la même bascule `.o-view-btns`
  et le choix retenu d'une page à l'autre ;
* pagination numérotée en pied de page, celle de la liste des patients ;
* l'échange AJAX passe par `includes/listing/page_js.html`, le pilotage commun
  des listes : `#subheader-controls`, `#dbl-resultats` et `.o-page-count` sont
  échangés par identifiant, exactement comme chez les patients.

Captures côte à côte : `docs/captures/doublons/cote-a-cote-{clair,sombre,tableau}.png`.

### L'onglet « Fiches masquées » *(fait, 14/10/2026)*

Une fiche masquée n'existe plus nulle part : ni dans la recherche, ni dans les
listes, ni dans les sélecteurs d'un rendez-vous ou d'une facture, et son
adresse directe ne s'ouvre que pour qui détient `gerer_doublons` — et
seulement dans son propre centre. Restait qu'on ne pouvait plus la retrouver
du tout : la reprendre demandait de se souvenir du groupe d'où elle avait été
retirée, ou de passer par l'admin.

L'onglet la montre : code et nom, naissance, téléphone, de quelle fiche elle
est le doublon, **qui l'a masquée et quand**, et « Réafficher ». Recherche par
nom, code ou ancien identifiant — l'ancien identifiant compte autant que le
code, c'est lui qui figure sur les cartes imprimées. Pagination et compte
comme les deux autres journaux, cloisonnement par centre comme le reste du
menu.

« Qui » et « quand » sont deux nouveaux champs de `Patient` (`masque_par`,
`masque_le`, migration `0051`), posés au masquage et effacés quand on
réaffiche. Portés par la fiche plutôt que déduits du journal : `LogActivite`
enregistre l'écriture, pas la décision, et le retrouver demanderait de
fouiller le texte d'un message — qui se reformule. Les fiches masquées avant
cette migration affichent « — » : on ne devine pas ce qu'on n'a pas mesuré.

Au passage, un trou du même genre que celui du menu : `patient_detail`
relisait une fiche retirée par `Patient.all_objects`, sans filtre de centre.
L'adresse directe d'une fiche masquée ou fusionnée d'un autre centre
s'ouvrait donc pour qui détient `gerer_doublons`. Corrigé par
`_retiree_lisible()`, qui applique la règle de `CentreManager`.

Captures : `docs/captures/doublons/masquees-{clair,sombre}.png`.

### Étape 4b — spécification d'origine
Écran côte à côte, actions Fusionner / Pas un doublon / Masquer,
aperçu (« cette fusion va déplacer 3 RDV et 2 factures »), journal de fusion,
annulation, redirection de l'ancien code. Tests : chaque FK déplacée,
comptage, rollback en cas d'erreur, annulation, test « nouvelle FK non gérée ».

**Cinq liens vers `Patient` à NE PAS déplacer lors d'une fusion.** La règle
générale — « toute FK vers `Patient` change de propriétaire », établie par
introspection pour que les futurs modules soient couverts d'office — ne vaut
pas pour les tables de l'étape 3, qui parlent *de* la fiche et non de ce qui
lui est arrivé. Les déplacer créerait des paires de la fiche gardée avec
elle-même, et ressusciterait des décisions prises sur une fiche qui n'existe
plus comme dossier.

| Lien | Ce qu'il faut faire à la fusion |
|---|---|
| `ClePhonetique.patient` | Supprimer celles de la fiche absorbée. Elle sort de la détection, ses clés n'ont plus d'objet. |
| `DoublonPaire.patient_a` / `.patient_b` | Supprimer toutes les paires qui la citent. Le relevé se refait. |
| `PaireEcartee.patient_a` / `.patient_b` | **Reporter** sur la fiche gardée, en sautant celles qui la désigneraient elle-même, et sans écraser une paire déjà écartée. Une décision « ce n'est pas la même personne » doit survivre à la fusion. |
| `ChoixFicheGardee.patient` | Supprimer si elle porte sur la fiche absorbée ; la fusion vient de trancher. |
| `Patient.fusionne_dans` | Jamais déplacé. Il est le résultat de la fusion, pas une donnée rattachée. En `PROTECT` : supprimer la fiche gardée emporterait sinon l'historique de la fusion. |

Le test « nouvelle FK non gérée » doit donc connaître cette liste
d'exceptions, et échouer si une FK apparaît en dehors d'elle **et** de la
règle générale.

### Étape 4d — La suppression définitive *(faite, 14/10/2026)*

4c est prise par le design : la suppression est **4d**.

Réservée à `is_superuser` — pas une permission, pour qu'aucun groupe ne puisse
la recevoir par inadvertance — et accessible du seul menu Doublons. Autorisée
pour une fiche **masquée ou fusionnée**, **sans aucune donnée rattachée**,
revérifié côté serveur au moment de supprimer et pas seulement à l'affichage
du bouton. Confirmation en tapant le code de la fiche. Pour une fiche
fusionnée, avertissement : « La fusion ne pourra plus être annulée. »

Une trace est conservée (`SuppressionPatient`) : qui, quand, la copie complète
de la fiche et son journal d'activité recopié — `LogActivite` est générique,
rien ne le rattache à la fiche, il serait sinon orphelin sans que personne le
voie.

**La redirection survit à la suppression.** Des cartes et des reçus imprimés
portent l'ancien code d'une fiche fusionnée : le résoudre ne peut plus passer
par la fiche absorbée, qui n'existe plus. `patients/resolution.py` doit donc
aussi lire `FusionPatient.code_absorbee` et `ancien_identifiant_absorbee`, et
remonter la chaîne même quand une fiche intermédiaire a été supprimée.

#### Ce qui a été fait

Le moteur est dans **`patients/suppression.py`** : `obstacles()` dit pourquoi
on refuse, `ce_qui_part()` dit ce que la suppression emporte, `supprimer()`
exécute — et refait tous les contrôles, parce que c'est le dernier endroit où
l'état de la base est celui qu'on supprime.

L'écran `doublons/supprimer/<pk>/` se lit avant de décider : la fiche et son
état, l'avertissement s'il y a lieu, ce qui part, ce qui reste, puis le code à
taper. Le bouton reste gris tant que le code ne correspond pas — garde-fou de
surface seulement, la vue revérifie. Le lien est posé sur les deux onglets qui
montrent des fiches retirées : « Fiches masquées » et « Fusions », et
seulement pour `is_superuser`.

**Le journal de fusion survit aux deux fiches.** `gardee` et `absorbee`
passent de `PROTECT` à `SET_NULL`, et trois repères sont recopiés à la fusion :
`code_absorbee`, `ancien_identifiant_absorbee`, `code_gardee` (migration
`0052`, qui les remplit aussi pour les fusions déjà écrites). Une fusion dont
une fiche a disparu n'est plus annulable — `FusionPatient.annulable` le dit, la
ligne du journal l'affiche, et `annuler()` le refuse.

**La chaîne ne se coupe nulle part.** Avant l'effacement, les fiches qui
pointaient sur celle-ci (`fusionne_dans`, `doublon_de`) sont reportées sur sa
remplaçante : sans cela `PROTECT` refuserait la suppression, et un `SET_NULL`
leur rendrait l'apparence d'un dossier ouvert. Au-delà, c'est le journal qui
répond : code supprimé → `code_absorbee` → fiche gardée, et si elle a disparu
aussi, `code_gardee` reprend la chaîne.

**Le journal est consulté dans tous les cas**, pas seulement quand aucune
fiche ne porte le repère. Les anciens identifiants ressemblent aux codes : sur
la base réelle, un dossier vivant portait comme ancien identifiant le code
exact d'une fiche supprimée. Les deux réponses sont justes ; laisser la
première masquer la seconde faisait disparaître la redirection — c'est le
navigateur qui l'a montré, pas les tests.

Ce qui part avec la fiche : ses clés phonétiques, les paires relevées et les
décisions prises dessus. Ce qui reste : `SuppressionPatient` — qui, quand, la
copie complète, et **le journal d'activité recopié**, car `LogActivite` est
générique et ne tombe dans aucune cascade.

Tests : `TestQuiPeutSupprimer`, `TestCeQueLaSuppressionRefuse`,
`TestLaSuppressionDUneFicheMasquee`, `TestLaSuppressionDUneFicheFusionnee`,
`TestLaChaineDeFusionsApresSuppression`.

Captures : `docs/captures/doublons/supprimer-masquee-clair.png`,
`supprimer-fusionnee-{clair,sombre}.png`, `masquees-patron.png`,
`fusions-patron.png`, `fusions-apres-suppression.png`.

### Retouches — boutons en ligne et centre à la saisie *(14/10/2026)*

**Les actions dans une ligne de tableau sont encadrées.** `.o-ctrl-btn` et
`.o-btn-danger` ne montrent leur cadre qu'au survol : juste dans une barre
d'outils, où les boutons se suivent et se devinent ; trompeur dans une ligne
de tableau, où « Réafficher » et « Annuler la fusion » se lisaient comme du
texte. Les tableaux du menu (`.dbl-tableau`) les dessinent donc toujours, au
gabarit de `.dbl-rapide-btn` pour que toutes les actions en ligne se
ressemblent.

**La saisie refuse de travailler sans centre actif.** Même règle que le menu,
même phrase : « Choisissez un centre. »

* `doublons_verifier` ne propose plus rien et le dit, au lieu de chercher
  dans tous les centres ;
* `PatientForm.clean()` refuse la création, et `_perimetre()` rend un
  ensemble vide au lieu de `all()` — un périmètre vide ne doit jamais pouvoir
  passer pour « aucun doublon trouvé » ;
* le centre peut venir du formulaire (`centre=`) **ou** de la fiche qu'on
  modifie : corriger l'adresse d'un dossier existant ne redemande rien ;
* un super-utilisateur ne fait pas exception ;
* l'import par lots et les commandes passent leur centre explicitement et
  n'empruntent pas le formulaire : ce chemin ne change pas.

Tests : `TestLeCentreEstObligatoirePourCreer` — formulaire seul, vue de
création, super-utilisateur, fenêtre de saisie avec et sans centre, et les
deux chemins d'import.

### Étape 4e — Traiter en lot, filtrer et regrouper *(faite, 14/10/2026)*

Neuf cents groupes quasi certains se traitent mal un par un. Trois mécaniques
s'ajoutent à l'écran, et une quatrième section dit ce qu'elles coûtent.

#### La phrase de raison, rangée dans l'index

`_construire_index` compose désormais la phrase de chaque entrée
(`ligne['raison']`) et la range avec elle ; `VERSION_INDEX` passe à 4. C'est
elle qui permet de filtrer, de compter et de regrouper sans relire les
fiches à chaque requête.

L'affichage continue de la **recomposer** depuis les fiches chargées
(`_raisons_du_groupe`) : la phrase d'une carte se corrige dès qu'un nom est
corrigé, sans attendre un recalcul. Les deux peuvent donc se contredire sur
un groupe entre une correction et la reconstruction de l'index ; un lot la
provoque (il supprime des paires, ce qui périme la clé de cache), le passage
de nuit sinon. Un test compare les deux sur tout le relevé : **zéro écart**
sur les 8 510 entrées de la base réelle.

#### Filtrer

Le menu « Filtres » porte trois sections : niveau (exclusif), données
rattachées (aucune des deux fiches / une seule / les deux) et raison — les
**40 phrases distinctes** de la base, de la plus fréquente à la moins
fréquente, chacune avec son nombre, cumulables. Chaque nombre est compté sur
le relevé filtré par les *autres* filtres : c'est ce qu'on obtiendra en
cochant, pas un nombre théorique. Les filtres actifs s'affichent en pastilles
au-dessus du relevé, avec « Effacer ».

#### Regrouper

« Regrouper par » range les cartes en sections — par raison, par niveau ou
par données rattachées — avec les bandes `.lst-groupe-bande` de la liste des
patients, en vue cartes comme en vue tableau. Le nombre d'une section est
celui de l'ensemble filtré, pas de la page : une section qui déborde dit ce
qu'elle contient. Chaque bande porte sa case « tout sélectionner ».

#### Traiter en lot

Une case par carte et par ligne, « tout sélectionner sur la page », « tout
sélectionner selon le filtre (N groupes) », et une barre d'actions qui
apparaît dès qu'un groupe est coché. Trois actions, et pour chacune une
confirmation qui **nomme les groupes** — fiche gardée (★) et fiche visée —
puis un bilan.

| Action | Retenu seulement si | Qui |
|---|---|---|
| Masquer | deux fiches, celle qu'on retire ne porte ni donnée ni champ que l'autre n'ait | `gerer_doublons` |
| Pas un doublon | deux fiches, aucune déjà traitée ; raison commune facultative | `gerer_doublons` |
| Fusionner | aucun obstacle, aucun avertissement, aucun champ à choisir | `fusionner_patients` |

Les autres sont **ignorés et listés avec leur raison** : « porte des
données », « porte des informations que l'autre n'a pas », « sexes
différents », « plus de deux fiches ». Ils restent à traiter un par un, et le
dire ici évite d'avoir à les chercher.

Trois choses font qu'un lot n'est pas une boucle sur l'action unitaire :

* **Ce qui est confirmé est ce qui est exécuté.** La liste est figée dans
  `LotDoublons.cles` à la confirmation. Un groupe traité entre-temps depuis
  un autre poste passe dans les écartés avec sa raison — il n'est ni refait,
  ni cause d'un échec général.
* **Le relevé se reprend une fois, à la fin.** `recalculer_fiche` coûte
  209 ms ; après chacun des neuf cents masquages, il ferait trois minutes.
  Les paires des fiches traitées partent d'un coup.
* **Au-delà de quarante groupes, le lot part en tâche de fond**, avec la
  jauge du projet — une fusion coûte 160 ms.

#### Annuler un lot

Chaque lot porte un numéro (`LOT20260001`), son auteur, sa date, son action
et ses groupes. L'onglet **« Lots »** les liste et offre « Annuler ce lot » :
il défait ce qui peut encore l'être et **dit ce qui ne le peut plus** (fiche
réaffichée depuis, fusion plus récente, fiche supprimée). L'annulation une
par une reste possible ailleurs.

#### Ce que ça coûte, mesuré sur la copie de la base réelle

47 811 fiches, 8 557 paires, 8 510 entrées, 40 phrases.

| Opération | Avant | Après |
|---|---|---|
| `_construire_index` (une fois par heure et par worker) | 350 ms | **760 ms** |
| `index()` relu dans le cache | 30 ms | 30 ms |
| Filtrer sur une ou trois raisons | — | **2 ms** |
| Compter les 40 phrases | — | **5 ms** |
| Ranger en sections | — | **6 ms** |
| Totaux rattachés de tout le relevé (premier appel) | — | **2,7 s**, puis en cache 60 s |
| Page complète, cache chaud (aller-retour HTTP) | ~0,9 s | ~0,9 s |

Les 400 ms ajoutés à l'index sont ceux de la mise à plat des écritures ;
elle est faite **une fois par fiche** et non une fois par paire, ce qui
divisait déjà le coût par trois. Le reste ne se voit pas : le filtre et le
regroupement travaillent sur une liste en mémoire.

Côté action : **220 écartements en 0,71 s**, leur annulation complète en
2,1 s. Une fusion coûte 160 ms, d'où la tâche de fond au-delà de quarante.
Le filtre « données rattachées » est le seul coûteux ; son cache d'une minute
est vidé après tout masquage, écartement, fusion ou suppression, sans quoi il
proposerait des groupes déjà traités.

Captures : `docs/captures/doublons/lot-{filtres,selection,groupe,groupe-tableau,confirmation,lots}-{clair,sombre}.png`.

### Garde-fou — pas d'action rapide sur un « à vérifier » *(15/10/2026)*

**Ce qu'on a vu.** La section « prénom presque identique, date de naissance
proche » compte 1 780 groupes, et beaucoup sont deux personnes : KONATE
FATIMATA ZAHARA et KONATE FATOUMATA ZARA, KOUAME KONAN ELISHAMA et KOUAME
ELISHAMA. Chaque carte y proposait « Masquer le doublon », et la sélection
permettait de masquer la section entière d'un geste.

**La règle.** « Masquer » et « Fusionner », en un clic comme en lot, ne
valent que pour les groupes **quasi certains**.

| | quasi certain | à vérifier |
|---|---|---|
| « Masquer le doublon » sur la carte | oui | **non** |
| Lot « Masquer » / « Fusionner » | oui | **ignoré**, raison : `à vérifier : à traiter un par un` |
| Lot « Pas un doublon » | oui | oui |
| À l'unité, depuis l'écran de comparaison | oui | **oui** — rien n'y change |

**Où c'est écrit.** `_masquable()` (`patients/doublons_groupes.py`) rend
`None` hors « quasi certain » ; `_refus()` (`patients/doublons_lots.py`)
écarte le groupe avec sa phrase. Le niveau est relu sur les paires
(`niveaux()`), pas sur l'index en cache : c'est de cette lecture que dépend
l'autorisation. Un groupe dont plus aucune paire ne subsiste est tenu pour
« à vérifier » — devant un relevé qu'on ne sait plus lire, on refuse.

La barre de sélection le dit avant le clic : « N « à vérifier » : seul « Pas
un doublon » les traitera », et les deux boutons s'éteignent s'il n'y a
qu'eux. Le serveur écarte de toute façon ; l'affichage évite seulement
l'aller-retour.

**Au passage.** « Effacer » n'apparaît plus qu'une fois, dans la barre de
contrôles, comme sur toutes les autres listes du projet.

Captures : `docs/captures/doublons/av-{barre,certains,melange,tableau,comparer}-{clair,sombre}.png`
et `av-confirmer-clair.png`.

### Correctif — les bandes de section se replient *(15/10/2026)*

**Ce qui n'allait pas.** La bande de section des doublons n'était pas celle
des autres listes. Pas de chevron, pas de clic : rien pour replier. En
cartes, elle portait bien la classe `.lst-groupe-bande`, mais ces règles
vivaient **dans** `patients/list.html` et `gynecologie/list.html` — du CSS de
page, jamais chargé ailleurs — et l'écran n'héritait donc de rien : une
phrase nue là où les autres montrent une bande. En tableau, c'était
l'inverse : `tr.lst-groupe` recevait le style partagé, `cursor: pointer`
compris, pour une bande qui ne faisait rien.

**Ce qui a été fait.**

1. Les règles `.lst-groupe-bande` rejoignent la brique
   (`includes/listing/styles.html`), à côté de celles du chevron et du
   compteur, déjà partagées. Les deux copies de page disparaissent.
2. Les bandes des doublons prennent le balisage commun : `lst-groupe`,
   chevron, `lst-compte`, `data-chemin`, `onclick="lstBasculerGroupe(this)"` ;
   cartes et lignes portent `data-parent`. Le repliage est donc **le script
   partagé**, pas une copie.
3. `data-charge="1"` et pas de `data-feuille` : les cartes sont déjà dans la
   page, il n'y a ni préchargement ni aller-retour au dépliage.
4. `window.lstSansMemoire` met de côté la seule chose que cet écran ne peut
   pas honorer : l'état déplié rangé dans l'adresse et redit au serveur. Les
   groupes des doublons sont composés en mémoire puis paginés — un chemin n'y
   désigne rien de stable d'une page à l'autre. Sans ce frein, chaque clic
   aurait déclenché une requête `_memo` inutile.
5. La case « sélectionner la section » arrête la propagation : cocher ne
   referme pas la bande.

Ce qui reste différent, et assumé : une seule dimension à la fois, et une
section qui déborde est coupée par la pagination. Les y rendre identiques
demanderait de poser le relevé sur `core/listing.py`, qui travaille sur un
queryset — pas sur 8 512 groupes composés en mémoire.

Captures : `docs/captures/doublons/bande-{cartes,repliee,sections,sections-repliee,tableau}-{clair,sombre}.png`.

### Étape 5 — Nettoyage de la base
D'abord en simulation, puis un lot de 20 groupes vérifiés, puis le reste par lots.

---

## 7. Règles de conduite pour Claude Code

- **Ne jamais commiter ni pousser sans demande explicite de l'utilisateur**,
  même avec la suite complète au vert. Une suite verte dit que le code tient,
  pas que le travail est celui qu'on attendait : c'est l'utilisateur qui le
  dit, et lui seul décide du moment.
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
