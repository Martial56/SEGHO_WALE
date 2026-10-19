# Blockchain — SEGHO-WALE

Couche de preuve de SEGHO-WALE : un registre Hyperledger Fabric sur lequel
sont ancrées les **empreintes** des enregistrements de l'application, afin de
prouver qu'ils n'ont pas été altérés depuis leur ancrage, y compris face à un
administrateur du système.

Documentation détaillée (fonctionnement, exploitation, tests) :
[`docs/integration_blockchain.md`](../docs/integration_blockchain.md).

## Principe : la preuve sur le registre, la donnée dans Django

Le registre est **immuable** et **répliqué chez chaque organisation** du
canal. Une donnée qui y est inscrite ne peut jamais en être effacée. Aucune
donnée personnelle ni aucune donnée de santé n'y figure donc, pas même un
identifiant interne :

| Champ inscrit | Contenu |
|---|---|
| `idEvenement` | `type:identifiant_public:vN` (exemple : `consultation:33f6…:v1`) |
| `idEntite` | identifiant public de 32 caractères, dérivé par HMAC-SHA256 |
| `codePatient` | pseudonyme HMAC-SHA256 de 64 caractères |
| `empreinteHash` | SHA-256 de la représentation canonique de l'enregistrement |
| `codeCentre` | code technique du centre (`WALE`, `TOUMBOKRO`) |
| `metadonnees` | liste blanche : `version_schema`, `type_document`, `code_examen`, `type_message_hprim` |
| `horodatage` / `horodatageTransaction` | date déclarée par l'application / date de la transaction Fabric |

La clé HMAC (`BLOCKCHAIN_CLE_PSEUDONYMISATION`) n'est connue que du CMS WALE.
La correspondance entre identifiant public et identifiant interne n'existe que
dans la table locale `AncrageBlockchain`.

## Réseau déployé

| Élément | Valeur |
|---|---|
| Base | `fabric-samples/test-network`, Hyperledger Fabric 2.5.16 |
| Organisations | `Org1MSP` (site principal, soumet les transactions), `Org2MSP` (contresigne) |
| Nœuds | `peer0.org1.example.com`, `peer0.org2.example.com`, `orderer.example.com` (Raft) |
| Canal | `seghochannel` |
| Base d'état | LevelDB (aucune requête riche CouchDB n'est utilisée) |
| Chaincode | `dossier-medical`, version 1.2, séquence 3 |
| Politique d'endossement | `AND('Org1MSP.peer','Org2MSP.peer')`, déclarée explicitement |

Avec cette politique, **aucune organisation ne peut inscrire seule un
événement** : une transaction approuvée par Org1MSP seule est invalidée
(`ENDORSEMENT_POLICY_FAILURE`).

Il s'agit d'un réseau de démonstration : identités générées par `cryptogen`,
deux organisations sur un même serveur. Le dossier `network/` contient une
configuration à trois organisations (`canal-sante`) préparée au début du
projet ; **elle n'est pas utilisée** par le réseau déployé.

## Structure du dossier

```
chaincode/dossier-medical/   Chaincode Go : 3 contrats + tests unitaires (mocks)
gateway/                     Passerelle REST Go ↔ Fabric Gateway (service blockchain-gateway)
network/                     Configuration à 3 organisations, non utilisée (référence)
```

## Contrats intelligents

- **`IntegriteContract`** : `EnregistrerEvenement`, `ConsulterEvenement`,
  `VerifierIntegrite`, `HistoriqueEntite`, `EvenementsParCentre` (pagination
  par clé composite `codeCentre~idEvenement`). Aucune fonction de mise à jour
  ni de suppression ; un identifiant déjà utilisé est refusé.
- **`ConsentementContract`** : `AccorderConsentement`, `RevoquerConsentement`,
  `ConsulterConsentement`, `ConsentementsActifsPourPatient`.
- **`TransfertContract`** : `InitierTransfert`, `ConfirmerReception`,
  `ConsulterTransfert`, `TransfertsParPatient`.

Le chaincode contrôle lui-même chaque écriture : empreinte SHA-256 au bon
format, code patient pseudonymisé, code de centre technique, métadonnées en
liste blanche. Les champs facultatifs portent la balise `metadata:",optional"`,
indispensable pour relire les enregistrements où ils sont absents.

## Passerelle REST

Service `systemd` `blockchain-gateway`, à l'écoute sur `127.0.0.1:8090`
uniquement, identité `Org1MSP`. Elle applique les mêmes contrôles que le
chaincode avant tout appel au réseau, refuse les champs inconnus et limite les
requêtes à 1 Mo.

```bash
curl -s http://127.0.0.1:8090/sante        # {"statut":"ok"}
```

## Versionnement des ancrages

Chaque état distinct d'un enregistrement est ancré sous une version propre
(`:v1`, `:v2`…). Une modification faite **par l'application** produit une
nouvelle version : elle est donc tracée sur le registre, avec sa date et
l'organisation émettrice. Une modification faite **hors de l'application**
(par exemple directement en base) ne produit aucune version et est détectée
comme une altération lors de la vérification. Voir la documentation
détaillée, § 4.

## Tests

```bash
# Chaincode (sans réseau, grâce aux mocks)
cd blockchain/chaincode/dossier-medical && GOTOOLCHAIN=local go test ./chaincode/

# Passerelle (sans réseau)
cd blockchain/gateway && GOTOOLCHAIN=local go test ./...

# Intégration Django
python manage.py test blockchain_bridge
```

## Règles d'exploitation

- **Ne jamais lancer `./network.sh down`** : cette commande détruit le
  registre, le canal et les certificats.
- Toute modification du chaincode se déploie avec une **nouvelle séquence**
  (`-ccv` et `-ccs` incrémentés) et la politique explicite
  `-ccep "AND('Org1MSP.peer','Org2MSP.peer')"`.
- `BLOCKCHAIN_ENABLED` reste à `False` en production tant que l'activation n'a
  pas été décidée.
