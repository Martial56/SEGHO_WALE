// Package mocks fournit des doubles de test minimalistes pour les
// interfaces Fabric utilisées par les contrats (shim.ChaincodeStubInterface,
// contractapi.TransactionContextInterface, cid.ClientIdentity). Ils
// embarquent l'interface réelle (valeur nil) pour la satisfaire par
// promotion de méthode et ne redéfinissent que ce dont les tests des
// contrats ont besoin — appeler une méthode non redéfinie paniquerait
// (interface nil), signe qu'elle doit être ajoutée ici.
package mocks

import (
	"fmt"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-chaincode-go/pkg/cid"
	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
	"github.com/hyperledger/fabric-protos-go/ledger/queryresult"
	"github.com/hyperledger/fabric-protos-go/peer"
)

// compositeKeySeparator n'a pas besoin de correspondre à l'encodage interne
// du vrai shim Fabric : seule la cohérence interne à ce double de test
// compte pour valider la logique des contrats.
const compositeKeySeparator = "\x00"

// ChaincodeStub est un double de test pour shim.ChaincodeStubInterface,
// avec un état en mémoire.
type ChaincodeStub struct {
	shim.ChaincodeStubInterface

	txID   string
	state  map[string][]byte
	events map[string][]byte
}

func NewChaincodeStub() *ChaincodeStub {
	return &ChaincodeStub{
		txID:   "tx-test-1",
		state:  make(map[string][]byte),
		events: make(map[string][]byte),
	}
}

func (s *ChaincodeStub) SetTxID(txID string) { s.txID = txID }
func (s *ChaincodeStub) GetTxID() string     { return s.txID }

func (s *ChaincodeStub) GetState(key string) ([]byte, error) {
	return s.state[key], nil
}

func (s *ChaincodeStub) PutState(key string, value []byte) error {
	s.state[key] = value
	return nil
}

func (s *ChaincodeStub) DelState(key string) error {
	delete(s.state, key)
	return nil
}

func (s *ChaincodeStub) SetEvent(name string, payload []byte) error {
	s.events[name] = payload
	return nil
}

// LastEvent retourne la charge utile du dernier événement émis sous ce nom
// (utilisable dans les assertions de test).
func (s *ChaincodeStub) LastEvent(name string) []byte { return s.events[name] }

func (s *ChaincodeStub) CreateCompositeKey(objectType string, attributes []string) (string, error) {
	return objectType + compositeKeySeparator + strings.Join(attributes, compositeKeySeparator), nil
}

func (s *ChaincodeStub) SplitCompositeKey(compositeKey string) (string, []string, error) {
	parts := strings.Split(compositeKey, compositeKeySeparator)
	if len(parts) == 0 {
		return "", nil, fmt.Errorf("clé composite invalide: %s", compositeKey)
	}
	return parts[0], parts[1:], nil
}

// GetStateByPartialCompositeKey renvoie les entrées dont la clé commence par
// le préfixe composite demandé — utilisé pour les index par entité/patient.
func (s *ChaincodeStub) GetStateByPartialCompositeKey(objectType string, attributes []string) (shim.StateQueryIteratorInterface, error) {
	prefix := objectType + compositeKeySeparator + strings.Join(attributes, compositeKeySeparator)
	return &StateQueryIterator{kvs: s.kvsWithPrefix(prefix)}, nil
}

// GetQueryResultWithPagination ignore le contenu du sélecteur CouchDB et
// renvoie l'ensemble des documents primaires connus (hors entrées d'index
// composite) : ce double de test valide le câblage du contrat, pas le moteur
// de requête riche de CouchDB, qui nécessite un test d'intégration contre un
// véritable état CouchDB.
func (s *ChaincodeStub) GetQueryResultWithPagination(query string, pageSize int32, bookmark string) (shim.StateQueryIteratorInterface, *peer.QueryResponseMetadata, error) {
	kvs := s.primaryStateKVs()
	metadata := &peer.QueryResponseMetadata{FetchedRecordsCount: int32(len(kvs))}
	return &StateQueryIterator{kvs: kvs}, metadata, nil
}

func (s *ChaincodeStub) kvsWithPrefix(prefix string) []*queryresult.KV {
	keys := make([]string, 0, len(s.state))
	for key := range s.state {
		if strings.HasPrefix(key, prefix) {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)

	kvs := make([]*queryresult.KV, 0, len(keys))
	for _, key := range keys {
		kvs = append(kvs, &queryresult.KV{Key: key, Value: s.state[key]})
	}
	return kvs
}

func (s *ChaincodeStub) primaryStateKVs() []*queryresult.KV {
	keys := make([]string, 0, len(s.state))
	for key := range s.state {
		if strings.Contains(key, compositeKeySeparator) {
			continue
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)

	kvs := make([]*queryresult.KV, 0, len(keys))
	for _, key := range keys {
		kvs = append(kvs, &queryresult.KV{Key: key, Value: s.state[key]})
	}
	return kvs
}

// StateQueryIterator est un double de test pour
// shim.StateQueryIteratorInterface.
type StateQueryIterator struct {
	shim.StateQueryIteratorInterface

	kvs   []*queryresult.KV
	index int
}

func (it *StateQueryIterator) HasNext() bool { return it.index < len(it.kvs) }

func (it *StateQueryIterator) Next() (*queryresult.KV, error) {
	if !it.HasNext() {
		return nil, fmt.Errorf("aucun résultat suivant")
	}
	kv := it.kvs[it.index]
	it.index++
	return kv, nil
}

func (it *StateQueryIterator) Close() error { return nil }

// ClientIdentity est un double de test pour cid.ClientIdentity : seule
// GetMSPID est utilisée par les contrats de ce chaincode.
type ClientIdentity struct {
	cid.ClientIdentity

	MSPID string
}

func (c *ClientIdentity) GetMSPID() (string, error) { return c.MSPID, nil }

// TransactionContext est un double de test pour
// contractapi.TransactionContextInterface.
type TransactionContext struct {
	contractapi.TransactionContextInterface

	Stub     *ChaincodeStub
	Identity *ClientIdentity
}

// NewTransactionContext crée un contexte de test simulant un appel émis par
// l'organisation orgMSPID (ex. "CentreSanteMSP").
func NewTransactionContext(orgMSPID string) *TransactionContext {
	return &TransactionContext{
		Stub:     NewChaincodeStub(),
		Identity: &ClientIdentity{MSPID: orgMSPID},
	}
}

func (ctx *TransactionContext) GetStub() shim.ChaincodeStubInterface  { return ctx.Stub }
func (ctx *TransactionContext) GetClientIdentity() cid.ClientIdentity { return ctx.Identity }
