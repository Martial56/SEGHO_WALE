package chaincode_test

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"

	"github.com/wale-sante/dossier-medical-cc/chaincode"
	"github.com/wale-sante/dossier-medical-cc/chaincode/mocks"
)

// empreinte calcule un SHA-256 hexadécimal, au format attendu par le chaincode.
func empreinte(contenu string) string {
	somme := sha256.Sum256([]byte(contenu))
	return hex.EncodeToString(somme[:])
}

// patientPseudonymise simule un code patient pseudonymisé (HMAC-SHA256).
func patientPseudonymise(code string) string {
	return empreinte("pseudonyme:" + code)
}

func TestEnregistrerEvenement(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}
	hashConsultation := empreinte("consultation CONS20250001")

	err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntiteConsultation, "CONS20250001",
		patientPseudonymise("PAT20250001"), "WALE", hashConsultation, "2025-01-10T09:00:00Z",
		`{"version_schema":"1","type_document":"consultation"}`)
	if err != nil {
		t.Fatalf("EnregistrerEvenement a échoué: %v", err)
	}

	evenement, err := contract.ConsulterEvenement(ctx, "EVT-001")
	if err != nil {
		t.Fatalf("ConsulterEvenement a échoué: %v", err)
	}
	if evenement.EmpreinteHash != hashConsultation {
		t.Errorf("empreinte attendue %s, obtenue %s", hashConsultation, evenement.EmpreinteHash)
	}
	if evenement.OrgEmettrice != "CentreSanteMSP" {
		t.Errorf("org émettrice attendue CentreSanteMSP, obtenue %s", evenement.OrgEmettrice)
	}
	if evenement.HorodatageTransaction != "2026-10-14T10:00:00Z" {
		t.Errorf("horodatage de transaction attendu 2026-10-14T10:00:00Z, obtenu %q", evenement.HorodatageTransaction)
	}
	if evenement.Horodatage != "2025-01-10T09:00:00Z" {
		t.Errorf("horodatage de l'acte attendu 2025-01-10T09:00:00Z, obtenu %q", evenement.Horodatage)
	}
	if evenement.Metadonnees["type_document"] != "consultation" {
		t.Errorf("métadonnée type_document attendue, obtenue %v", evenement.Metadonnees)
	}
	if ctx.Stub.LastEvent("EvenementEnregistre") == nil {
		t.Errorf("l'événement chaincode EvenementEnregistre aurait dû être émis")
	}
}

func TestEnregistrerEvenementRefuseDoublon(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}
	patient := patientPseudonymise("PAT20250001")

	if err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", patient, "WALE", empreinte("version 1"), "2025-01-10T09:00:00Z", ""); err != nil {
		t.Fatalf("premier enregistrement inattendu en échec: %v", err)
	}

	err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", patient, "WALE", empreinte("version 2"), "2025-01-10T09:05:00Z", "")
	if err == nil {
		t.Fatalf("un second enregistrement sous le même idEvenement aurait dû être refusé (registre immuable)")
	}
}

func TestEnregistrerEvenementRejetteDonneesNonConformes(t *testing.T) {
	hashValide := empreinte("document")
	patientValide := patientPseudonymise("PAT20250001")

	cas := []struct {
		nom             string
		codePatient     string
		codeCentre      string
		empreinteHash   string
		metadonneesJSON string
	}{
		{"empreinte au mauvais format", patientValide, "WALE", "abc123hash", ""},
		{"code patient en clair", "PAT20250001", "WALE", hashValide, ""},
		{"code centre invalide", patientValide, "WALE CENTRE", hashValide, ""},
		{"clé de métadonnée interdite", patientValide, "WALE", hashValide, `{"nom_patient":"KOUASSI"}`},
		{"métadonnée en texte libre", patientValide, "WALE", hashValide, `{"type_document":"consultation fièvre"}`},
		{"métadonnée non textuelle", patientValide, "WALE", hashValide, `{"version_schema":1}`},
	}

	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			ctx := mocks.NewTransactionContext("CentreSanteMSP")
			contract := &chaincode.IntegriteContract{}

			err := contract.EnregistrerEvenement(ctx, "EVT-REJET", chaincode.TypeEntiteConsultation, "CONS1",
				c.codePatient, c.codeCentre, c.empreinteHash, "2025-01-10T09:00:00Z", c.metadonneesJSON)
			if err == nil {
				t.Fatalf("la requête aurait dû être rejetée")
			}
			if donnees, _ := ctx.Stub.GetState("EVT-REJET"); donnees != nil {
				t.Errorf("aucune donnée ne doit être écrite en cas de rejet")
			}
		})
	}
}

func TestHistoriqueEntite(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}
	hashConsultation := empreinte("consultation CONS20250001")

	enregistrer := func(id, typeEntite, idEntite, patient, contenu string) {
		t.Helper()
		if err := contract.EnregistrerEvenement(ctx, id, typeEntite, idEntite, patientPseudonymise(patient), "WALE", empreinte(contenu), "2025-01-10T09:00:00Z", ""); err != nil {
			t.Fatalf("enregistrement %s en échec: %v", id, err)
		}
	}
	enregistrer("EVT-001", chaincode.TypeEntiteConsultation, "CONS20250001", "PAT20250001", "consultation CONS20250001")
	enregistrer("EVT-002", chaincode.TypeEntiteFacture, "FAC20250001", "PAT20250001", "facture FAC20250001")
	enregistrer("EVT-003", chaincode.TypeEntiteConsultation, "CONS200250010", "PAT20250002", "autre consultation")

	historique, err := contract.HistoriqueEntite(ctx, chaincode.TypeEntiteConsultation, "CONS20250001")
	if err != nil {
		t.Fatalf("HistoriqueEntite a échoué: %v", err)
	}
	if len(historique) != 1 {
		t.Fatalf("un seul événement attendu pour CONS20250001, obtenu %d", len(historique))
	}
	if historique[0].EmpreinteHash != hashConsultation {
		t.Errorf("empreinte attendue %s, obtenue %s", hashConsultation, historique[0].EmpreinteHash)
	}
}

func TestVerifierIntegrite(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}
	hashOriginal := empreinte("dossier original")

	if err := contract.EnregistrerEvenement(ctx, "EVT-001", chaincode.TypeEntitePatient, "PAT20250001", patientPseudonymise("PAT20250001"), "WALE", hashOriginal, "2025-01-10T09:00:00Z", ""); err != nil {
		t.Fatalf("enregistrement en échec: %v", err)
	}

	conforme, err := contract.VerifierIntegrite(ctx, "EVT-001", hashOriginal)
	if err != nil {
		t.Fatalf("VerifierIntegrite a échoué: %v", err)
	}
	if !conforme.Conforme {
		t.Errorf("le hash inchangé aurait dû être conforme")
	}
	if conforme.HorodatageTransaction == "" {
		t.Errorf("l'horodatage de transaction doit figurer dans le résultat de vérification")
	}

	nonConforme, err := contract.VerifierIntegrite(ctx, "EVT-001", empreinte("dossier modifié"))
	if err != nil {
		t.Fatalf("VerifierIntegrite a échoué: %v", err)
	}
	if nonConforme.Conforme {
		t.Errorf("un hash différent aurait dû être signalé non conforme (donnée altérée)")
	}
}

func TestEvenementsParCentre(t *testing.T) {
	ctx := mocks.NewTransactionContext("CentreSanteMSP")
	contract := &chaincode.IntegriteContract{}

	enregistrer := func(id, centre string) {
		t.Helper()
		if err := contract.EnregistrerEvenement(ctx, id, chaincode.TypeEntiteConsultation, id, "", centre, empreinte(id), "2025-01-10T09:00:00Z", ""); err != nil {
			t.Fatalf("enregistrement %s en échec: %v", id, err)
		}
	}
	enregistrer("EVT-001", "WALE")
	enregistrer("EVT-002", "WALE")
	enregistrer("EVT-003", "WALE")
	enregistrer("EVT-004", "WALE2")     // ne doit pas apparaître pour WALE
	enregistrer("EVT-005", "TOUMBOKRO") // autre centre

	premierePage, err := contract.EvenementsParCentre(ctx, "WALE", 2, "")
	if err != nil {
		t.Fatalf("EvenementsParCentre a échoué: %v", err)
	}
	if len(premierePage.Evenements) != 2 || premierePage.BookmarkSuivant == "" {
		t.Fatalf("première page : 2 événements et un bookmark attendus, obtenu %d et %q",
			len(premierePage.Evenements), premierePage.BookmarkSuivant)
	}

	secondePage, err := contract.EvenementsParCentre(ctx, "WALE", 2, premierePage.BookmarkSuivant)
	if err != nil {
		t.Fatalf("EvenementsParCentre (page 2) a échoué: %v", err)
	}
	if len(secondePage.Evenements) != 1 || secondePage.BookmarkSuivant != "" {
		t.Fatalf("seconde page : 1 événement et aucun bookmark attendus, obtenu %d et %q",
			len(secondePage.Evenements), secondePage.BookmarkSuivant)
	}

	trouves := map[string]bool{}
	for _, page := range []*chaincode.EvenementsPage{premierePage, secondePage} {
		for _, evenement := range page.Evenements {
			if evenement.CodeCentre != "WALE" {
				t.Errorf("événement d'un autre centre retourné : %s (%s)", evenement.IDEvenement, evenement.CodeCentre)
			}
			trouves[evenement.IDEvenement] = true
		}
	}
	for _, id := range []string{"EVT-001", "EVT-002", "EVT-003"} {
		if !trouves[id] {
			t.Errorf("%s manquant dans les résultats", id)
		}
	}

	for _, taille := range []int32{0, 101} {
		if _, err := contract.EvenementsParCentre(ctx, "WALE", taille, ""); err == nil {
			t.Errorf("pageSize %d aurait dû être refusé", taille)
		}
	}
	if _, err := contract.EvenementsParCentre(ctx, "", 10, ""); err == nil {
		t.Errorf("un codeCentre vide aurait dû être refusé")
	}
}
