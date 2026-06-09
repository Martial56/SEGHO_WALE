# Interopérabilité HPRIM — module `laboratoire`

Ce module permet à SEGHO-WALE d'**envoyer des demandes d'analyses** à un
logiciel de laboratoire (message **ORM**) et de **recevoir les résultats**
(message **ORU**) au format HPRIM Santé v2.4, via FTP.

## Fichiers ajoutés

```
laboratoire/
├── hprim/
│   ├── core.py          # Moteur HPRIM (génération + parsing), sans Django
│   ├── transport.py     # Envoi/réception FTP + fichier témoin .ok (§6.3)
│   ├── integration.py   # Pont modèles Django <-> HPRIM (ORM out, ORU in)
│   └── services.py      # Orchestration + journalisation (EchangeHPRIM)
├── management/commands/
│   └── relever_resultats_hprim.py   # Commande de relève des résultats
├── models.py            # + ConfigurationHPRIM, EchangeHPRIM
├── admin.py             # + action "Envoyer au laboratoire", admin journal
└── migrations/0004_configurationhprim_echangehprim.py
```

## Gestion des messages d'erreur (ERR, §5.14)

Le laboratoire peut renvoyer un message **ERR** pour signaler un problème dans
un message reçu (rejet total `T`, rejet partiel `P`, ou information `I`).

**Réception** : la commande `relever_resultats_hprim` détecte automatiquement
le contexte de chaque fichier (`detect_contexte`) et route les ERR vers leur
propre traitement. Chaque erreur signalée crée un enregistrement
**ErreurHPRIM** (admin : *Laboratoire → Erreurs HPRIM*, ou en ligne sous
l'échange concerné).

Rapprochement avec la demande d'origine :
- via le nom du fichier erroné (champ 25.3) rapproché d'un envoi `EchangeHPRIM` ;
- à défaut, via un numéro `DEM…` trouvé dans l'adresse du segment fautif (25.7).

En cas de **rejet total** (`gravité = T`) sur une demande identifiée, celle-ci
repasse au statut `brouillon` pour correction et réémission.

**Émission** : SEGHO peut aussi générer un ERR pour signaler au labo un
message ORU mal formé :
```python
from laboratoire.hprim.core import construire_err, ErreurAEmettre, Entite
contenu = construire_err(
    emetteur=Entite("WALE", "CMS WALE"),
    recepteur=Entite("LABO", "LABO BIO"),
    nom_fichier="WALE0009.HPR",
    nom_fichier_errone="LABO0042.HPR",
    erreurs=[ErreurAEmettre(gravite="P", type_erreur="I",
                            donnee_erronee="9.3.2",
                            designation="Numéro de demande inconnu")],
)
```

## Mise en route

1. Appliquer les migrations (déjà appliquées dans le db.sqlite3 fourni) :
   ```bash
   python manage.py migrate laboratoire
   ```

2. Dans l'admin Django : **Laboratoire → Configurations HPRIM → Ajouter**.
   Renseigner :
   - les identités émetteur (vous) et récepteur (le laboratoire) ;
   - les paramètres FTP (hôte, utilisateur, mot de passe, port) ;
   - le `répertoire d'envoi` (dépôt des demandes) et le
     `répertoire de réception` (relève des résultats) ;
   - cocher **actif**.

## Envoyer une demande au laboratoire (ORM)

### Validation en amont (admin)

Le formulaire d'édition d'une demande dans l'admin **refuse** d'enregistrer une
demande au statut « Demandé » tant qu'aucune ligne d'examen n'est saisie. Un
message d'erreur s'affiche et l'enregistrement est bloqué ; la demande peut
rester en « Brouillon » sans ligne. Cette validation (formset inline,
`LigneDemandeInlineFormSet`) garantit qu'une demande ne part jamais vide,
en complément du contrôle de complétude côté envoi.

### Envoi automatique (au statut « demandé »)

Dès qu'une `DemandeExamen` passe au statut **« Demandé »** (à la création ou
par transition depuis un autre statut), l'envoi HPRIM est déclenché
automatiquement — aucune action manuelle requise. C'est géré par un signal
Django (`laboratoire/signals.py`, branché dans `apps.py`).

Garanties :
- l'envoi a lieu **après le commit** de la transaction (`transaction.on_commit`),
  donc jamais pour une demande dont l'enregistrement échouerait ;
- un échec (FTP indisponible, configuration absente) **n'interrompt pas** la
  sauvegarde de la demande : l'erreur est journalisée dans *Échanges HPRIM* ;
- **anti-doublon** : pas de réémission si un envoi a déjà abouti, et la
  mise à jour interne du statut après envoi ne re-déclenche pas le signal ;
- **contrôle de complétude** : une demande passée à « demandé » mais sans
  aucune ligne d'examen n'est **pas** transmise ; un échange en statut
  « erreur » est journalisé avec un message explicite. Ajoutez au moins un
  examen puis relancez l'envoi manuellement (action « Envoyer au
  laboratoire »). La vérification a lieu après le commit, donc les lignes
  ajoutées dans la même opération que la demande sont bien prises en compte.

En cas d'échec, relancez l'envoi manuellement (voir ci-dessous) une fois le
problème résolu.

### Envoi manuel (admin)

Dans l'admin : **Laboratoire → Demandes d'examen**, sélectionner une ou
plusieurs demandes → action **« Envoyer au laboratoire (HPRIM / FTP) »**.

Le module génère le fichier `.HPR`, le dépose par FTP, puis dépose le fichier
témoin `.ok`. Chaque envoi est tracé dans **Échanges HPRIM**.

Programmatiquement :
```python
from laboratoire.hprim.services import envoyer_demande
echange = envoyer_demande(demande)   # demande : DemandeExamen
```

## Recevoir les résultats (ORU)

Relève manuelle :
```bash
python manage.py relever_resultats_hprim
```

Relève automatique (cron, toutes les 10 min) :
```cron
*/10 * * * * cd /chemin/SEGHO_WALE && python manage.py relever_resultats_hprim
```

Pour chaque fichier ORU dont le témoin `.ok` est présent, le module :
- crée une `AnalyseLaboratoire` par demande (OBR) ;
- crée un `ResultatAnalyse` par test (OBX), avec normales et interprétation ;
- passe la `DemandeExamen` correspondante au statut `terminé` ;
- journalise tout dans **Échanges HPRIM**.

## Rapprochement des messages

| Donnée HPRIM | Champ | Modèle SEGHO |
|---|---|---|
| Numéro de demande | OBR 9.3.2 | `DemandeExamen.numero` |
| Identifiant patient | P 8.3 | `Patient.code_patient` |

Le laboratoire **doit renvoyer le numéro de demande à l'identique** dans
l'ORU (champ consigné) pour que le rapprochement fonctionne.

## Points à convenir avec le laboratoire

- **Codification des examens** : les codes envoyés (champ 9.5 / 10.4)
  proviennent de `TypeExamen.code`. Il faut une table de correspondance
  commune, ou que le labo accepte vos codes locaux (table = `L`).
- **Répertoires FTP** et mécanisme de témoin (extension `.ok` par défaut).
- **Encodage** : ISO-8859-1 (Latin-1), conforme à la norme.

## Conformité norme HPRIM 2.4

- Segment H avec déclaration des 5 séparateurs `|~^\&` (§7.2)
- Encodage ISO-8859-1, fins de segment CR/LF (§7.1, §5.1)
- Champs vides transmis vides, délimiteurs de fin supprimés (§5.1)
- Découpage automatique en segments A au-delà de 220 caractères (§5.8)
- Nom de fichier RADIX 50 + `.HPR` (§7.2)
- Synchronisation par fichier témoin (§6.3)
```
```
