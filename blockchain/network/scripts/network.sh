#!/usr/bin/env bash
# Orchestration du réseau de démonstration "canal-sante" : up|down|createChannel|deployCC.
#
# Prérequis : Docker Desktop (avec `docker compose`), et generate.sh déjà
# exécuté (crypto-config/ et channel-artifacts/ présents).
#
# Non exécuté dans l'environnement de développement de cette session (pas de
# Docker disponible) — à lancer par l'utilisateur, depuis blockchain/network.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_DIR="$(dirname "$SCRIPT_DIR")"
cd "$NETWORK_DIR"

CHANNEL_NAME="canal-sante"
CC_NAME="dossier-medical"
CC_LABEL="${CC_NAME}_1.0"
CC_SRC_IN_CLI="/opt/gopath/src/github.com/hyperledger/fabric/peer/chaincode/dossier-medical"

ORGS=(CentreSante VerificationFacture Regulateur)

exec_cli() {
  docker exec cli bash -c "$1"
}

# Bascule le contexte d'identité de la CLI sur l'organisation donnée
# (CentreSante|VerificationFacture|Regulateur), pour les commandes peer suivantes.
set_globals() {
  local org="$1"
  local port
  case "$org" in
    CentreSante) port=7051 ;;
    VerificationFacture) port=8051 ;;
    Regulateur)  port=9051 ;;
    *) echo "Organisation inconnue: $org" >&2; exit 1 ;;
  esac
  cat <<EOF
export CORE_PEER_LOCALMSPID=${org}MSP
export CORE_PEER_TLS_ROOTCERT_FILE=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/$(to_domain "$org")/peers/peer0.$(to_domain "$org")/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/$(to_domain "$org")/users/Admin@$(to_domain "$org")/msp
export CORE_PEER_ADDRESS=peer0.$(to_domain "$org"):${port}
EOF
}

to_domain() {
  case "$1" in
    CentreSante) echo "centresante.wale-sante.local" ;;
    VerificationFacture) echo "verificationfacture.wale-sante.local" ;;
    Regulateur)  echo "regulateur.wale-sante.local" ;;
  esac
}

networkUp() {
  echo "==> Démarrage des conteneurs (orderer, 3 peers, 3 CouchDB, cli)"
  docker compose -f docker-compose.yaml up -d
}

networkDown() {
  echo "==> Arrêt et nettoyage des conteneurs et volumes"
  docker compose -f docker-compose.yaml down --volumes
}

createChannel() {
  echo "==> Création du canal ${CHANNEL_NAME} (par CentreSanteMSP)"
  exec_cli "$(set_globals CentreSante) && peer channel create \
    -o orderer0.orderer.wale-sante.local:7050 \
    -c ${CHANNEL_NAME} \
    -f ./channel-artifacts/${CHANNEL_NAME}.tx \
    --outputBlock ./channel-artifacts/${CHANNEL_NAME}.block \
    --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.wale-sante.local/orderers/orderer0.orderer.wale-sante.local/tls/ca.crt"

  for org in "${ORGS[@]}"; do
    echo "==> ${org}MSP rejoint le canal"
    exec_cli "$(set_globals "$org") && peer channel join -b ./channel-artifacts/${CHANNEL_NAME}.block"

    echo "==> Mise à jour du peer ancre pour ${org}MSP"
    exec_cli "$(set_globals "$org") && peer channel update \
      -o orderer0.orderer.wale-sante.local:7050 \
      -c ${CHANNEL_NAME} \
      -f ./channel-artifacts/${org}MSPanchors.tx \
      --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.wale-sante.local/orderers/orderer0.orderer.wale-sante.local/tls/ca.crt"
  done
}

deployChaincode() {
  echo "==> Empaquetage du chaincode ${CC_NAME}"
  exec_cli "cd ${CC_SRC_IN_CLI} && GO111MODULE=on go mod vendor"
  exec_cli "peer lifecycle chaincode package ${CC_NAME}.tar.gz \
    --path ${CC_SRC_IN_CLI} --lang golang --label ${CC_LABEL}"

  for org in "${ORGS[@]}"; do
    echo "==> Installation du chaincode chez ${org}MSP"
    exec_cli "$(set_globals "$org") && peer lifecycle chaincode install ${CC_NAME}.tar.gz"
  done

  echo "==> Récupération du package ID"
  PACKAGE_ID=$(exec_cli "$(set_globals CentreSante) && peer lifecycle chaincode queryinstalled" | grep "${CC_LABEL}" | sed -n 's/^Package ID: \(.*\), Label:.*$/\1/p')
  echo "Package ID: ${PACKAGE_ID}"

  for org in "${ORGS[@]}"; do
    echo "==> Approbation par ${org}MSP"
    exec_cli "$(set_globals "$org") && peer lifecycle chaincode approveformyorg \
      -o orderer0.orderer.wale-sante.local:7050 \
      --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.wale-sante.local/orderers/orderer0.orderer.wale-sante.local/tls/ca.crt \
      --channelID ${CHANNEL_NAME} --name ${CC_NAME} --version 1.0 --package-id ${PACKAGE_ID} --sequence 1"
  done

  echo "==> Commit du chaincode sur le canal"
  exec_cli "$(set_globals CentreSante) && peer lifecycle chaincode commit \
    -o orderer0.orderer.wale-sante.local:7050 \
    --tls --cafile /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/ordererOrganizations/orderer.wale-sante.local/orderers/orderer0.orderer.wale-sante.local/tls/ca.crt \
    --channelID ${CHANNEL_NAME} --name ${CC_NAME} --version 1.0 --sequence 1 \
    --peerAddresses peer0.centresante.wale-sante.local:7051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/centresante.wale-sante.local/peers/peer0.centresante.wale-sante.local/tls/ca.crt \
    --peerAddresses peer0.verificationfacture.wale-sante.local:8051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/verificationfacture.wale-sante.local/peers/peer0.verificationfacture.wale-sante.local/tls/ca.crt \
    --peerAddresses peer0.regulateur.wale-sante.local:9051 \
    --tlsRootCertFiles /opt/gopath/src/github.com/hyperledger/fabric/peer/crypto/peerOrganizations/regulateur.wale-sante.local/peers/peer0.regulateur.wale-sante.local/tls/ca.crt"

  echo "==> Chaincode ${CC_NAME} déployé sur ${CHANNEL_NAME}"
}

case "${1:-}" in
  up) networkUp ;;
  down) networkDown ;;
  createChannel) createChannel ;;
  deployCC) deployChaincode ;;
  *)
    echo "Usage: $0 {up|down|createChannel|deployCC}" >&2
    exit 1
    ;;
esac
