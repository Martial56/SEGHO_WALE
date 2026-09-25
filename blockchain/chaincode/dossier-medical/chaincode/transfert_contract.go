package chaincode

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

const docTypeTransfertPatient = "transfertPatient"
const indexCodePatientIDTransfert = "codePatient~idTransfert"

// TransfertContract notarise les transferts/référencements de patients entre
// centres : la comparaison de l'empreinte reçue à l'empreinte d'origine
// prouve, sans que le contenu du dossier ne transite par la chaîne, que le
// centre destinataire a bien reçu un dossier non altéré.
type TransfertContract struct {
	contractapi.Contract
}

// InitierTransfert notarise le départ d'un transfert de patient vers un
// autre centre.
func (c *TransfertContract) InitierTransfert(
	ctx contractapi.TransactionContextInterface,
	idTransfert string,
	codePatient string,
	centreOrigine string,
	centreDestination string,
	empreinteResume string,
	dateInitiation string,
) error {
	if idTransfert == "" || codePatient == "" || centreOrigine == "" || centreDestination == "" || empreinteResume == "" {
		return fmt.Errorf("idTransfert, codePatient, centreOrigine, centreDestination et empreinteResume sont obligatoires")
	}

	existing, err := ctx.GetStub().GetState(idTransfert)
	if err != nil {
		return fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if existing != nil {
		return fmt.Errorf("un transfert %s existe déjà", idTransfert)
	}

	orgInitiatrice, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("échec de lecture de l'identité de l'appelant: %w", err)
	}

	transfert := TransfertPatient{
		DocType:           docTypeTransfertPatient,
		IDTransfert:       idTransfert,
		CodePatient:       codePatient,
		CentreOrigine:     centreOrigine,
		CentreDestination: centreDestination,
		EmpreinteResume:   empreinteResume,
		Statut:            StatutTransfertInitie,
		OrgInitiatrice:    orgInitiatrice,
		DateInitiation:    dateInitiation,
		TxIDCreation:      ctx.GetStub().GetTxID(),
	}

	transfertJSON, err := json.Marshal(transfert)
	if err != nil {
		return fmt.Errorf("échec de sérialisation du transfert: %w", err)
	}

	if err := ctx.GetStub().PutState(idTransfert, transfertJSON); err != nil {
		return fmt.Errorf("échec d'écriture de l'état: %w", err)
	}

	indexKey, err := ctx.GetStub().CreateCompositeKey(indexCodePatientIDTransfert, []string{codePatient, idTransfert})
	if err != nil {
		return fmt.Errorf("échec de création de la clé d'index: %w", err)
	}
	return ctx.GetStub().PutState(indexKey, []byte{0x00})
}

// ConfirmerReception clôt le transfert : le centre destinataire fournit
// l'empreinte du dossier qu'il a reçu, comparée à celle notariée par le
// centre d'origine. Un écart fait passer le transfert au statut "rejete"
// plutôt que d'échouer silencieusement.
func (c *TransfertContract) ConfirmerReception(ctx contractapi.TransactionContextInterface, idTransfert string, empreinteRecue string, dateConfirmation string) error {
	transfert, err := lireTransfert(ctx, idTransfert)
	if err != nil {
		return err
	}
	if transfert.Statut != StatutTransfertInitie {
		return fmt.Errorf("le transfert %s n'est plus en attente de confirmation (statut actuel: %s)", idTransfert, transfert.Statut)
	}

	orgConfirmatrice, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("échec de lecture de l'identité de l'appelant: %w", err)
	}

	transfert.EmpreinteRecue = empreinteRecue
	transfert.OrgConfirmatrice = orgConfirmatrice
	transfert.DateConfirmation = dateConfirmation
	if empreinteRecue == transfert.EmpreinteResume {
		transfert.Statut = StatutTransfertConfirme
	} else {
		transfert.Statut = StatutTransfertRejete
	}

	transfertJSON, err := json.Marshal(transfert)
	if err != nil {
		return fmt.Errorf("échec de sérialisation du transfert: %w", err)
	}
	return ctx.GetStub().PutState(idTransfert, transfertJSON)
}

// ConsulterTransfert retourne un transfert par son identifiant.
func (c *TransfertContract) ConsulterTransfert(ctx contractapi.TransactionContextInterface, idTransfert string) (*TransfertPatient, error) {
	return lireTransfert(ctx, idTransfert)
}

func lireTransfert(ctx contractapi.TransactionContextInterface, idTransfert string) (*TransfertPatient, error) {
	data, err := ctx.GetStub().GetState(idTransfert)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if data == nil {
		return nil, fmt.Errorf("aucun transfert %s trouvé", idTransfert)
	}
	var transfert TransfertPatient
	if err := json.Unmarshal(data, &transfert); err != nil {
		return nil, fmt.Errorf("échec de désérialisation du transfert: %w", err)
	}
	return &transfert, nil
}

// TransfertsParPatient liste tous les transferts (en cours ou clos) d'un
// patient — la piste d'audit de son parcours inter-centres.
func (c *TransfertContract) TransfertsParPatient(ctx contractapi.TransactionContextInterface, codePatient string) ([]*TransfertPatient, error) {
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(indexCodePatientIDTransfert, []string{codePatient})
	if err != nil {
		return nil, fmt.Errorf("échec de la requête: %w", err)
	}
	defer iterator.Close()

	transferts := []*TransfertPatient{}
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("échec de parcours des résultats: %w", err)
		}
		_, parts, err := ctx.GetStub().SplitCompositeKey(result.Key)
		if err != nil {
			return nil, fmt.Errorf("clé d'index invalide: %w", err)
		}
		transfert, err := lireTransfert(ctx, parts[1])
		if err != nil {
			return nil, err
		}
		transferts = append(transferts, transfert)
	}
	return transferts, nil
}
