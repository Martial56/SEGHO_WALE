#!/usr/bin/env bash
# Génère le matériel cryptographique (cryptogen) et les artefacts du canal
# (configtxgen) à partir de crypto-config.yaml / configtx.yaml.
#
# Prérequis : les binaires Fabric `cryptogen` et `configtxgen` sur le PATH.
# Ils s'obtiennent avec le script officiel d'installation Hyperledger Fabric :
#   curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh | bash -s -- binary
# puis en ajoutant le dossier `bin/` obtenu au PATH.
#
# Non exécuté dans l'environnement de développement de cette session (pas de
# Docker ni de binaires Fabric disponibles) — à lancer par l'utilisateur.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_DIR="$(dirname "$SCRIPT_DIR")"
cd "$NETWORK_DIR"

for bin in cryptogen configtxgen; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Erreur : '$bin' est introuvable sur le PATH. Voir l'en-tête de ce script pour l'installer." >&2
    exit 1
  fi
done

rm -rf crypto-config channel-artifacts
mkdir -p channel-artifacts

echo "==> Génération du matériel cryptographique (cryptogen)"
cryptogen generate --config=crypto-config.yaml --output=crypto-config

echo "==> Génération du bloc genesis de l'orderer"
FABRIC_CFG_PATH="$NETWORK_DIR" configtxgen \
  -profile ReseauSanteOrdererGenesis \
  -channelID system-channel \
  -outputBlock ./channel-artifacts/genesis.block

echo "==> Génération de la transaction de création du canal canal-sante"
FABRIC_CFG_PATH="$NETWORK_DIR" configtxgen \
  -profile CanalSante \
  -channelID canal-sante \
  -outputCreateChannelTx ./channel-artifacts/canal-sante.tx

for org in CentreSante VerificationFacture Regulateur; do
  echo "==> Mise à jour d'ancrage pour ${org}MSP"
  FABRIC_CFG_PATH="$NETWORK_DIR" configtxgen \
    -profile CanalSante \
    -channelID canal-sante \
    -outputAnchorPeersUpdate "./channel-artifacts/${org}MSPanchors.tx" \
    -asOrg "${org}MSP"
done

echo "==> Terminé. Matériel dans ./crypto-config, artefacts dans ./channel-artifacts"
