# Blockchain — SEGHO-WALE

Couche blockchain (Hyperledger Fabric) garantissant l'**intégrité**, la
**traçabilité** et la **sécurité** des données médicales, et une
**interopérabilité fiable** entre les acteurs de la prise en charge du
patient : le centre de santé, les assureurs et le régulateur (Ministère de la
Santé).

## Principe : hash on-chain, données off-chain

Aucune donnée médicale en clair ne transite sur le registre partagé. Seuls
sont ancrés : un **hash SHA-256** de l'enregistrement, son type, un
identifiant métier (`PAT…`, `CONS…`, `FAC…`) et des métadonnées non
sensibles (centre, horodatage). Les dossiers complets restent dans la base
Django de chaque centre. La blockchain sert à prouver, entre organisations
qui ne se font pas mutuellement confiance, qu'un enregistrement n'a pas été
altéré depuis son ancrage — pas à le stocker.

## Organisations du réseau

| Organisation | MSP ID | Rôle |
|---|---|---|
| Centre de santé (CMS WALÉ) | `CentreSanteMSP` | soumet l'essentiel des événements (dossiers patients, consultations, ordonnances, factures) |
| VerificationFacture | `VerificationFactureMSP` | vérifie les faits liés à la facturation/remboursement sans voir le dossier médical complet |
| Régulateur (Ministère de la Santé) | `RegulateurMSP` | audit, déclarations épidémiologiques obligatoires, registre de vaccination |

Les 3 organisations partagent un canal unique, `canal-sante` : les données
qui y circulent n'étant que des empreintes et métadonnées, un canal unique
suffit (pas de collection de données privées nécessaire au stade actuel).

## Structure du dossier

```
chaincode/dossier-medical/   Chaincode Go (3 smart contracts), voir plus bas
network/                     Configuration Fabric (configtx, crypto-config, docker-compose, scripts)
gateway/                     Passerelle REST Go ↔ Fabric Gateway, appelée par Django
```

## Smart contracts

- **`IntegriteContract`** — ancre l'empreinte de tout enregistrement
  (`EnregistrerEvenement`), immuable (aucune mise à jour/suppression
  exposée), interrogeable par entité (`HistoriqueEntite`) ou par centre
  (`EvenementsParCentre`, requête riche CouchDB), et vérifiable
  (`VerifierIntegrite` compare le hash ancré à un hash recalculé côté
  applicatif).
- **`ConsentementContract`** — octroi/révocation d'autorisations d'accès
  qu'un patient (ou le centre en son nom) accorde à une autre organisation,
  sur un périmètre et une durée donnés.
- **`TransfertContract`** — notarise les transferts de patients entre
  centres : le centre destinataire confirme la réception avec l'empreinte du
  dossier reçu, comparée à celle notariée par le centre d'origine, prouvant
  l'absence d'altération pendant le transfert.

## Portée de l'intégration Django (côté `blockchain_bridge/`)

Seul l'ancrage automatique via `IntegriteContract` est câblé sur les
signaux `post_save` des modèles existants (Patient, Consultation, Ordonnance,
Facture, Paiement). `ConsentementContract` et `TransfertContract` sont
pleinement implémentés et exposés par la passerelle REST, mais pas encore
reliés à une interface Django : les workflows métier correspondants (recueil
de consentement patient, transfert inter-centres) n'existent pas encore dans
l'application. Les brancher est une extension naturelle, pas une
réinvention.

### Cas central : l'échange HPRIM avec le laboratoire (`laboratoire/hprim/`)

C'est le point d'interopérabilité inter-systèmes le plus concret du projet :
SEGHO-WALE échange par FTP, au format HPRIM Santé v2.4, des demandes
d'examens (ORM) et des résultats (ORU, ou une erreur ERR) avec le système du
laboratoire externe (SYSLAM) — deux logiciels différents, deux acteurs
différents, aucune confiance mutuelle a priori. C'est exactement le scénario
que `IntegriteContract` sert à sécuriser, et il est câblé de bout en bout :

- **`EchangeHPRIM`** (`blockchain_bridge/signals.py::ancrer_echange_hprim`) —
  chaque message *réellement* échangé est ancré : l'envoi d'une demande une
  fois transmise par FTP (`sens='envoi'`, `statut='transmis'`), et la
  réception d'un résultat ou d'une erreur une fois intégrée
  (`sens='reception'`, `statut='traite'`, que le contexte soit ORU ou ERR).
  Les tentatives internes en échec (FTP indisponible, config absente) ne sont
  pas ancrées : rien n'a alors franchi la frontière inter-systèmes. L'empreinte
  porte sur le **contenu brut du message HPRIM** (`EchangeHPRIM.contenu`) —
  exactement les octets transmis au/reçus du laboratoire, avant toute
  interprétation côté SEGHO. Tous les événements liés à un même échange
  partagent `type_entite='echange_hprim'`, consultables via
  `IntegriteContract.HistoriqueEntite`.
- **`AnalyseLaboratoire`** (`blockchain_bridge/signals.py::ancrer_analyse_laboratoire_validee`) —
  une fois un résultat validé (`statut='valide'`), le résultat structuré
  côté SEGHO (paramètres, valeurs, unités, interprétation) est ancré à son
  tour. Appelé explicitement depuis
  `laboratoire/hprim/integration.py::integrer_oru`, juste après que les
  `ResultatAnalyse` d'une analyse ont été créées — **pas** via un signal
  `post_save` générique sur `AnalyseLaboratoire` : au moment où son `statut`
  passe à `valide` pendant un import HPRIM, ses résultats ne sont pas encore
  attachés (ils le sont juste après, dans la même fonction) ; ancrer sur ce
  seul signal aurait figé un jeu de résultats incomplet — un cas testé
  explicitement dans `blockchain_bridge/tests.py`.

Cette double empreinte donne une chaîne de traçabilité complète et vérifiable
indépendamment à chaque étape : *demande envoyée* → *résultat brut reçu du
labo* → *résultat validé cliniquement par SEGHO* — chacune comparable à tout
moment à l'état courant de la base via l'action admin « Vérifier
l'intégrité ».

## Lancer le réseau (à faire par vous — Docker n'était pas disponible dans
l'environnement où ce code a été écrit)

Prérequis : Docker Desktop, Git Bash ou WSL2, les binaires Fabric
(`cryptogen`, `configtxgen`, `peer`) sur le PATH — voir l'en-tête de
`network/scripts/generate.sh` pour les obtenir.

```bash
cd blockchain/network
./scripts/generate.sh      # matériel crypto + artefacts du canal
./scripts/network.sh up
./scripts/network.sh createChannel
./scripts/network.sh deployCC
```

Puis démarrer la passerelle (côté CentreSante, celle que Django appelle) :

```bash
cd blockchain/gateway
cp config.example.yaml config.yaml   # adapter les chemins si besoin
go mod tidy
go run . -config config.yaml
```

Côté Django, activer l'intégration dans `.env` :

```
BLOCKCHAIN_ENABLED=True
BLOCKCHAIN_GATEWAY_URL=http://localhost:8090
```

## Vérifier le chaincode sans Docker

Les contrats sont testables unitairement sans réseau Fabric, via des
doubles de test (`chaincode/dossier-medical/chaincode/mocks`) :

```bash
cd blockchain/chaincode/dossier-medical
go mod tidy   # nécessite un accès internet la première fois
go build ./...
go vet ./...
go test ./...
```

Ce code a été écrit et relu manuellement, mais **non compilé** dans
l'environnement de développement de cette session (ni Docker, ni accès
internet pour récupérer les modules Go Hyperledger n'y étaient disponibles).
`go build`/`go test` ci-dessus doivent être la première chose lancée avant
tout déploiement.

## Évolutions possibles

- Passer de `cryptogen` à une Fabric CA par organisation pour un
  provisionnement d'identités plus réaliste.
- Orderer etcdraft à 3 nœuds (au lieu d'1) pour la tolérance aux pannes.
- Collections de données privées si des métadonnées elles-mêmes devenaient
  sensibles (aujourd'hui, seuls des hash y transitent).
- Brancher `ConsentementContract`/`TransfertContract` à des vues Django
  dédiées une fois ces workflows métier définis.
