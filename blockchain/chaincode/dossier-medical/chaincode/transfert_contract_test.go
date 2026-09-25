package chaincode_test

import (
	"testing"

	"github.com/wale-sante/dossier-medical-cc/chaincode"
	"github.com/wale-sante/dossier-medical-cc/chaincode/mocks"
)

func TestInitierEtConfirmerTransfertConforme(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.TransfertContract{}

	err := contract.InitierTransfert(ctx, "TRF-001", "PAT20250001", "WALE", "AUTRE-CENTRE", "hash-resume", "2025-01-10T09:00:00Z")
	if err != nil {
		t.Fatalf("InitierTransfert a échoué: %v", err)
	}

	if err := contract.ConfirmerReception(ctx, "TRF-001", "hash-resume", "2025-01-10T11:00:00Z"); err != nil {
		t.Fatalf("ConfirmerReception a échoué: %v", err)
	}

	transfert, err := contract.ConsulterTransfert(ctx, "TRF-001")
	if err != nil {
		t.Fatalf("ConsulterTransfert a échoué: %v", err)
	}
	if transfert.Statut != chaincode.StatutTransfertConfirme {
		t.Errorf("statut attendu %s, obtenu %s", chaincode.StatutTransfertConfirme, transfert.Statut)
	}
}

func TestConfirmerReceptionRejetteSiEmpreinteDiffere(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.TransfertContract{}
	_ = contract.InitierTransfert(ctx, "TRF-001", "PAT20250001", "WALE", "AUTRE-CENTRE", "hash-resume-original", "2025-01-10T09:00:00Z")

	if err := contract.ConfirmerReception(ctx, "TRF-001", "hash-resume-altere", "2025-01-10T11:00:00Z"); err != nil {
		t.Fatalf("ConfirmerReception a échoué: %v", err)
	}

	transfert, err := contract.ConsulterTransfert(ctx, "TRF-001")
	if err != nil {
		t.Fatalf("ConsulterTransfert a échoué: %v", err)
	}
	if transfert.Statut != chaincode.StatutTransfertRejete {
		t.Errorf("un écart d'empreinte aurait dû faire passer le transfert au statut %s, obtenu %s", chaincode.StatutTransfertRejete, transfert.Statut)
	}
}

func TestConfirmerReceptionRefuseSiDejaClos(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.TransfertContract{}
	_ = contract.InitierTransfert(ctx, "TRF-001", "PAT20250001", "WALE", "AUTRE-CENTRE", "hash-resume", "2025-01-10T09:00:00Z")
	_ = contract.ConfirmerReception(ctx, "TRF-001", "hash-resume", "2025-01-10T11:00:00Z")

	if err := contract.ConfirmerReception(ctx, "TRF-001", "hash-resume", "2025-01-10T12:00:00Z"); err == nil {
		t.Errorf("une seconde confirmation sur un transfert déjà clos aurait dû être refusée")
	}
}

func TestTransfertsParPatient(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.TransfertContract{}
	_ = contract.InitierTransfert(ctx, "TRF-001", "PAT20250001", "WALE", "AUTRE-CENTRE", "hash-1", "2025-01-10T09:00:00Z")
	_ = contract.InitierTransfert(ctx, "TRF-002", "PAT20250001", "WALE", "TROISIEME-CENTRE", "hash-2", "2025-02-05T09:00:00Z")
	_ = contract.InitierTransfert(ctx, "TRF-003", "PAT20250002", "WALE", "AUTRE-CENTRE", "hash-3", "2025-02-06T09:00:00Z")

	transferts, err := contract.TransfertsParPatient(ctx, "PAT20250001")
	if err != nil {
		t.Fatalf("TransfertsParPatient a échoué: %v", err)
	}
	if len(transferts) != 2 {
		t.Fatalf("2 transferts attendus pour PAT20250001, obtenu %d", len(transferts))
	}
}
