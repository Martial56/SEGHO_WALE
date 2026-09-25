package chaincode

import (
	"encoding/json"
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

const docTypeEvenementIntegrite = "evenementIntegrite"
const indexTypeEntiteIDEntite = "typeEntite~idEntite~idEvenement"

// IntegriteContract ancre l'empreinte des enregistrements médicaux et
// administratifs gérés hors chaîne, afin d'en garantir l'intégrité et la
// traçabilité entre les organisations du réseau.
type IntegriteContract struct {
	contractapi.Contract
}

// EnregistrerEvenement ancre une nouvelle empreinte. Le registre est
// append-only : aucune fonction de mise à jour ou de suppression n'est
// exposée, un idEvenement déjà utilisé est refusé.
func (c *IntegriteContract) EnregistrerEvenement(
	ctx contractapi.TransactionContextInterface,
	idEvenement string,
	typeEntite string,
	idEntite string,
	codePatient string,
	codeCentre string,
	empreinteHash string,
	horodatage string,
	metadonneesJSON string,
) error {
	if idEvenement == "" || typeEntite == "" || idEntite == "" || empreinteHash == "" {
		return fmt.Errorf("idEvenement, typeEntite, idEntite et empreinteHash sont obligatoires")
	}

	existing, err := ctx.GetStub().GetState(idEvenement)
	if err != nil {
		return fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if existing != nil {
		return fmt.Errorf("un événement %s est déjà enregistré, le registre est immuable", idEvenement)
	}

	var metadonnees map[string]string
	if metadonneesJSON != "" {
		if err := json.Unmarshal([]byte(metadonneesJSON), &metadonnees); err != nil {
			return fmt.Errorf("metadonneesJSON invalide: %w", err)
		}
	}

	orgEmettrice, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return fmt.Errorf("échec de lecture de l'identité de l'appelant: %w", err)
	}

	evenement := EvenementIntegrite{
		DocType:        docTypeEvenementIntegrite,
		IDEvenement:    idEvenement,
		TypeEntite:     typeEntite,
		IDEntite:       idEntite,
		CodePatient:    codePatient,
		CodeCentre:     codeCentre,
		EmpreinteHash:  empreinteHash,
		AlgorithmeHash: "SHA-256",
		OrgEmettrice:   orgEmettrice,
		Horodatage:     horodatage,
		Metadonnees:    metadonnees,
		TxIDCreation:   ctx.GetStub().GetTxID(),
	}

	evenementJSON, err := json.Marshal(evenement)
	if err != nil {
		return fmt.Errorf("échec de sérialisation de l'événement: %w", err)
	}

	if err := ctx.GetStub().PutState(idEvenement, evenementJSON); err != nil {
		return fmt.Errorf("échec d'écriture de l'état: %w", err)
	}

	indexKey, err := ctx.GetStub().CreateCompositeKey(indexTypeEntiteIDEntite, []string{typeEntite, idEntite, idEvenement})
	if err != nil {
		return fmt.Errorf("échec de création de la clé d'index: %w", err)
	}
	if err := ctx.GetStub().PutState(indexKey, []byte{0x00}); err != nil {
		return fmt.Errorf("échec d'écriture de l'index: %w", err)
	}

	return ctx.GetStub().SetEvent("EvenementEnregistre", evenementJSON)
}

// ConsulterEvenement retourne un événement par son identifiant.
func (c *IntegriteContract) ConsulterEvenement(ctx contractapi.TransactionContextInterface, idEvenement string) (*EvenementIntegrite, error) {
	return lireEvenement(ctx, idEvenement)
}

func lireEvenement(ctx contractapi.TransactionContextInterface, idEvenement string) (*EvenementIntegrite, error) {
	data, err := ctx.GetStub().GetState(idEvenement)
	if err != nil {
		return nil, fmt.Errorf("échec de lecture de l'état: %w", err)
	}
	if data == nil {
		return nil, fmt.Errorf("aucun événement %s trouvé", idEvenement)
	}
	var evenement EvenementIntegrite
	if err := json.Unmarshal(data, &evenement); err != nil {
		return nil, fmt.Errorf("échec de désérialisation de l'événement: %w", err)
	}
	return &evenement, nil
}

// HistoriqueEntite retourne tous les événements ancrés pour une entité
// donnée (ex. tous les événements de la consultation CONS20250001),
// dans l'ordre où ils ont été enregistrés.
func (c *IntegriteContract) HistoriqueEntite(ctx contractapi.TransactionContextInterface, typeEntite string, idEntite string) ([]*EvenementIntegrite, error) {
	iterator, err := ctx.GetStub().GetStateByPartialCompositeKey(indexTypeEntiteIDEntite, []string{typeEntite, idEntite})
	if err != nil {
		return nil, fmt.Errorf("échec de la requête d'historique: %w", err)
	}
	defer iterator.Close()

	evenements := []*EvenementIntegrite{}
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("échec de parcours de l'historique: %w", err)
		}
		_, parts, err := ctx.GetStub().SplitCompositeKey(result.Key)
		if err != nil {
			return nil, fmt.Errorf("clé d'index invalide: %w", err)
		}
		evenement, err := lireEvenement(ctx, parts[2])
		if err != nil {
			return nil, err
		}
		evenements = append(evenements, evenement)
	}
	return evenements, nil
}

// VerifierIntegrite compare l'empreinte ancrée sur la chaîne à une empreinte
// recalculée à partir de l'état courant de la base applicative — c'est la
// preuve qu'un enregistrement n'a pas été modifié depuis son ancrage.
func (c *IntegriteContract) VerifierIntegrite(ctx contractapi.TransactionContextInterface, idEvenement string, empreinteRecalculee string) (*ResultatVerification, error) {
	evenement, err := lireEvenement(ctx, idEvenement)
	if err != nil {
		return nil, err
	}
	return &ResultatVerification{
		IDEvenement:       idEvenement,
		Conforme:          evenement.EmpreinteHash == empreinteRecalculee,
		EmpreinteAttendue: evenement.EmpreinteHash,
		EmpreinteRecue:    empreinteRecalculee,
		OrgEmettrice:      evenement.OrgEmettrice,
		Horodatage:        evenement.Horodatage,
	}, nil
}

// EvenementsParCentre liste, de façon paginée, les événements soumis par un
// centre — utile à OrgVerificationFacture/OrgRegulateur pour l'audit. Nécessite une
// base d'état CouchDB (requêtes riches).
func (c *IntegriteContract) EvenementsParCentre(ctx contractapi.TransactionContextInterface, codeCentre string, pageSize int32, bookmark string) (*EvenementsPage, error) {
	selector := fmt.Sprintf(`{"selector":{"docType":"%s","codeCentre":"%s"}}`, docTypeEvenementIntegrite, codeCentre)
	iterator, metadata, err := ctx.GetStub().GetQueryResultWithPagination(selector, pageSize, bookmark)
	if err != nil {
		return nil, fmt.Errorf("échec de la requête riche: %w", err)
	}
	defer iterator.Close()

	evenements := []*EvenementIntegrite{}
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("échec de parcours des résultats: %w", err)
		}
		var evenement EvenementIntegrite
		if err := json.Unmarshal(result.Value, &evenement); err != nil {
			return nil, fmt.Errorf("échec de désérialisation d'un résultat: %w", err)
		}
		evenements = append(evenements, &evenement)
	}

	return &EvenementsPage{
		Evenements:      evenements,
		BookmarkSuivant: metadata.GetBookmark(),
		NombreTotal:     metadata.GetFetchedRecordsCount(),
	}, nil
}
