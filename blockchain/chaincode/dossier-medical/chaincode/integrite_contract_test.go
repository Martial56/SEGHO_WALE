package chaincode_test

import (
	"testing"

	"github.com/wale-sante/dossier-medical-cc/chaincode"
	"github.com/wale-sante/dossier-medical-cc/chaincode/mocks"
)

func TestEnregistrerEvenement(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}

	err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntiteConsultation, "CONS20250001", "PAT20250001", "WALE", "abc123hash", "2025-01-10T09:00:00Z", "")
	if err != nil {
		t.Fatalf("EnregistrerEvenement a échoué: %v", err)
	}

	evenement, err := contract.ConsulterEvenement(ctx, "EVT-001")
	if err != nil {
		t.Fatalf("ConsulterEvenement a échoué: %v", err)
	}
	if evenement.EmpreinteHash != "abc123hash" {
		t.Errorf("empreinte attendue abc123hash, obtenue %s", evenement.EmpreinteHash)
	}
	if evenement.OrgEmettrice != "CentreSanteMSP" {
		t.Errorf("org émettrice attendue CentreSanteMSP, obtenue %s", evenement.OrgEmettrice)
	}
	if ctx.Stub.LastEvent("EvenementEnregistre") == nil {
		t.Errorf("l'événement chaincode EvenementEnregistre aurait dû être émis")
	}
}

func TestEnregistrerEvenementRefuseDoublon(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}

	if err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", "PAT20250001", "WALE", "hash-1", "2025-01-10T09:00:00Z", ""); err != nil {
		t.Fatalf("premier enregistrement inattendu en échec: %v", err)
	}

	err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", "PAT20250001", "WALE", "hash-2", "2025-01-10T09:05:00Z", "")
	if err == nil {
		t.Fatalf("un second enregistrement sous le même idEvenement aurait dû être refusé (registre immuable)")
	}
}

func TestHistoriqueEntite(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}

	_ = contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntiteConsultation, "CONS20250001", "PAT20250001", "WALE", "hash-consultation", "2025-01-10T09:00:00Z", "")
	_ = contract.EnregistrerEvenement(ctx, "EVT-002", chaincode.TypeEntiteFacture, "FAC20250001", "PAT20250001", "WALE", "hash-facture", "2025-01-10T09:30:00Z", "")
	_ = contract.EnregistrerEvenement(ctx, "EVT-003", chaincode.TypeEntiteConsultation, "CONS20250002", "PAT20250002", "WALE", "hash-autre-consultation", "2025-01-11T09:00:00Z", "")

	historique, err := contract.HistoriqueEntite(ctx, chaincode.TypeEntiteConsultation, "CONS20250001")
	if err != nil {
		t.Fatalf("HistoriqueEntite a échoué: %v", err)
	}
	if len(historique) != 1 {
		t.Fatalf("un seul événement attendu pour CONS20250001, obtenu %d", len(historique))
	}
	if historique[0].EmpreinteHash != "hash-consultation" {
		t.Errorf("empreinte attendue hash-consultation, obtenue %s", historique[0].EmpreinteHash)
	}
}

func TestVerifierIntegrite(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}
	_ = contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", "PAT20250001", "WALE", "hash-original", "2025-01-10T09:00:00Z", "")

	conforme, err := contract.VerifierIntegrite(ctx, "EVT-001", "hash-original")
	if err != nil {
		t.Fatalf("VerifierIntegrite a échoué: %v", err)
	}
	if !conforme.Conforme {
		t.Errorf("le hash inchangé aurait dû être conforme")
	}

	nonConforme, err := contract.VerifierIntegrite(ctx, "EVT-001", "hash-modifie")
	if err != nil {
		t.Fatalf("VerifierIntegrite a échoué: %v", err)
	}
	if nonConforme.Conforme {
		t.Errorf("un hash différent aurait dû être signalé non conforme (donnée altérée)")
	}
}
