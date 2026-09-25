// Package chaincode implémente les smart contracts du réseau blockchain de
// SEGHO-WALE. Aucune donnée médicale en clair n'est manipulée ici : seules
// des empreintes (hash) et des métadonnées transitent sur le registre, les
// dossiers complets restant dans la base applicative de chaque centre.
package chaincode

// Types d'entités pouvant être ancrées via IntegriteContract. La liste reste
// ouverte (le champ TypeEntite est une simple chaîne) pour ne pas figer le
// chaincode aux seuls types déjà câblés côté Django.
const (
	TypeEntitePatient                    = "Patient"
	TypeEntiteConsultation               = "Consultation"
	TypeEntiteOrdonnance                 = "Ordonnance"
	TypeEntiteFacture                    = "Facture"
	TypeEntitePaiement                   = "Paiement"
	TypeEntiteVaccination                = "Vaccination"
	TypeEntiteDeclarationEpidemiologique = "DeclarationEpidemiologique"
)

// EvenementIntegrite est l'empreinte immuable d'un enregistrement géré hors
// chaîne (base applicative d'un centre).
type EvenementIntegrite struct {
	DocType        string            `json:"docType"`
	IDEvenement    string            `json:"idEvenement"`
	TypeEntite     string            `json:"typeEntite"`
	IDEntite       string            `json:"idEntite"`
	CodePatient    string            `json:"codePatient,omitempty"`
	CodeCentre     string            `json:"codeCentre,omitempty"`
	EmpreinteHash  string            `json:"empreinteHash"`
	AlgorithmeHash string            `json:"algorithmeHash"`
	OrgEmettrice   string            `json:"orgEmettrice"`
	Horodatage     string            `json:"horodatage"`
	Metadonnees    map[string]string `json:"metadonnees,omitempty"`
	TxIDCreation   string            `json:"txIdCreation"`
}

// EvenementsPage est le résultat paginé d'une requête riche CouchDB.
type EvenementsPage struct {
	Evenements      []*EvenementIntegrite `json:"evenements"`
	BookmarkSuivant string                `json:"bookmarkSuivant"`
	NombreTotal     int32                 `json:"nombreTotal"`
}

// ResultatVerification compare l'empreinte ancrée sur la chaîne à une
// empreinte recalculée côté applicatif à partir de l'état courant.
type ResultatVerification struct {
	IDEvenement       string `json:"idEvenement"`
	Conforme          bool   `json:"conforme"`
	EmpreinteAttendue string `json:"empreinteAttendue"`
	EmpreinteRecue    string `json:"empreinteRecue"`
	OrgEmettrice      string `json:"orgEmettrice"`
	Horodatage        string `json:"horodatage"`
}

// Statuts possibles d'un Consentement.
const (
	StatutConsentementActif   = "actif"
	StatutConsentementRevoque = "revoque"
)

// Consentement représente une autorisation d'accès accordée à une
// organisation du réseau sur les données d'un patient, pour un périmètre et
// une durée donnés.
type Consentement struct {
	DocType         string   `json:"docType"`
	IDConsentement  string   `json:"idConsentement"`
	CodePatient     string   `json:"codePatient"`
	OrgBeneficiaire string   `json:"orgBeneficiaire"`
	Portee          []string `json:"portee,omitempty"`
	OrgEmettrice    string   `json:"orgEmettrice"`
	DateOctroi      string   `json:"dateOctroi"`
	DateExpiration  string   `json:"dateExpiration,omitempty"`
	Statut          string   `json:"statut"`
	OrgRevocation   string   `json:"orgRevocation,omitempty"`
	DateRevocation  string   `json:"dateRevocation,omitempty"`
	MotifRevocation string   `json:"motifRevocation,omitempty"`
	TxIDCreation    string   `json:"txIdCreation"`
}

// Statuts possibles d'un TransfertPatient.
const (
	StatutTransfertInitie   = "initie"
	StatutTransfertConfirme = "confirme"
	StatutTransfertRejete   = "rejete"
)

// TransfertPatient notarise le transfert d'un patient (ou de son dossier)
// entre deux centres : la comparaison de l'empreinte reçue à l'empreinte
// d'origine prouve qu'aucune altération n'a eu lieu pendant le transfert,
// sans que le contenu du dossier ne transite par la chaîne.
type TransfertPatient struct {
	DocType           string `json:"docType"`
	IDTransfert       string `json:"idTransfert"`
	CodePatient       string `json:"codePatient"`
	CentreOrigine     string `json:"centreOrigine"`
	CentreDestination string `json:"centreDestination"`
	EmpreinteResume   string `json:"empreinteResume"`
	EmpreinteRecue    string `json:"empreinteRecue,omitempty"`
	Statut            string `json:"statut"`
	OrgInitiatrice    string `json:"orgInitiatrice"`
	OrgConfirmatrice  string `json:"orgConfirmatrice,omitempty"`
	DateInitiation    string `json:"dateInitiation"`
	DateConfirmation  string `json:"dateConfirmation,omitempty"`
	TxIDCreation      string `json:"txIdCreation"`
}
