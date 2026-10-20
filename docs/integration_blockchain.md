# Intégration blockchain — SEGHO-WALE

Ce document décrit la couche de preuve de SEGHO-WALE telle qu'elle est
réalisée et déployée : son principe, son architecture, la protection des
données, le versionnement des ancrages, l'intégration à Django, les tests et
les règles d'exploitation.

---

## 1. Objectif et principe

La couche de preuve permet d'établir, y compris face à un administrateur du
système, qu'un enregistrement de SEGHO-WALE (dossier patient, consultation,
facture, échange avec le laboratoire…) n'a pas été modifié depuis son
ancrage, ou que toute modification a été tracée.

**Principe : la preuve sur le registre, la donnée dans Django.** Seule une
empreinte SHA-256 de chaque enregistrement est inscrite sur un registre
Hyperledger Fabric. Le registre étant **immuable** et **répliqué chez chaque
organisation**, aucune donnée personnelle ni aucune donnée de santé n'y
figure, pas même un identifiant interne (voir § 3).

Pour vérifier un enregistrement, l'application recalcule son empreinte à
partir de l'état courant de la base et la compare à l'empreinte ancrée.
Aucune organisation ne pouvant inscrire seule un événement (politique
d'endossement conjonctive), le CMS WALE ne peut pas réécrire la preuve.

---

## 2. Architecture déployée

### 2.1 Réseau Hyperledger Fabric

| Élément | Valeur |
|---|---|
| Base | `fabric-samples/test-network` (`/home/segho/hyperledger/fabric-samples`) |
| Versions | Hyperledger Fabric 2.5.16, Fabric CA 1.5.17, Go 1.26.8, Docker 29.8.2 |
| Organisations | `Org1MSP` : site principal, soumet les transactions ; `Org2MSP` : organisation contresignataire |
| Nœuds | `peer0.org1.example.com`, `peer0.org2.example.com`, `orderer.example.com` (Raft) |
| Canal | `seghochannel` |
| Base d'état | LevelDB |
| Chaincode | `dossier-medical`, version 1.2, séquence 3 |
| Politique d'endossement | `AND('Org1MSP.peer','Org2MSP.peer')`, déclarée explicitement |

Dans la topologie cible décrite dans le mémoire, Org2MSP sera tenue par
l'antenne de Toumbokro, puis par le laboratoire partenaire. Le réseau actuel
est un **réseau de démonstration** : identités générées par `cryptogen`, deux
organisations sur un même serveur.

Le dossier `blockchain/network/` contient une configuration à trois
organisations (`CentreSanteMSP`, `VerificationFactureMSP`, `RegulateurMSP`,
canal `canal-sante`) préparée au début du projet. **Elle n'est pas utilisée**
et n'est pas maintenue ; elle est conservée pour référence.

### 2.2 Chaincode `dossier-medical` (Go)

Emplacement : `blockchain/chaincode/dossier-medical/`, bibliothèque
`fabric-contract-api-go`.

| Contrat | Fonctions |
|---|---|
| `IntegriteContract` | `EnregistrerEvenement`, `ConsulterEvenement`, `VerifierIntegrite`, `HistoriqueEntite`, `EvenementsParCentre` |
| `ConsentementContract` | `AccorderConsentement`, `RevoquerConsentement`, `ConsulterConsentement`, `ConsentementsActifsPourPatient` |
| `TransfertContract` | `InitierTransfert`, `ConfirmerReception`, `ConsulterTransfert`, `TransfertsParPatient` |

Points de conception :

- **Immuabilité** : aucune fonction de mise à jour ni de suppression ; un
  identifiant déjà utilisé est refusé.
- **Contrôles avant écriture** (`chaincode/validation.go`) : empreinte SHA-256
  de 64 caractères hexadécimaux, code patient pseudonymisé (même format),
  code de centre technique (1 à 32 caractères parmi lettres, chiffres, `_`,
  `-`), métadonnées en liste blanche.
- **Double horodatage** : `horodatage` (date déclarée par l'application) et
  `horodatageTransaction` (lu par `GetTxTimestamp()`, identique chez tous les
  pairs). L'horodatage de transaction est fixé et signé par le client qui
  soumet ; il n'est pas soumis au consensus. Le consensus garantit l'**ordre**
  des transactions.
- **Recherche par centre** par clé composite `codeCentre~idEvenement`
  (`GetStateByPartialCompositeKeyWithPagination`) : compatible LevelDB, et
  sans le risque d'injection de l'ancienne requête riche CouchDB.
- **Champs facultatifs** déclarés avec la balise `metadata:",optional"` :
  sans elle, `fabric-contract-api-go` refuse de restituer un enregistrement où
  ils sont absents (anomalie corrigée en version 1.2).

Historique du déploiement :

| Version | Séquence | Apport |
|---|---|---|
| 1.0 | 1 | Version initiale |
| 1.1 | 2 | Contrôles de conformité, horodatage de transaction, index par centre, politique `AND` explicite |
| 1.2 | 3 | Champs facultatifs déclarés dans le schéma |

### 2.3 Passerelle REST (Go)

Emplacement : `blockchain/gateway/`. Installée dans
`/usr/local/bin/blockchain-gateway`, service `systemd` `blockchain-gateway`,
à l'écoute sur **`127.0.0.1:8090` uniquement**, identité `Org1MSP`. La
collecte de la signature d'Org2MSP est assurée par le service Gateway du pair.

| Méthode | Point d'accès | Fonction |
|---|---|---|
| GET | `/sante` | Disponibilité |
| POST | `/evenements` | Ancrage |
| GET | `/evenements/{id}` | Consultation |
| POST | `/evenements/{id}/verifier` | Vérification d'une empreinte recalculée |
| GET | `/entites/{type}/{id}/historique` | Toutes les versions d'une entité |
| POST, GET | `/consentements` | Octroi ; consentements actifs d'un patient |
| POST | `/consentements/{id}/revoquer` | Révocation |
| POST, GET | `/transferts` | Initiation ; transferts d'un patient |
| GET, POST | `/transferts/{id}`, `/transferts/{id}/confirmer` | Consultation, confirmation |

Avant tout appel au réseau, la passerelle applique les mêmes contrôles que le
chaincode (`validation.go`), refuse les champs inconnus et limite le corps des
requêtes à 1 Mo. Une requête non conforme reçoit une réponse **400** avec un
message explicite.

### 2.4 Application Django `blockchain_bridge`

| Fichier | Rôle |
|---|---|
| `models.py` | `AncrageBlockchain` : une ligne par version ancrée (identifiant, version, empreinte, transaction, statut) |
| `hashing.py` | Empreinte canonique par type d'entité (JSON trié puis SHA-256) et recalcul pour la vérification |
| `services.py` | Pseudonymisation, identifiants publics, normalisation des métadonnées, ancrage versionné, vérification |
| `signals.py` | Déclenchement des ancrages après validation de la transaction |
| `admin.py` | Consultation en lecture seule, action « Vérifier l'intégrité » |
| `management/commands/reessayer_ancrages.py` | Reprise des ancrages restés en erreur |

---

## 3. Protection des données

### 3.1 Ce qui est inscrit sur le registre

| Champ | Contenu inscrit | Jamais inscrit |
|---|---|---|
| `idEvenement` | `type:identifiant_public:vN` | numéro interne (`CONS…`, `FAC…`) |
| `idEntite` | identifiant public (32 caractères, HMAC) | identifiant interne |
| `codePatient` | pseudonyme (64 caractères, HMAC) | code patient en clair |
| `empreinteHash` | SHA-256 de l'enregistrement | contenu de l'enregistrement |
| `metadonnees` | clés de la liste blanche, valeurs techniques | nom de fichier, texte libre |

Liste blanche des métadonnées, identique dans Django, la passerelle et le
chaincode : `version_schema`, `type_document`, `code_examen`,
`type_message_hprim`. Valeurs : 1 à 64 caractères parmi lettres, chiffres,
`.`, `_`, `:`, `-` (ni espace, ni accent, donc aucun texte libre).

### 3.2 Pseudonymisation

Le code patient et l'identifiant de chaque enregistrement sont transformés
par HMAC-SHA256 avec la clé `BLOCKCHAIN_CLE_PSEUDONYMISATION`, connue du seul
CMS WALE. Sans cette clé, un membre du canal ne peut ni retrouver un
identifiant interne, ni relier deux pseudonymes à une même personne. La
correspondance n'existe que dans la table locale `AncrageBlockchain`.

**La clé ne doit jamais changer** (un même patient aurait sinon deux
pseudonymes), doit être **sauvegardée** avec les autres secrets, et ne doit
**jamais** être versionnée dans Git ni communiquée à une autre organisation.

### 3.3 Défense en profondeur

1. **Django** normalise et pseudonymise avant l'envoi ; des métadonnées non
   conformes ne sont jamais envoyées (ancrage marqué en erreur).
2. **La passerelle** rejette toute requête non conforme (400).
3. **Le chaincode** refuse toute écriture non conforme.

Pourquoi trois niveaux : l'événement de test `TEST-FABRIC:001`, ancré avant
la mise en place de ces contrôles, porte un code patient en clair qui ne
pourra **jamais** être effacé du registre. Les données étant fictives, c'est
sans conséquence ; mais sur un registre immuable, une erreur ne se corrige
pas après coup.

---

## 4. Versionnement des ancrages

### 4.1 Principe

Chaque **état distinct** d'un enregistrement est ancré sous une version
propre, avec l'identifiant `type:identifiant_public:vN`. Toutes les versions
d'une entité partagent le même `idEntite` : `HistoriqueEntite` les restitue
toutes, ce qui reconstitue la chronologie des modifications.

| Situation lors d'un déclenchement | Comportement |
|---|---|
| Aucun ancrage antérieur | Version 1 créée et soumise |
| Dernière version confirmée, même empreinte | Rien n'est envoyé (état déjà ancré) |
| Dernière version confirmée, empreinte différente | Nouvelle version créée et soumise |
| Dernière version en erreur ou en attente | Même version retentée avec l'état courant |
| La version existe déjà sur la chaîne avec une autre empreinte | La chaîne fait foi : la version est enregistrée avec l'empreinte inscrite, puis l'état courant est ancré comme version suivante |

### 4.2 Ce que la vérification établit

La vérification porte toujours sur la **dernière version confirmée** :

- une modification faite **par l'application** a été ancrée comme nouvelle
  version : la vérification est conforme, et la modification reste tracée
  sur le registre (version, date, organisation émettrice) ;
- une modification faite **hors de l'application** (requête SQL directe,
  restauration de sauvegarde altérée…) ne produit aucune version : la
  vérification signale une **altération**.

Vérifier une version antérieure renvoie le résultat pour la dernière
version, avec une remarque indiquant qu'elle a été remplacée.

### 4.3 Limites

- Un état qui n'a jamais été confirmé (par exemple, deux modifications
  successives pendant une panne de la passerelle) n'est pas ancré : seule la
  version retentée, avec l'état courant, l'est.
- Lors d'une reprise, c'est l'état au moment de la reprise qui est ancré.
  D'où l'intérêt d'une reprise fréquente (§ 7.3).

---

## 5. Intégration à Django

### 5.1 Entités ancrées et déclencheurs

| Entité | `type_entite` | Déclencheur |
|---|---|---|
| `patients.Patient` | `patient` | création, puis chaque modification des champs couverts par l'empreinte |
| `consultations.Consultation` | `consultation` | toute sauvegarde au statut `termine` |
| `consultations.Ordonnance` | `ordonnance` | toute sauvegarde d'une ordonnance hors consultation |
| `facturation.Facture` | `facture` | toute sauvegarde au statut `emise` |
| `facturation.Paiement` | `paiement` | création, puis chaque modification |
| `laboratoire.EchangeHPRIM` | `echange_hprim` | envoi `transmis` (ORM) ou réception `traite` (ORU/ERR) |
| `laboratoire.AnalyseLaboratoire` | `analyse_laboratoire` | validation, appel explicite depuis `integrer_oru` après rattachement des résultats |

Grâce au versionnement, un déclenchement sur une sauvegarde qui ne modifie
aucun champ couvert par l'empreinte n'envoie rien au registre.

L'empreinte d'un échange HPRIM porte sur le **contenu brut du message**,
exactement les octets transmis au laboratoire ou reçus de lui. L'ancrage de
l'analyse validée est déclenché explicitement, et non par un signal, parce
qu'au passage au statut `valide` les résultats ne sont pas encore attachés :
un ancrage à ce moment aurait figé un jeu de résultats incomplet.

### 5.2 Moment de l'ancrage

Tout ancrage est différé après la validation de la transaction de base de
données (`transaction.on_commit`) : un événement inscrit étant définitif, il
ne doit jamais porter sur une donnée dont l'enregistrement serait annulé.
L'empreinte est calculée à ce moment, sur l'état validé.

### 5.3 Aucun blocage de l'activité

Aucune défaillance de la couche de preuve n'interrompt un soin, une
facturation ou un import HPRIM : erreur réseau, rejet de la passerelle ou
erreur inattendue sont journalisés, et l'ancrage est marqué `erreur`. Le délai
d'attente de la passerelle est de 15 secondes.

### 5.4 Vérification depuis l'administration

**Blockchain → Ancrages blockchain**, sélectionner une ou plusieurs lignes,
action **« Vérifier l'intégrité »**. Le message indique la version vérifiée,
ou signale une altération.

---

## 6. Configuration

Dans `.env` :

```
BLOCKCHAIN_ENABLED=False
BLOCKCHAIN_GATEWAY_URL=http://127.0.0.1:8090
BLOCKCHAIN_CLE_PSEUDONYMISATION=<64 caractères hexadécimaux>
```

Génération de la clé (une seule fois, à conserver) :

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Si `BLOCKCHAIN_ENABLED` vaut `True` sans clé, aucun ancrage n'est tenté et
l'erreur est journalisée.

---

## 7. Exploitation

### 7.1 Règle absolue

**Ne jamais lancer `./network.sh down`** : la commande détruit le registre,
le canal et les certificats. Sauvegarder `~/preuves-memoire` et la clé HMAC
hors du serveur.

### 7.2 Mettre à jour le chaincode

```bash
cp -r /opt/SEGHO_WALE/blockchain/chaincode/dossier-medical ~/sauvegardes/dossier-medical-$(date +%Y%m%d)
cd /home/segho/hyperledger/fabric-samples/test-network
./network.sh deployCC -c seghochannel -ccn dossier-medical \
  -ccp /opt/SEGHO_WALE/blockchain/chaincode/dossier-medical -ccl go \
  -ccv <version suivante> -ccs <séquence suivante> \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')"
```

Vérification :

```bash
export PATH=${PWD}/../bin:$PATH FABRIC_CFG_PATH=${PWD}/../config/
source ./scripts/envVar.sh && setGlobals 1
peer lifecycle chaincode querycommitted -C seghochannel -n dossier-medical --output json
```

### 7.3 Activer l'ancrage en production (sur décision de l'établissement)

1. Sauvegarder la clé HMAC hors du serveur.
2. Vérifier la passerelle : `curl -s http://127.0.0.1:8090/sante`.
3. Planifier la reprise des ancrages en erreur, par exemple toutes les
   15 minutes (`crontab -e` de l'utilisateur du service) :

   ```
   */15 * * * * cd /opt/SEGHO_WALE && venv/bin/python manage.py reessayer_ancrages >> /var/log/segho/reprise_ancrages.log 2>&1
   ```

4. Passer `BLOCKCHAIN_ENABLED=True` dans `.env` et redémarrer le service
   applicatif.
5. Suivre régulièrement, dans l'administration, les ancrages au statut
   `erreur`.

---

## 8. Tests

### 8.1 Tests unitaires (sans réseau)

```bash
cd /opt/SEGHO_WALE/blockchain/chaincode/dossier-medical && GOTOOLCHAIN=local go test -v ./chaincode/
cd /opt/SEGHO_WALE/blockchain/gateway && GOTOOLCHAIN=local go test -v ./...
cd /opt/SEGHO_WALE && source venv/bin/activate && python manage.py test blockchain_bridge -v 2
```

Les tests Django créent une base temporaire : l'utilisateur PostgreSQL doit
disposer du droit `CREATEDB` pendant la phase de tests.

### 8.2 Tests contre le réseau

Avec des données **fictives** uniquement, par la passerelle :

```bash
EMPREINTE=$(printf 'TEST-FICTIF' | sha256sum | cut -d' ' -f1)
PATIENT=$(printf 'PATIENT-FICTIF' | sha256sum | cut -d' ' -f1)
curl -s -i -X POST http://127.0.0.1:8090/evenements -H 'Content-Type: application/json' \
  -d "{\"idEvenement\":\"TEST-FICTIF:v1\",\"typeEntite\":\"consultation\",\"idEntite\":\"1\",\"codePatient\":\"$PATIENT\",\"codeCentre\":\"WALE\",\"empreinteHash\":\"$EMPREINTE\",\"horodatage\":\"2026-10-15T10:00:00Z\",\"metadonnees\":{\"type_document\":\"consultation\"}}"
```

Preuve de l'exigence de double signature : soumettre une transaction avec le
seul pair d'Org1MSP (`peer chaincode invoke … --peerAddresses localhost:7051`)
doit aboutir à `ENDORSEMENT_POLICY_FAILURE`.

### 8.3 Démonstration de la détection d'une altération

Sur une **base de test**, jamais en production :

1. Créer un patient fictif avec l'ancrage activé ; vérifier que l'ancrage
   apparaît au statut `Confirmé`.
2. Le modifier **depuis l'application** : une version 2 apparaît, et la
   vérification est conforme.
3. Le modifier **sans passer par l'application**, par exemple dans
   `python manage.py shell` avec
   `Patient.objects.filter(pk=…).update(allergies='modification hors application')`
   (`update()` ne déclenche aucun signal) : la vérification signale une
   **altération**.

### 8.4 Preuves conservées

Les sorties des essais du 14 et 15 octobre 2026 sont conservées dans
`~/preuves-memoire/` (fichiers `01` à `12`) : tests unitaires, déploiements,
définition du chaincode, essais A à O, test de bout en bout.

---

## 9. Limites connues

- Réseau de démonstration : identités `cryptogen`, deux organisations sur un
  même serveur (pas de résilience géographique), passerelle sous une seule
  identité.
- `ConsentementContract` et `TransfertContract` sont exposés par la
  passerelle mais ne sont reliés à aucun écran Django ; la confirmation d'un
  transfert par l'organisation destinataire n'a pas été éprouvée.
- L'horodatage de transaction n'est pas soumis au consensus (§ 2.2).
- L'empreinte d'un dossier patient porte sur des champs en partie prévisibles
  (nom, date de naissance, sexe) : un membre du canal qui les connaît pourrait
  tenter de vérifier par calcul la présence d'une personne. L'ajout d'un
  secret au calcul de l'empreinte supprimerait ce risque.
- Journal d'audit ancré, supervision de l'usage des modules, interface FHIR et
  stockage des documents (MinIO) : prévus dans la conception, non réalisés.
- Hors blockchain : des échecs de tests liés aux permissions (403 au lieu de
  302) avaient été signalés dans d'autres applications ; à revérifier.

---

## 10. Arborescence

```
blockchain/
  README.md
  chaincode/dossier-medical/
    main.go, go.mod
    chaincode/
      types.go, validation.go
      integrite_contract.go       + integrite_contract_test.go
      consentement_contract.go    + consentement_contract_test.go
      transfert_contract.go       + transfert_contract_test.go
      mocks/mocks.go
  gateway/
    main.go, fabric_client.go, handlers.go, validation.go, handlers_test.go
    config.example.yaml           (config.yaml : local, non versionné)
  network/                        (configuration à 3 organisations, non utilisée)

blockchain_bridge/
  models.py, hashing.py, services.py, signals.py, admin.py, tests.py
  management/commands/reessayer_ancrages.py
  migrations/0001 à 0003
```
