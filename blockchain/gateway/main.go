// Command blockchain-gateway expose en REST, pour une organisation du
// réseau Fabric, les smart contracts du chaincode dossier-medical. Django
// (app blockchain_bridge) l'appelle en HTTP plutôt que de dépendre d'un SDK
// Fabric Python, peu maintenu.
package main

import (
	"flag"
	"log"
	"net/http"
)

func main() {
	configPath := flag.String("config", "config.yaml", "chemin du fichier de configuration de l'organisation")
	flag.Parse()

	cfg, err := LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("échec de chargement de la configuration: %v", err)
	}

	fabric, err := NewFabricClient(cfg)
	if err != nil {
		log.Fatalf("échec de connexion au réseau Fabric: %v", err)
	}
	defer fabric.Close()

	server := NewServer(fabric)

	log.Printf("passerelle blockchain (%s) à l'écoute sur %s", cfg.OrgMSPID, cfg.ListenAddress)
	if err := http.ListenAndServe(cfg.ListenAddress, server.Routes()); err != nil {
		log.Fatalf("échec du serveur HTTP: %v", err)
	}
}
