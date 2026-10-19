package chaincode

import (
	"fmt"
	"regexp"
)

// Contrôles de conformité appliqués par le chaincode lui-même, en complément
// de ceux de la passerelle (défense en profondeur) : un client qui
// contournerait la passerelle ne peut pas inscrire de données non conformes.
// Les métadonnées sont immuables et répliquées chez Org2 : aucune donnée
// nominative ou clinique ne doit y figurer.

// clesMetadonneesAutorisees doit rester identique à la liste de la passerelle.
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
	// Valeurs techniques courtes : pas d'espace ni d'accent, ce qui exclut
	// le texte libre (motifs, diagnostics, noms).
	motifValeurMetadonnee = regexp.MustCompile(`^[A-Za-z0-9._:\-]+$`)
	// SHA-256 ou HMAC-SHA256 en hexadécimal minuscule.
	motifHexa64 = regexp.MustCompile(`^[0-9a-f]{64}$`)
	// Code de centre : identifiant technique court (ex. CMS-WALE).
	motifCodeCentre = regexp.MustCompile(`^[A-Za-z0-9_\-]{1,32}$`)
)

// validerEmpreinte impose un SHA-256 hexadécimal minuscule.
func validerEmpreinte(nomChamp string, empreinte string) error {
	if !motifHexa64.MatchString(empreinte) {
		return fmt.Errorf("%s doit être un SHA-256 hexadécimal minuscule (64 caractères)", nomChamp)
	}
	return nil
}

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

// validerCodeCentre accepte un code vide (facultatif) ou un identifiant court.
func validerCodeCentre(codeCentre string) error {
	if codeCentre == "" {
		return nil
	}
	if !motifCodeCentre.MatchString(codeCentre) {
		return fmt.Errorf("codeCentre invalide : 1 à 32 caractères parmi lettres, chiffres, _ et -")
	}
	return nil
}

// validerMetadonnees applique la liste blanche et le format des valeurs.
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
