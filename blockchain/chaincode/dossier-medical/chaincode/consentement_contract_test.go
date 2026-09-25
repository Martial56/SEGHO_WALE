package chaincode_test

import (
	"testing"

	"github.com/wale-sante/dossier-medical-cc/chaincode"
	"github.com/wale-sante/dossier-medical-cc/chaincode/mocks"
)

func TestAccorderEtConsulterConsentement(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.ConsentementContract{}

	err := contract.AccorderConsentement(ctx, "CONS-ACC-001", "PAT20250001", "VerificationFactureMSP", `["facturation"]`, "2025-01-10T09:00:00Z", "2025-12-31T23:59:59Z")
	if err != nil {
		t.Fatalf("AccorderConsentement a échoué: %v", err)
	}

	consentement, err := contract.ConsulterConsentement(ctx, "CONS-ACC-001")
	if err != nil {
		t.Fatalf("ConsulterConsentement a échoué: %v", err)
	}
	if consentement.Statut != chaincode.StatutConsentementActif {
		t.Errorf("statut attendu %s, obtenu %s", chaincode.StatutConsentementActif, consentement.Statut)
	}
}

func TestRevoquerConsentement(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.ConsentementContract{}
	_ = contract.AccorderConsentement(ctx, "CONS-ACC-001", "PAT20250001", "VerificationFactureMSP", `[]`, "2025-01-10T09:00:00Z", "")

	if err := contract.RevoquerConsentement(ctx, "CONS-ACC-001", "fin de prise en charge", "2025-02-01T00:00:00Z"); err != nil {
		t.Fatalf("RevoquerConsentement a échoué: %v", err)
	}

	consentement, err := contract.ConsulterConsentement(ctx, "CONS-ACC-001")
	if err != nil {
		t.Fatalf("ConsulterConsentement a échoué: %v", err)
	}
	if consentement.Statut != chaincode.StatutConsentementRevoque {
		t.Errorf("statut attendu %s, obtenu %s", chaincode.StatutConsentementRevoque, consentement.Statut)
	}

	if err := contract.RevoquerConsentement(ctx, "CONS-ACC-001", "double révocation", "2025-02-02T00:00:00Z"); err == nil {
		t.Errorf("une seconde révocation du même consentement aurait dû être refusée")
	}
}

func TestConsentementsActifsPourPatientIgnoreExpiresEtRevoques(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.ConsentementContract{}

	_ = contract.AccorderConsentement(ctx, "CONS-ACTIF", "PAT20250001", "VerificationFactureMSP", `[]`, "2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z")
	_ = contract.AccorderConsentement(ctx, "CONS-EXPIRE", "PAT20250001", "RegulateurMSP", `[]`, "2024-01-01T00:00:00Z", "2024-06-30T23:59:59Z")
	_ = contract.AccorderConsentement(ctx, "CONS-REVOQUE", "PAT20250001", "VerificationFactureMSP", `[]`, "2025-01-01T00:00:00Z", "")
	_ = contract.RevoquerConsentement(ctx, "CONS-REVOQUE", "erreur de saisie", "2025-01-02T00:00:00Z")

	actifs, err := contract.ConsentementsActifsPourPatient(ctx, "PAT20250001", "2025-06-01T00:00:00Z")
	if err != nil {
		t.Fatalf("ConsentementsActifsPourPatient a échoué: %v", err)
	}
	if len(actifs) != 1 {
		t.Fatalf("un seul consentement actif attendu, obtenu %d", len(actifs))
	}
	if actifs[0].IDConsentement != "CONS-ACTIF" {
		t.Errorf("consentement actif attendu CONS-ACTIF, obtenu %s", actifs[0].IDConsentement)
	}
}
