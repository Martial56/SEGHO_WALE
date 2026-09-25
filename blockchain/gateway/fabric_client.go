package main

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-gateway/pkg/identity"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"gopkg.in/yaml.v3"
)

// Config décrit l'identité et le point de connexion Fabric d'une
// organisation. Une instance de la passerelle sert une seule organisation :
// on en démarre une par acteur du réseau (CentreSante, VerificationFacture,
// Regulateur), chacune avec son propre config.yaml.
type Config struct {
	OrgMSPID      string `yaml:"org_msp_id"`
	PeerEndpoint  string `yaml:"peer_endpoint"`
	PeerTLSCACert string `yaml:"peer_tls_ca_cert"`
	GatewayPeer   string `yaml:"gateway_peer"`
	CertPath      string `yaml:"cert_path"`
	KeyPath       string `yaml:"key_path"`
	ChannelName   string `yaml:"channel_name"`
	ChaincodeName string `yaml:"chaincode_name"`
	ListenAddress string `yaml:"listen_address"`
}

func LoadConfig(path string) (Config, error) {
	var cfg Config
	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, fmt.Errorf("échec de lecture de %s: %w", path, err)
	}
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("échec de lecture du YAML de configuration: %w", err)
	}
	if cfg.ListenAddress == "" {
		cfg.ListenAddress = ":8090"
	}
	return cfg, nil
}

// FabricClient encapsule la connexion Gateway au peer Fabric de
// l'organisation, avec un handle par smart contract nommé du chaincode
// dossier-medical.
type FabricClient struct {
	connection   *grpc.ClientConn
	gateway      *client.Gateway
	Integrite    *client.Contract
	Consentement *client.Contract
	Transfert    *client.Contract
}

// NewFabricClient établit la connexion gRPC + Gateway et résout les 3
// contrats nommés du chaincode dossier-medical sur le canal configuré.
func NewFabricClient(cfg Config) (*FabricClient, error) {
	connection, err := newGrpcConnection(cfg)
	if err != nil {
		return nil, fmt.Errorf("échec de connexion gRPC au peer: %w", err)
	}

	id, err := newIdentity(cfg)
	if err != nil {
		connection.Close()
		return nil, fmt.Errorf("échec de chargement de l'identité: %w", err)
	}

	sign, err := newSign(cfg)
	if err != nil {
		connection.Close()
		return nil, fmt.Errorf("échec de chargement de la clé de signature: %w", err)
	}

	gateway, err := client.Connect(
		id,
		client.WithSign(sign),
		client.WithClientConnection(connection),
		client.WithEvaluateTimeout(5*time.Second),
		client.WithEndorseTimeout(15*time.Second),
		client.WithSubmitTimeout(5*time.Second),
		client.WithCommitStatusTimeout(1*time.Minute),
	)
	if err != nil {
		connection.Close()
		return nil, fmt.Errorf("échec de connexion à la passerelle Fabric: %w", err)
	}

	network := gateway.GetNetwork(cfg.ChannelName)

	return &FabricClient{
		connection:   connection,
		gateway:      gateway,
		Integrite:    network.GetContractWithName(cfg.ChaincodeName, "IntegriteContract"),
		Consentement: network.GetContractWithName(cfg.ChaincodeName, "ConsentementContract"),
		Transfert:    network.GetContractWithName(cfg.ChaincodeName, "TransfertContract"),
	}, nil
}

// Close libère la connexion Gateway et la connexion gRPC sous-jacente.
func (c *FabricClient) Close() {
	c.gateway.Close()
	c.connection.Close()
}

func newGrpcConnection(cfg Config) (*grpc.ClientConn, error) {
	caCertPEM, err := os.ReadFile(cfg.PeerTLSCACert)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture du certificat CA du peer: %w", err)
	}

	certPool := x509.NewCertPool()
	if !certPool.AppendCertsFromPEM(caCertPEM) {
		return nil, fmt.Errorf("échec d'ajout du certificat CA au pool")
	}

	transportCredentials := credentials.NewTLS(&tls.Config{
		RootCAs:    certPool,
		ServerName: cfg.GatewayPeer,
	})

	return grpc.Dial(cfg.PeerEndpoint, grpc.WithTransportCredentials(transportCredentials))
}

func newIdentity(cfg Config) (*identity.X509Identity, error) {
	certificatePEM, err := os.ReadFile(cfg.CertPath)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture du certificat client: %w", err)
	}

	certificate, err := identity.CertificateFromPEM(certificatePEM)
	if err != nil {
		return nil, fmt.Errorf("échec de décodage du certificat client: %w", err)
	}

	return identity.NewX509Identity(cfg.OrgMSPID, certificate)
}

// newSign charge la clé privée du client. `cfg.KeyPath` pointe vers le
// dossier `keystore` généré par cryptogen, qui ne contient qu'un seul
// fichier dont le nom (un hash) n'est pas prévisible à l'avance.
func newSign(cfg Config) (identity.Sign, error) {
	files, err := os.ReadDir(cfg.KeyPath)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture du dossier de clés %s: %w", cfg.KeyPath, err)
	}
	if len(files) == 0 {
		return nil, fmt.Errorf("aucune clé privée trouvée dans %s", cfg.KeyPath)
	}

	privateKeyPEM, err := os.ReadFile(filepath.Join(cfg.KeyPath, files[0].Name()))
	if err != nil {
		return nil, fmt.Errorf("échec de lecture de la clé privée: %w", err)
	}

	privateKey, err := identity.PrivateKeyFromPEM(privateKeyPEM)
	if err != nil {
		return nil, fmt.Errorf("échec de décodage de la clé privée: %w", err)
	}

	return identity.NewPrivateKeySign(privateKey)
}
