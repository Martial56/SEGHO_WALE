package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const empreinteTest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

func TestValiderMetadonnees(t *testing.T) {
	cas := []struct {
		nom    string
		valeur map[string]string
		valide bool
	}{
		{"aucune métadonnée", nil, true},
		{"clés autorisées", map[string]string{"version_schema": "1", "code_examen": "GE"}, true},
		{"clé non autorisée", map[string]string{"nom_patient": "KOUASSI"}, false},
		{"texte libre", map[string]string{"type_document": "consultation fièvre"}, false},
		{"valeur vide", map[string]string{"code_examen": ""}, false},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			err := validerMetadonnees(c.valeur)
			if c.valide && err != nil {
				t.Errorf("rejet inattendu : %v", err)
			}
			if !c.valide && err == nil {
				t.Errorf("acceptation inattendue")
			}
		})
	}
}

func TestEvenementRejeteAvantFabric(t *testing.T) {
	// Aucun client Fabric : si une requête invalide atteignait Fabric, le test planterait.
	serveur := NewServer(nil)
	debut := `{"idEvenement":"T1","typeEntite":"consultation","idEntite":"1",`
	corps := []string{
		debut + `"empreinteHash":"` + empreinteTest + `","metadonnees":{"valide":true}}`,
		debut + `"empreinteHash":"` + empreinteTest + `","metadonnees":{"nom_patient":"X"}}`,
		debut + `"empreinteHash":"abc"}`,
		debut + `"empreinteHash":"` + empreinteTest + `","codePatient":"PAT-0001"}`,
		`{"idEvenement":"T1","champInconnu":"x"}`,
	}
	for _, c := range corps {
		requete := httptest.NewRequest(http.MethodPost, "/evenements", strings.NewReader(c))
		reponse := httptest.NewRecorder()
		serveur.Routes().ServeHTTP(reponse, requete)
		if reponse.Code != http.StatusBadRequest {
			t.Errorf("attendu 400, obtenu %d pour : %s", reponse.Code, c)
		}
	}
}

func TestConsentementCodePatientEnClairRejete(t *testing.T) {
	serveur := NewServer(nil)
	requete := httptest.NewRequest(http.MethodGet, "/consentements?codePatient=PAT-0001&dateReference=2026-10-14", nil)
	reponse := httptest.NewRecorder()
	serveur.Routes().ServeHTTP(reponse, requete)
	if reponse.Code != http.StatusBadRequest {
		t.Errorf("attendu 400, obtenu %d", reponse.Code)
	}
}
