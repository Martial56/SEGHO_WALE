// Command dossier-medical-cc démarre le chaincode Go du réseau blockchain de
// SEGHO-WALE : ancrage d'intégrité, gestion des consentements patient et
// notarisation des transferts inter-centres.
package main

import (
	"log"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
	"github.com/wale-sante/dossier-medical-cc/chaincode"
)

func main() {
	cc, err := contractapi.NewChaincode(
		&chaincode.IntegriteContract{},
		&chaincode.ConsentementContract{},
		&chaincode.TransfertContract{},
	)
	if err != nil {
		log.Panicf("échec de création du chaincode dossier-medical: %v", err)
	}

	if err := cc.Start(); err != nil {
		log.Panicf("échec de démarrage du chaincode dossier-medical: %v", err)
	}
}
