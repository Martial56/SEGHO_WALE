# Enrichit le contenu de base (migration 0002) : chaque catégorie passe d'un
# article unique à trois articles (Vue d'ensemble / Actions courantes / Bon à
# savoir), chacun avec sa propre icône. Les anciens articles de présentation
# sont remplacés par ce contenu plus détaillé — toujours modifiable ensuite
# depuis /admin/ sans nouvelle migration.

from django.db import migrations

ICONE_APERCU = 'bi-info-circle-fill'
ICONE_ACTIONS = 'bi-list-check'
ICONE_ASTUCE = 'bi-lightbulb-fill'

CONTENU = {
    'demarrage': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "SEGHO-WALE est le système de gestion du Centre Médico-Social WALÉ. Après connexion avec "
            "votre identifiant et votre mot de passe, vous arrivez sur le tableau de bord : une grille de "
            "modules, chacun représentant un domaine de l'activité du centre (patients, pharmacie, "
            "hospitalisation, facturation…).\n\n"
            "Seuls les modules auxquels votre compte a été autorisé apparaissent sur votre tableau de "
            "bord — deux comptes (un médecin et un caissier, par exemple) peuvent donc voir des grilles "
            "très différentes. Chaque module s'ouvre dans son propre espace, avec sa barre de navigation "
            "et ses propres écrans (listes, fiches, formulaires)."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Connectez-vous avec l'identifiant et le mot de passe fournis par un administrateur.\n"
            "• Sur le tableau de bord, cliquez sur une tuile pour entrer dans le module correspondant.\n"
            "• Depuis n'importe quelle page d'un module, l'icône en grille de points (en haut à gauche de "
            "la barre du module) ramène toujours au tableau de bord.\n"
            "• Le menu de votre profil (en haut à droite) permet de basculer entre thème clair et sombre, "
            "de verrouiller la session ou de se déconnecter."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Après un délai d'inactivité configurable (réglable dans « Mon compte »), la session se "
            "verrouille automatiquement par sécurité : un simple mot de passe suffit à la déverrouiller, "
            "sans perdre la page en cours ni devoir se reconnecter entièrement.\n\n"
            "Si un module ou un lien vous semble manquant, ce n'est pas une erreur technique la plupart du "
            "temps : seul un administrateur peut accorder l'accès à un module ou à un élément de menu "
            "précis, groupe par groupe ou utilisateur par utilisateur."
        )),
    ],
    'patients': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Patients centralise l'identité et le dossier de chaque patient reçu au centre : "
            "état civil, coordonnées, couverture d'assurance et historique des rendez-vous.\n\n"
            "Chaque patient créé reçoit un code unique (PATxxxxxxxx) qui l'identifie dans toute "
            "l'application — consultations, soins, hospitalisations, facturation. Depuis sa fiche, vous "
            "accédez directement à tout son historique médical, sans ressaisir les mêmes informations "
            "dans chaque module."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Utilisez la recherche de la liste des patients pour retrouver quelqu'un par nom, prénom ou "
            "code patient.\n"
            "• Le bouton de création ouvre un formulaire d'enregistrement : état civil, contact, assurance "
            "éventuelle.\n"
            "• Depuis la fiche d'un patient, une section dédiée liste ses rendez-vous, consultations, "
            "hospitalisations et factures.\n"
            "• La prise de rendez-vous se fait soit depuis la fiche du patient, soit depuis l'écran global "
            "des rendez-vous."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le code patient (PATxxxxxxxx) est généré automatiquement à la création et ne doit jamais être "
            "modifié à la main : il sert de référence stable dans tous les autres modules.\n\n"
            "Un rendez-vous suit un cycle de statuts précis — planifié, confirmé, terminé, annulé ou "
            "absent — qui reflète son déroulement réel plutôt qu'une simple case à cocher.\n\n"
            "Un patient couvert par une assurance profite d'un partage automatique du montant de ses "
            "factures entre part patient et part assurance, calculé en facturation."
        )),
    ],
    'medecins': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Médecins recense le corps médical du centre : spécialité, département de "
            "rattachement et disponibilités.\n\n"
            "Un médecin peut être lié à un compte employé existant, ce qui rattache automatiquement son "
            "dossier RH (contrat, présence) à sa fiche médecin — deux vues d'une même personne, reliées "
            "sans double saisie."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Consultez la liste des médecins, filtrable par spécialité ou par département.\n"
            "• Créez une fiche médecin en la reliant, si besoin, à un employé déjà enregistré en "
            "ressources humaines.\n"
            "• Gérez les spécialités et les départements depuis les écrans de configuration dédiés du "
            "module.\n"
            "• Le tableau de bord des médecins donne une vue synthétique de l'activité du corps médical."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Les spécialités et les départements sont configurables séparément du reste de l'application, "
            "pour rester cohérents avec l'organisation réelle du centre plutôt qu'avec une liste figée.\n\n"
            "Un médecin marqué inactif dans son dossier employé passe automatiquement au même statut côté "
            "médecin — les deux dossiers restent synchronisés sans action manuelle supplémentaire."
        )),
    ],
    'services': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Prestations gère le catalogue des articles et services facturables du centre : "
            "actes médicaux, consommables, équipements.\n\n"
            "Chaque article porte un type (prestation, consommable, stockable) qui détermine s'il doit "
            "être suivi en stock ou simplement facturé, et un prix de vente utilisé ensuite en "
            "facturation et en pharmacie."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Parcourez le catalogue par catégorie ou par famille d'articles.\n"
            "• Créez un nouvel article en précisant son type, son prix de vente et, si besoin, son unité "
            "de mesure.\n"
            "• Associez un article à un ou plusieurs fournisseurs pour préparer les achats.\n"
            "• Marquez un article inactif plutôt que de le supprimer, pour conserver l'historique des "
            "opérations qui le référencent."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le prix de vente défini ici est celui repris automatiquement en facturation et lors d'une "
            "vente directe en pharmacie — le modifier au même endroit évite les incohérences de prix "
            "entre modules.\n\n"
            "Un article de type « stockable » alimente le module Stock ; un article purement « prestation » "
            "n'a pas de niveau de stock à suivre."
        )),
    ],
    'soins': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Soins regroupe les consultations et les actes de soins réalisés pour un patient : "
            "mise en observation, soins infirmiers, procédures.\n\n"
            "Chaque soin suit un statut (en attente, en cours, terminé) qui permet de savoir en un coup "
            "d'œil ce qui reste à administrer ou à facturer, sans avoir à ouvrir chaque dossier un par un."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Depuis la liste des soins, filtrez par statut pour repérer ce qui reste à administrer ou à "
            "facturer.\n"
            "• Ouvrez un soin pour enregistrer son évolution : observations, procédures réalisées, "
            "changement de statut.\n"
            "• Un soin peut être créé directement depuis le dossier d'une hospitalisation en cours, ou de "
            "façon indépendante.\n"
            "• Les procédures de soin disposent de leur propre liste et de leur propre fiche, distinctes "
            "du soin global."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Un soin rattaché à une hospitalisation hérite automatiquement du centre et du dossier patient "
            "de cette hospitalisation, ce qui évite toute confusion entre les sites du centre.\n\n"
            "Les compteurs « en attente » et « à administrer » visibles sur le tableau de bord reflètent "
            "directement les statuts des soins de ce module — les tenir à jour permet un suivi correct de "
            "la charge de travail."
        )),
    ],
    'hospitalisation': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Hospitalisation gère les chambres du centre, les admissions et les notes de suivi "
            "quotidiennes des patients hospitalisés.\n\n"
            "Chaque admission est rattachée à une chambre et à un patient ; l'occupation des chambres se "
            "met à jour automatiquement à l'admission comme à la sortie, sans décompte manuel."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Consultez la liste des chambres pour voir en un coup d'œil celles occupées et celles "
            "disponibles.\n"
            "• Admettez un patient en lui attribuant une chambre libre, à partir de sa fiche ou depuis la "
            "liste des hospitalisations.\n"
            "• Ajoutez des notes de suivi quotidiennes au dossier d'hospitalisation au fil du séjour.\n"
            "• En cas de décès pendant le séjour, enregistrez-le dans le registre des décès du module."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Une chambre occupée ne peut pas recevoir un second patient tant que la sortie du précédent "
            "n'a pas été enregistrée — c'est cette règle qui garantit la fiabilité du taux d'occupation "
            "affiché.\n\n"
            "Le registre des décès conserve les informations nécessaires à l'établissement des documents "
            "officiels et reste consultable indépendamment du dossier d'hospitalisation d'origine."
        )),
    ],
    'laboratoire': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Laboratoire suit les demandes d'analyses biologiques et d'imagerie prescrites pour "
            "un patient, de la demande jusqu'au résultat.\n\n"
            "Chaque demande passe par un statut (en attente, en cours, terminée) qui alimente le compteur "
            "d'analyses en attente visible sur le tableau de bord."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Créez une nouvelle demande d'analyse en la rattachant au patient et, si besoin, à une "
            "consultation.\n"
            "• Faites progresser le statut de la demande à mesure que l'analyse avance.\n"
            "• Saisissez les résultats une fois l'analyse terminée.\n"
            "• Générez le bulletin de résultats pour l'imprimer ou le remettre au patient."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le compteur « analyses en attente » du tableau de bord se vide au fur et à mesure que les "
            "demandes passent au statut terminé — c'est un bon indicateur de la charge en cours du "
            "laboratoire.\n\n"
            "Le bulletin de résultats reste régénérable à tout moment depuis la demande correspondante, "
            "sans avoir à ressaisir les résultats."
        )),
    ],
    'pharmacie': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Pharmacie gère le catalogue des médicaments, le stock par lots (avec date de "
            "péremption) et la dispensation aux patients ou en vente directe à la caisse.\n\n"
            "Le stock est suivi par pharmacie — chaque site du centre a son propre stock — et par lot, ce "
            "qui permet de retirer en priorité les lots les plus proches de la péremption."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Consultez le stock d'une pharmacie, avec alerte visuelle sur les produits en rupture ou "
            "proches de la péremption.\n"
            "• Dispensez une ordonnance ou réalisez une vente directe à la caisse de la pharmacie.\n"
            "• Enregistrez une entrée de stock (réception, dotation) ou un ajustement après inventaire.\n"
            "• Consultez le journal des mouvements pour retrouver l'historique complet d'un produit."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Un produit suivi par lots dont tous les lots sont périmés ou épuisés est bloqué à la vente et "
            "à la dispensation, même si sa fiche indique encore une quantité théorique : le blocage se "
            "base sur les lots réellement disponibles, pas sur le total affiché.\n\n"
            "Le journal des mouvements retrace chaque entrée, dispensation, ajustement ou transfert, avec "
            "la quantité avant et après chaque opération — un bon point de départ en cas d'écart constaté."
        )),
    ],
    'ordonnance': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Ordonnances enregistre les prescriptions médicales délivrées à un patient : liste "
            "des médicaments, posologie et durée du traitement.\n\n"
            "Une ordonnance créée en consultation peut être directement dispensée en pharmacie, sans "
            "ressaisie des médicaments prescrits."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Créez une ordonnance depuis une consultation, en listant les médicaments et leur "
            "posologie.\n"
            "• Consultez l'historique des ordonnances d'un patient depuis sa fiche.\n"
            "• Transmettez une ordonnance à la pharmacie pour dispensation."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "L'historique des ordonnances d'un patient reste consultable depuis sa fiche à tout moment, "
            "utile pour vérifier les traitements en cours avant d'en prescrire un nouveau ou de détecter "
            "une interaction."
        )),
    ],
    'facturation': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Facturation regroupe les factures générées pour les soins, hospitalisations et "
            "médicaments d'un patient.\n\n"
            "Une facture peut être réglée en espèces, en mobile money ou prise en charge (totalement ou "
            "partiellement) par une assurance : le montant se répartit alors entre part patient et part "
            "assurance."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Créez une facture depuis un soin, une hospitalisation ou directement depuis la liste de "
            "facturation.\n"
            "• Enregistrez un paiement en précisant le mode (espèces, mobile money, assurance).\n"
            "• Suivez les factures impayées grâce au compteur dédié du tableau de bord.\n"
            "• Consultez le détail d'une facture pour voir la répartition entre part patient et part "
            "assurance."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le tableau de bord signale en permanence le nombre de factures impayées : un indicateur "
            "simple pour garder un œil sur les paiements en attente sans parcourir toute la liste.\n\n"
            "Une facture prise en charge par une assurance ne devient pas automatiquement soldée : le "
            "paiement de la part assurance doit être enregistré comme celui de la part patient."
        )),
    ],
    'caisse': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Caisse encadre les opérations d'encaissement du centre : ouverture et fermeture de "
            "session de caisse, transactions en espèces ou en mobile money.\n\n"
            "Chaque session de caisse enregistre le fonds de départ et les mouvements de la journée, ce "
            "qui permet un rapprochement en fin de journée."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Ouvrez une session de caisse en début de journée en indiquant le fonds de départ.\n"
            "• Enregistrez les encaissements au fil de la journée (factures, ventes directes en "
            "pharmacie).\n"
            "• Clôturez la session en fin de journée pour figer le total des mouvements.\n"
            "• Consultez l'historique des sessions passées pour un rapprochement ultérieur."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Les ventes directes en pharmacie et les paiements de factures passent automatiquement par la "
            "caisse active de l'utilisateur connecté — il faut donc qu'une session de caisse soit ouverte "
            "pour encaisser un paiement."
        )),
    ],
    'gynecologie': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Gynécologie gère les rendez-vous et consultations spécialisées, avec un suivi "
            "particulier des consultations prénatales (CPN).\n\n"
            "Le registre des naissances enregistre chaque accouchement survenu au centre, indépendamment "
            "du reste du dossier d'hospitalisation."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Planifiez un rendez-vous gynécologique en précisant son type de visite (CPN, consultation "
            "curative, planification familiale…).\n"
            "• Démarrez une consultation depuis un rendez-vous confirmé.\n"
            "• Enregistrez une naissance dans le registre dédié.\n"
            "• Configurez les types de visite depuis les écrans de configuration du module."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Les types de visite (CPN, curative, planification familiale…) sont configurables pour "
            "s'adapter aux besoins réels du service, plutôt qu'imposés par une liste fixe.\n\n"
            "Le registre des naissances existe indépendamment du dossier d'hospitalisation : une naissance "
            "peut y être enregistrée même sans hospitalisation formelle associée."
        )),
    ],
    'planning': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Planning organise les plannings hebdomadaires du personnel et des médecins de "
            "garde.\n\n"
            "Un planning publié génère une notification pour les personnes concernées, visible tant "
            "qu'elles ne l'ont pas consulté."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Construisez un planning hebdomadaire en assignant le personnel aux créneaux et services "
            "concernés.\n"
            "• Publiez le planning pour le rendre visible et déclencher les notifications.\n"
            "• Consultez les statistiques du module pour visualiser la couverture par service.\n"
            "• Retrouvez les plannings passés depuis l'historique du module."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Une notification de nouveau planning reste active tant que l'utilisateur concerné ne l'a pas "
            "consulté — un planning modifié après publication est donc à re-signaler explicitement aux "
            "personnes concernées."
        )),
    ],
    'achats': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Achats gère les fournisseurs du centre et le suivi des commandes passées auprès "
            "d'eux, du brouillon jusqu'à la réception.\n\n"
            "Chaque commande suit un statut (brouillon, envoyé, reçu) qui reflète son avancement réel "
            "auprès du fournisseur."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Enregistrez un fournisseur avec ses coordonnées et les articles qu'il propose.\n"
            "• Créez une commande en brouillon, puis passez-la au statut envoyé une fois transmise au "
            "fournisseur.\n"
            "• Réceptionnez la commande en indiquant les quantités réellement livrées.\n"
            "• Suivez le tableau de bord des achats pour visualiser les commandes en cours."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "À la réception d'une commande, les quantités livrées viennent alimenter automatiquement le "
            "stock du module Stock — une réception mal saisie se répercute directement sur les niveaux de "
            "stock affichés ailleurs."
        )),
    ],
    'stock': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Stock suit les niveaux de stock des produits du centre, les dotations vers les "
            "services et les inventaires physiques.\n\n"
            "Le retrait du stock se fait en priorité sur les lots les plus proches de la péremption "
            "(méthode FEFO), pour limiter les pertes liées aux produits périmés."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Consultez les niveaux de stock par produit, avec alerte sur les seuils bas.\n"
            "• Créez une dotation pour transférer du stock vers un service.\n"
            "• Lancez un inventaire physique pour comparer le stock théorique au stock réellement compté.\n"
            "• Validez les écarts constatés lors d'un inventaire pour ajuster le stock."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "La méthode FEFO (premier périmé, premier sorti) prime sur l'ordre d'arrivée : un lot plus "
            "récent mais périmant plus tôt sera proposé avant un lot plus ancien à péremption plus "
            "lointaine.\n\n"
            "Un inventaire non validé ne modifie pas le stock théorique — c'est la validation qui applique "
            "réellement les écarts constatés."
        )),
    ],
    'employer': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Ressources humaines centralise les dossiers du personnel : informations "
            "personnelles, contrat de travail, documents administratifs.\n\n"
            "Une alerte apparaît automatiquement à l'approche de la fin d'un contrat ou de l'expiration "
            "d'un document, pour anticiper son renouvellement."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Créez le dossier d'un nouvel employé avec ses informations personnelles et son contrat.\n"
            "• Ajoutez les documents administratifs de l'employé (pièces d'identité, diplômes, etc.).\n"
            "• Consultez les alertes de fin de contrat ou de document expiré depuis les notifications.\n"
            "• Reliez un employé à une fiche médecin s'il fait partie du corps médical."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le dossier d'un employé se retrouve automatiquement relié à sa fiche médecin ou à son "
            "historique de présence lorsque ces modules s'appliquent à lui — un seul dossier, plusieurs "
            "vues selon le module consulté."
        )),
    ],
    'presence': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Présence enregistre les pointages du personnel — arrivée et départ, matin comme "
            "soir — via le kiosque de pointage.\n\n"
            "Un retard est calculé automatiquement par rapport à l'horaire attendu, en tenant compte du "
            "planning de permanence en vigueur."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Pointez son arrivée ou son départ depuis le kiosque de pointage dédié.\n"
            "• Consultez le registre de présence pour voir les pointages d'une journée ou d'une période.\n"
            "• Générez un rapport d'assiduité par employé ou par service.\n"
            "• Vérifiez les retards signalés par rapport au planning de permanence."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Le calcul du retard tient compte du planning de permanence en vigueur pour la personne "
            "concernée : un même horaire de pointage peut être « à l'heure » ou « en retard » selon le "
            "planning qui s'applique ce jour-là."
        )),
    ],
    'conges': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Congés gère les demandes de congé du personnel, de la demande initiale jusqu'à son "
            "terme : demandé, approuvé ou refusé, puis en cours et terminé.\n\n"
            "Une notification prévient les responsables lorsqu'une nouvelle demande attend une décision, "
            "et prévient l'employé une fois la décision prise."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Déposez une demande de congé en précisant les dates souhaitées.\n"
            "• Un responsable approuve ou refuse la demande depuis les notifications ou la liste des "
            "congés.\n"
            "• Consultez la planification du module pour repérer les chevauchements de congés dans un "
            "même service.\n"
            "• Suivez l'avancement d'une demande (demandé, approuvé, en cours, terminé) depuis son détail."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "La planification du module aide à visualiser les chevauchements de congés au sein d'un même "
            "service avant validation — un bon réflexe pour éviter qu'un service se retrouve sous-effectif "
            "sur une même période."
        )),
    ],
    'rapports': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Rapports génère les rapports d'activité du centre : rapports mensuels de "
            "maternité, de soins, de gynécologie ou de médecine générale, ainsi que des rapports "
            "personnalisés.\n\n"
            "Chaque rapport généré est conservé dans un historique, téléchargeable à nouveau sans avoir à "
            "le régénérer."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Choisissez un rapport spécial (maternité, soins, gynécologie, médecine générale) ou un "
            "rapport disponible dans la liste générale.\n"
            "• Sélectionnez la période souhaitée puis générez le rapport.\n"
            "• Retrouvez un rapport déjà généré depuis l'historique, pour le retélécharger.\n"
            "• Utilisez les rapports destinés aux autorités sanitaires (registre de vaccination, "
            "statistiques CDIP) lorsque requis."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Un rapport déjà généré reste disponible en téléchargement depuis l'historique : il n'est pas "
            "nécessaire de le régénérer si les données de la période n'ont pas changé."
        )),
    ],
    'compte': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Depuis « Mon compte », chaque utilisateur peut modifier sa photo de profil, son mot de passe "
            "et sa couleur d'accent préférée.\n\n"
            "Le délai avant verrouillage automatique de session s'ajuste également ici, tout comme le "
            "choix du thème d'affichage."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Changez votre photo de profil et vos informations de contact.\n"
            "• Modifiez votre mot de passe régulièrement pour la sécurité de votre compte.\n"
            "• Ajustez le délai d'inactivité avant verrouillage automatique de session.\n"
            "• Choisissez votre couleur d'accent et basculez entre thème clair et sombre."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Un verrouillage de session protège le poste sans déconnecter complètement l'utilisateur : le "
            "mot de passe suffit à reprendre le travail exactement là où il avait été laissé.\n\n"
            "Le mode d'affichage sombre et la couleur d'accent sont propres à chaque utilisateur — les "
            "modifier ne change rien à l'affichage des autres comptes."
        )),
    ],
    'admin': [
        (ICONE_APERCU, "Vue d'ensemble", (
            "Le module Administration (l'admin Django, réservé aux comptes autorisés) permet de gérer les "
            "utilisateurs, les groupes et les permissions d'accès à chaque module de l'application.\n\n"
            "C'est ici que l'on décide quels modules et quels éléments de menu sont visibles pour chaque "
            "groupe ou chaque utilisateur, individuellement si besoin."
        )),
        (ICONE_ACTIONS, "Actions courantes", (
            "• Créez un utilisateur et affectez-le à un ou plusieurs groupes selon son rôle.\n"
            "• Accordez ou retirez l'accès à un module pour un groupe entier, ou individuellement pour un "
            "utilisateur précis.\n"
            "• Masquez ou affichez un élément de menu spécifique pour un groupe donné.\n"
            "• Consultez et gérez les autres données de l'application directement depuis l'admin."
        )),
        (ICONE_ASTUCE, "Bon à savoir", (
            "Un accès individuel (accordé ou retiré pour un utilisateur précis) prend toujours le pas sur "
            "l'accès défini par son groupe — utile pour une exception ponctuelle sans devoir créer un "
            "groupe supplémentaire.\n\n"
            "Un compte superutilisateur voit tous les modules actifs par défaut, sans avoir besoin qu'on "
            "les lui accorde un par un."
        )),
    ],
}


def enrichir_contenu(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideArticle = apps.get_model('guide', 'GuideArticle')
    for code, articles in CONTENU.items():
        try:
            categorie = GuideCategorie.objects.get(code=code)
        except GuideCategorie.DoesNotExist:
            continue
        categorie.articles.all().delete()
        for ordre, (icone, titre, contenu) in enumerate(articles):
            GuideArticle.objects.create(
                categorie=categorie, titre=titre, icone=icone, contenu=contenu, ordre=ordre,
            )


def restaurer_contenu_simple(apps, schema_editor):
    """Retour arrière : supprime les articles enrichis (les anciens articles
    de la migration 0002 ne sont pas restaurés automatiquement)."""
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    for code in CONTENU:
        try:
            categorie = GuideCategorie.objects.get(code=code)
        except GuideCategorie.DoesNotExist:
            continue
        categorie.articles.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('guide', '0003_guidearticle_icone'),
    ]

    operations = [
        migrations.RunPython(enrichir_contenu, restaurer_contenu_simple),
    ]
