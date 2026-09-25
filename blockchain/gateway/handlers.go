package main

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strings"

	"github.com/hyperledger/fabric-gateway/pkg/client"
)

// Server expose en REST les 3 smart contracts du chaincode dossier-medical,
// pour une organisation donnée (celle du FabricClient injecté).
type Server struct {
	fabric *FabricClient
}

func NewServer(fabric *FabricClient) *Server {
	return &Server{fabric: fabric}
}

func (s *Server) Routes() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/sante", s.handleSante)
	mux.HandleFunc("/evenements", s.handleEvenements)
	mux.HandleFunc("/evenements/", s.handleEvenementParID)
	mux.HandleFunc("/entites/", s.handleHistoriqueEntite)
	mux.HandleFunc("/consentements", s.handleConsentements)
	mux.HandleFunc("/consentements/", s.handleConsentementParID)
	mux.HandleFunc("/transferts", s.handleTransferts)
	mux.HandleFunc("/transferts/", s.handleTransfertParID)
	return mux
}

func (s *Server) handleSante(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"statut": "ok"})
}

// --- Événements d'intégrité ---

type requeteEvenement struct {
	IDEvenement   string            `json:"idEvenement"`
	TypeEntite    string            `json:"typeEntite"`
	IDEntite      string            `json:"idEntite"`
	CodePatient   string            `json:"codePatient"`
	CodeCentre    string            `json:"codeCentre"`
	EmpreinteHash string            `json:"empreinteHash"`
	Horodatage    string            `json:"horodatage"`
	Metadonnees   map[string]string `json:"metadonnees"`
}

func (s *Server) handleEvenements(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeErreurMethode(w)
		return
	}

	var req requeteEvenement
	if err := readJSON(r, &req); err != nil {
		writeErreur(w, http.StatusBadRequest, err)
		return
	}

	metadonneesJSON := ""
	if len(req.Metadonnees) > 0 {
		encoded, err := json.Marshal(req.Metadonnees)
		if err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		metadonneesJSON = string(encoded)
	}

	_, err := s.fabric.Integrite.SubmitTransaction(
		"EnregistrerEvenement",
		req.IDEvenement, req.TypeEntite, req.IDEntite, req.CodePatient, req.CodeCentre,
		req.EmpreinteHash, req.Horodatage, metadonneesJSON,
	)
	if err != nil {
		writeErreur(w, http.StatusBadGateway, err)
		return
	}

	resultat, err := s.fabric.Integrite.EvaluateTransaction("ConsulterEvenement", req.IDEvenement)
	if err != nil {
		writeErreur(w, http.StatusBadGateway, err)
		return
	}
	writeJSONBytes(w, http.StatusCreated, resultat)
}

// handleEvenementParID route GET /evenements/{id} et POST /evenements/{id}/verifier.
func (s *Server) handleEvenementParID(w http.ResponseWriter, r *http.Request) {
	reste := strings.TrimPrefix(r.URL.Path, "/evenements/")
	segments := strings.Split(strings.Trim(reste, "/"), "/")
	idEvenement := segments[0]
	if idEvenement == "" {
		http.NotFound(w, r)
		return
	}

	if len(segments) == 1 && r.Method == http.MethodGet {
		resultat, err := s.fabric.Integrite.EvaluateTransaction("ConsulterEvenement", idEvenement)
		if err != nil {
			writeErreur(w, http.StatusNotFound, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)
		return
	}

	if len(segments) == 2 && segments[1] == "verifier" && r.Method == http.MethodPost {
		var req struct {
			EmpreinteRecalculee string `json:"empreinteRecalculee"`
		}
		if err := readJSON(r, &req); err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		resultat, err := s.fabric.Integrite.EvaluateTransaction("VerifierIntegrite", idEvenement, req.EmpreinteRecalculee)
		if err != nil {
			writeErreur(w, http.StatusNotFound, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)
		return
	}

	http.NotFound(w, r)
}

// handleHistoriqueEntite route GET /entites/{typeEntite}/{idEntite}/historique.
func (s *Server) handleHistoriqueEntite(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErreurMethode(w)
		return
	}

	reste := strings.TrimPrefix(r.URL.Path, "/entites/")
	segments := strings.Split(strings.Trim(reste, "/"), "/")
	if len(segments) != 3 || segments[2] != "historique" {
		http.NotFound(w, r)
		return
	}
	typeEntite, idEntite := segments[0], segments[1]

	resultat, err := s.fabric.Integrite.EvaluateTransaction("HistoriqueEntite", typeEntite, idEntite)
	if err != nil {
		writeErreur(w, http.StatusBadGateway, err)
		return
	}
	writeJSONBytes(w, http.StatusOK, resultat)
}

// --- Consentements ---

func (s *Server) handleConsentements(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		var req struct {
			IDConsentement  string   `json:"idConsentement"`
			CodePatient     string   `json:"codePatient"`
			OrgBeneficiaire string   `json:"orgBeneficiaire"`
			Portee          []string `json:"portee"`
			DateOctroi      string   `json:"dateOctroi"`
			DateExpiration  string   `json:"dateExpiration"`
		}
		if err := readJSON(r, &req); err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		porteeJSON, err := json.Marshal(req.Portee)
		if err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		_, err = s.fabric.Consentement.SubmitTransaction(
			"AccorderConsentement",
			req.IDConsentement, req.CodePatient, req.OrgBeneficiaire, string(porteeJSON), req.DateOctroi, req.DateExpiration,
		)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		resultat, err := s.fabric.Consentement.EvaluateTransaction("ConsulterConsentement", req.IDConsentement)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		writeJSONBytes(w, http.StatusCreated, resultat)

	case http.MethodGet:
		codePatient := r.URL.Query().Get("codePatient")
		dateReference := r.URL.Query().Get("dateReference")
		if codePatient == "" || dateReference == "" {
			writeErreur(w, http.StatusBadRequest, errors.New("les paramètres codePatient et dateReference sont obligatoires"))
			return
		}
		resultat, err := s.fabric.Consentement.EvaluateTransaction("ConsentementsActifsPourPatient", codePatient, dateReference)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)

	default:
		writeErreurMethode(w)
	}
}

// handleConsentementParID route POST /consentements/{id}/revoquer.
func (s *Server) handleConsentementParID(w http.ResponseWriter, r *http.Request) {
	reste := strings.TrimPrefix(r.URL.Path, "/consentements/")
	segments := strings.Split(strings.Trim(reste, "/"), "/")
	if len(segments) != 2 || segments[1] != "revoquer" || r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}
	idConsentement := segments[0]

	var req struct {
		Motif          string `json:"motif"`
		DateRevocation string `json:"dateRevocation"`
	}
	if err := readJSON(r, &req); err != nil {
		writeErreur(w, http.StatusBadRequest, err)
		return
	}

	_, err := s.fabric.Consentement.SubmitTransaction("RevoquerConsentement", idConsentement, req.Motif, req.DateRevocation)
	if err != nil {
		writeErreur(w, http.StatusBadGateway, err)
		return
	}
	resultat, err := s.fabric.Consentement.EvaluateTransaction("ConsulterConsentement", idConsentement)
	if err != nil {
		writeErreur(w, http.StatusBadGateway, err)
		return
	}
	writeJSONBytes(w, http.StatusOK, resultat)
}

// --- Transferts inter-centres ---

func (s *Server) handleTransferts(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		var req struct {
			IDTransfert       string `json:"idTransfert"`
			CodePatient       string `json:"codePatient"`
			CentreOrigine     string `json:"centreOrigine"`
			CentreDestination string `json:"centreDestination"`
			EmpreinteResume   string `json:"empreinteResume"`
			DateInitiation    string `json:"dateInitiation"`
		}
		if err := readJSON(r, &req); err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		_, err := s.fabric.Transfert.SubmitTransaction(
			"InitierTransfert",
			req.IDTransfert, req.CodePatient, req.CentreOrigine, req.CentreDestination, req.EmpreinteResume, req.DateInitiation,
		)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		resultat, err := s.fabric.Transfert.EvaluateTransaction("ConsulterTransfert", req.IDTransfert)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		writeJSONBytes(w, http.StatusCreated, resultat)

	case http.MethodGet:
		codePatient := r.URL.Query().Get("codePatient")
		if codePatient == "" {
			writeErreur(w, http.StatusBadRequest, errors.New("le paramètre codePatient est obligatoire"))
			return
		}
		resultat, err := s.fabric.Transfert.EvaluateTransaction("TransfertsParPatient", codePatient)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)

	default:
		writeErreurMethode(w)
	}
}

// handleTransfertParID route GET /transferts/{id} et POST /transferts/{id}/confirmer.
func (s *Server) handleTransfertParID(w http.ResponseWriter, r *http.Request) {
	reste := strings.TrimPrefix(r.URL.Path, "/transferts/")
	segments := strings.Split(strings.Trim(reste, "/"), "/")
	idTransfert := segments[0]
	if idTransfert == "" {
		http.NotFound(w, r)
		return
	}

	if len(segments) == 1 && r.Method == http.MethodGet {
		resultat, err := s.fabric.Transfert.EvaluateTransaction("ConsulterTransfert", idTransfert)
		if err != nil {
			writeErreur(w, http.StatusNotFound, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)
		return
	}

	if len(segments) == 2 && segments[1] == "confirmer" && r.Method == http.MethodPost {
		var req struct {
			EmpreinteRecue   string `json:"empreinteRecue"`
			DateConfirmation string `json:"dateConfirmation"`
		}
		if err := readJSON(r, &req); err != nil {
			writeErreur(w, http.StatusBadRequest, err)
			return
		}
		_, err := s.fabric.Transfert.SubmitTransaction("ConfirmerReception", idTransfert, req.EmpreinteRecue, req.DateConfirmation)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		resultat, err := s.fabric.Transfert.EvaluateTransaction("ConsulterTransfert", idTransfert)
		if err != nil {
			writeErreur(w, http.StatusBadGateway, err)
			return
		}
		writeJSONBytes(w, http.StatusOK, resultat)
		return
	}

	http.NotFound(w, r)
}

// --- Utilitaires HTTP ---

func readJSON(r *http.Request, dest interface{}) error {
	defer r.Body.Close()
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	return decoder.Decode(dest)
}

func writeJSON(w http.ResponseWriter, status int, body interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		log.Printf("échec d'écriture de la réponse JSON: %v", err)
	}
}

// writeJSONBytes écrit tel quel le JSON déjà produit par le chaincode
// (réponses des EvaluateTransaction/SubmitTransaction), sans le désérialiser
// puis le réencoder côté passerelle.
func writeJSONBytes(w http.ResponseWriter, status int, body []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if _, err := w.Write(body); err != nil {
		log.Printf("échec d'écriture de la réponse JSON: %v", err)
	}
}

func writeErreur(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"erreur": errMessageSansGRPCNoise(err)})
}

func writeErreurMethode(w http.ResponseWriter) {
	writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"erreur": "méthode non autorisée"})
}

// errMessageSansGRPCNoise renvoie le message d'erreur du chaincode/gRPC tel
// quel : les erreurs fabric-gateway embarquent déjà un message lisible côté
// serveur (endorsement échoué, transaction invalide, etc.).
func errMessageSansGRPCNoise(err error) string {
	if err == nil {
		return ""
	}
	var endorseErr *client.EndorseError
	if errors.As(err, &endorseErr) {
		return endorseErr.Error()
	}
	return err.Error()
}
