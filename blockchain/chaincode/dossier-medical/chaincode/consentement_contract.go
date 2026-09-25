package chaincode

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

const docTypeConsentement = "consentement"
const indexCodePatientIDConsentement = "codePatient~idConsentement"

// ConsentementContract gère les autorisations d'accès qu'un patient (ou le
// centre qui le prend en charge, en son nom) accorde aux autres
// organisations du réseau, sur un périmètre et une durée définis.
type ConsentementContract struct {
	contractapi.Contract
}

// AccorderConsentement enregistre une nouvelle autorisation d'accès.
func (c *ConsentementContract) AccorderConsentement(
	ctx contractapi.TransactionContextInterface,
	idConsentement string,
	codePatient string,
	orgBeneficiaire string,
	porteeJSON string,
	dateOctroi string,
	dateExpiration string,
) error {
	if idConsentement == "" || codePatient == "" || orgBeneficiaire == "" {
		return fmt.Errorf("idConsentement, codePatient et orgBeneficiaire sont obligatoires")
	}

	existing, err := ctx.GetStub().GetState(idConsentement)
	if err != nil {
		return fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if existing != nil {
		return fmt.Errorf("un consentement %s existe déjà", idConsentement)
	}

	var portee []string
	if porteeJSON != "" {
		if err := json.Unmarshal([]byte(porteeJSON), &portee); err != nil {
			return fmt.Errorf("porteeJSON invalide: %w", err)
		}
	}

	orgEmettrice, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("échec de lecture de l'identité de l'appelant: %w", err)
	}

	consentement := Consentement{
		DocType:         docTypeConsentement,
		IDConsentement:  idConsentement,
		CodePatient:     codePatient,
		OrgBeneficiaire: orgBeneficiaire,
		Portee:          portee,
		OrgEmettrice:    orgEmettrice,
		DateOctroi:      dateOctroi,
		DateExpiration:  dateExpiration,
		Statut:          StatutConsentementActif,
		TxIDCreation:    ctx.GetStub().GetTxID(),
	}

	consentementJSON, err := json.Marshal(consentement)
	if err != nil {
		return fmt.Errorf("échec de sérialisation du consentement: %w", err)
	}

	if err := ctx.GetStub().PutState(idConsentement, consentementJSON); err != nil {
		return fmt.Errorf("échec d'écriture de l'état: %w", err)
	}

	indexKey, err := ctx.GetStub().CreateCompositeKey(indexCodePatientIDConsentement, []string{codePatient, idConsentement})
	if err != nil {
		return fmt.Errorf("échec de création de la clé d'index: %w", err)
	}
	return ctx.GetStub().PutState(indexKey, []byte{0x00})
}

// RevoquerConsentement révoque un consentement actif. L'historique n'est pas
// supprimé : le document passe au statut "revoque" et conserve la trace de
// qui a révoqué, quand et pourquoi.
func (c *ConsentementContract) RevoquerConsentement(ctx contractapi.TransactionContextInterface, idConsentement string, motif string, dateRevocation string) error {
	consentement, err := lireConsentement(ctx, idConsentement)
	if err != nil {
		return err
	}
	if consentement.Statut == StatutConsentementRevoque {
		return fmt.Errorf("le consentement %s est déjà révoqué", idConsentement)
	}

	orgRevocation, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("échec de lecture de l'identité de l'appelant: %w", err)
	}

	consentement.Statut = StatutConsentementRevoque
	consentement.OrgRevocation = orgRevocation
	consentement.DateRevocation = dateRevocation
	consentement.MotifRevocation = motif

	consentementJSON, err := json.Marshal(consentement)
	if err != nil {
		return fmt.Errorf("échec de sérialisation du consentement: %w", err)
	}
	return ctx.GetStub().PutState(idConsentement, consentementJSON)
}

// ConsulterConsentement retourne un consentement par son identifiant.
func (c *ConsentementContract) ConsulterConsentement(ctx contractapi.TransactionContextInterface, idConsentement string) (*Consentement, error) {
	return lireConsentement(ctx, idConsentement)
}

func lireConsentement(ctx contractapi.TransactionContextInterface, idConsentement string) (*Consentement, error) {
	data, err := ctx.GetStub().GetState(idConsentement)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if data == nil {
		return nil, fmt.Errorf("aucun consentement %s trouvé", idConsentement)
	}
	var consentement Consentement
	if err := json.Unmarshal(data, &consentement); err != nil {
		return nil, fmt.Errorf("échec de désérialisation du consentement: %w", err)
	}
	return &consentement, nil
}

// ConsentementsActifsPourPatient liste les consentements actifs et non
// expirés d'un patient. Les dates étant au format RFC3339, une comparaison
// lexicographique avec dateReference suffit à détecter une expiration, sans
// avoir à parser de date côté chaincode.
func (c *ConsentementContract) ConsentementsActifsPourPatient(ctx contractapi.TransactionContextInterface, codePatient string, dateReference string) ([]*Consentement, error) {
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(indexCodePatientIDConsentement, []string{codePatient})
	if err != nil {
		return nil, fmt.Errorf("échec de la requête: %w", err)
	}
	defer iterator.Close()

	consentements := []*Consentement{}
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("échec de parcours des résultats: %w", err)
		}
		_, parts, err := ctx.GetStub().SplitCompositeKey(result.Key)
		if err != nil {
			return nil, fmt.Errorf("clé d'index invalide: %w", err)
		}
		consentement, err := lireConsentement(ctx, parts[1])
		if err != nil {
			return nil, err
		}
		if consentement.Statut != StatutConsentementActif {
			continue
		}
		if consentement.DateExpiration != "" && consentement.DateExpiration < dateReference {
			continue
		}
		consentements = append(consentements, consentement)
	}
	return consentements, nil
}
