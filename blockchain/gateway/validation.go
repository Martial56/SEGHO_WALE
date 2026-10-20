package main

import (
	"fmt"
	"regexp"
)

// Clés de métadonnées autorisées. Aucune donnée nominative ou clinique :
// les métadonnées sont immuables et répliquées chez Org2.
var clesMetadonneesAutorisees = map[string]bool{
	"version_schema":     true,
	"type_document":      true,
	"code_examen":        true,
	"type_message_hprim": true,
}

const (
	nombreMaxMetadonnees = 10
	longueurMaxValeur    = 64
)

var (
	// Valeurs techniques courtes uniquement : pas d'espace ni d'accent,
	// ce qui exclut le texte libre (motifs, diagnostics, noms).
	motifValeurMetadonnee = regexp.MustCompile(`^[A-Za-z0-9._:\-]+$`)
	// SHA-256 ou HMAC-SHA256 en hexadécimal minuscule.
	motifHexa64 = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

// validerCodePatient impose un code patient pseudonymisé (HMAC-SHA256).
func validerCodePatient(codePatient string, obligatoire bool) error {
	if codePatient == "" {
		if obligatoire {
			return fmt.Errorf("codePatient est obligatoire")
		}
		return nil
	}
	if !motifHexa64.MatchString(codePatient) {
		return fmt.Errorf("codePatient doit être pseudonymisé (HMAC-SHA256 hexadécimal, 64 caractères)")
	}
	return nil
}

func validerRequeteEvenement(req *requeteEvenement) error {
	if req.IDEvenement == "" || req.TypeEntite == "" || req.IDEntite == "" {
		return fmt.Errorf("idEvenement, typeEntite et idEntite sont obligatoires")
	}
	if !motifHexa64.MatchString(req.EmpreinteHash) {
		return fmt.Errorf("empreinteHash doit être un SHA-256 hexadécimal minuscule (64 caractères)")
	}
	if err := validerCodePatient(req.CodePatient, false); err != nil {
		return err
	}
	return validerMetadonnees(req.Metadonnees)
}

func validerMetadonnees(metadonnees map[string]string) error {
	if len(metadonnees) > nombreMaxMetadonnees {
		return fmt.Errorf("metadonnees : %d clés maximum", nombreMaxMetadonnees)
	}
	for cle, valeur := range metadonnees {
		if !clesMetadonneesAutorisees[cle] {
			return fmt.Errorf("clé de métadonnée non autorisée : %q", cle)
		}
		if len(valeur) == 0 || len(valeur) > longueurMaxValeur {
			return fmt.Errorf("métadonnée %q : longueur entre 1 et %d caractères", cle, longueurMaxValeur)
		}
		if !motifValeurMetadonnee.MatchString(valeur) {
			return fmt.Errorf("métadonnée %q : valeur technique attendue (lettres, chiffres, . _ : -)", cle)
		}
	}
	return nil
}
