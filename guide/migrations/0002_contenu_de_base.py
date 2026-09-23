# Contenu de base du guide d'utilisation : une catégorie par module existant
# de l'application, avec un article de présentation générale. Ce contenu est
# un point de départ — modifiable ensuite depuis /admin/ sans nouvelle
# migration.

from django.db import migrations

CATEGORIES = [
    {
        'code': 'demarrage', 'nom': "Prise en main", 'icone': 'bi-rocket-takeoff-fill',
        'description': "Se connecter et naviguer dans l'application", 'ordre': 0,
        'articles': [{
            'titre': "Se connecter et naviguer",
            'contenu': (
                "SEGHO-WALE est le système de gestion du Centre Médico-Social WALÉ. Après connexion "
                "avec votre identifiant et votre mot de passe, vous arrivez sur le tableau de bord : une "
                "grille de modules, chacun représentant un domaine de l'activité du centre (patients, "
                "pharmacie, hospitalisation...).\n\n"
                "Seuls les modules auxquels votre compte a été autorisé apparaissent sur votre tableau de "
                "bord — si un module vous manque, contactez un administrateur.\n\n"
                "Depuis n'importe quel module, l'icône en haut à gauche (une grille de points) vous ramène "
                "toujours au tableau de bord. En cas d'inactivité prolongée, votre session se verrouille "
                "automatiquement : il suffit de ressaisir votre mot de passe pour continuer, sans perdre "
                "votre travail en cours."
            ),
        }],
    },
    {
        'code': 'patients', 'nom': "Patients", 'icone': 'bi-people-fill',
        'description': "Dossiers patients, assurances, rendez-vous", 'ordre': 1,
        'articles': [{
            'titre': "Gérer les dossiers patients",
            'contenu': (
                "Le module Patients centralise l'identité et le dossier de chaque patient reçu au centre : "
                "état civil, coordonnées, couverture d'assurance et historique des rendez-vous.\n\n"
                "Chaque patient créé reçoit un code unique (PATxxxxxxxx) qui l'identifie dans toute "
                "l'application — consultations, hospitalisations, facturation. Ce code ne doit jamais être "
                "modifié manuellement.\n\n"
                "Depuis la fiche d'un patient, vous accédez directement à son historique médical "
                "(consultations, soins, hospitalisations, factures), ce qui évite de ressaisir les mêmes "
                "informations dans chaque module."
            ),
        }],
    },
    {
        'code': 'medecins', 'nom': "Médecins", 'icone': 'bi-heart-pulse-fill',
        'description': "Corps médical, spécialités, départements", 'ordre': 2,
        'articles': [{
            'titre': "Gérer le corps médical",
            'contenu': (
                "Le module Médecins recense le corps médical du centre : spécialité, département de "
                "rattachement et disponibilités.\n\n"
                "Un médecin peut être lié à un compte employé existant, ce qui rattache automatiquement son "
                "dossier RH (contrat, présence) à sa fiche médecin.\n\n"
                "Les spécialités et les départements sont configurables séparément, dans les écrans de "
                "configuration du module, pour rester cohérents avec l'organisation réelle du centre."
            ),
        }],
    },
    {
        'code': 'services', 'nom': "Prestations / Services", 'icone': 'bi-clipboard2-pulse-fill',
        'description': "Catalogue des articles et prestations médicales", 'ordre': 3,
        'articles': [{
            'titre': "Le catalogue des prestations",
            'contenu': (
                "Le module Prestations gère le catalogue des articles et services facturables du centre : "
                "actes médicaux, consommables, équipements.\n\n"
                "Chaque article porte un type (prestation, consommable, stockable) qui détermine s'il doit "
                "être suivi en stock ou simplement facturé.\n\n"
                "C'est dans ce catalogue que sont définis les prix de vente utilisés ensuite en facturation "
                "et en pharmacie."
            ),
        }],
    },
    {
        'code': 'soins', 'nom': "Soins", 'icone': 'bi-bandaid-fill',
        'description': "Consultations et actes de soins infirmiers", 'ordre': 4,
        'articles': [{
            'titre': "Suivre les soins d'un patient",
            'contenu': (
                "Le module Soins regroupe les consultations et les actes de soins réalisés pour un patient : "
                "mise en observation, soins infirmiers, procédures.\n\n"
                "Chaque soin suit un statut (en attente, en cours, terminé) qui permet de savoir en un coup "
                "d'œil ce qui reste à administrer ou à facturer.\n\n"
                "Un soin peut être rattaché à une hospitalisation en cours, ce qui le relie automatiquement "
                "au bon centre et au bon dossier patient."
            ),
        }],
    },
    {
        'code': 'hospitalisation', 'nom': "Hospitalisation", 'icone': 'bi-hospital-fill',
        'description': "Chambres, admissions, registre des décès", 'ordre': 5,
        'articles': [{
            'titre': "Chambres et admissions",
            'contenu': (
                "Le module Hospitalisation gère les chambres du centre, les admissions et les notes de suivi "
                "quotidiennes des patients hospitalisés.\n\n"
                "Chaque admission est rattachée à une chambre et à un patient ; l'occupation des chambres se "
                "met à jour automatiquement à l'admission comme à la sortie.\n\n"
                "Le registre des décès enregistre les décès survenus pendant une hospitalisation, avec les "
                "informations nécessaires à l'établissement des documents officiels."
            ),
        }],
    },
    {
        'code': 'laboratoire', 'nom': "Laboratoire", 'icone': 'bi-droplet-half',
        'description': "Analyses biologiques et imagerie", 'ordre': 6,
        'articles': [{
            'titre': "Demandes d'analyses et résultats",
            'contenu': (
                "Le module Laboratoire suit les demandes d'analyses biologiques et d'imagerie prescrites pour "
                "un patient, de la demande jusqu'au résultat.\n\n"
                "Chaque demande passe par un statut (en attente, en cours, terminée) qui alimente le compteur "
                "d'analyses en attente visible sur le tableau de bord.\n\n"
                "Une fois les résultats saisis, un bulletin est généré et peut être imprimé ou remis au "
                "patient."
            ),
        }],
    },
    {
        'code': 'pharmacie', 'nom': "Pharmacie", 'icone': 'bi-capsule',
        'description': "Catalogue, stock par lots, dispensation", 'ordre': 7,
        'articles': [{
            'titre': "Stock, lots et dispensation",
            'contenu': (
                "Le module Pharmacie gère le catalogue des médicaments, le stock par lots (avec date de "
                "péremption) et la dispensation aux patients ou en vente directe à la caisse.\n\n"
                "Le stock est suivi par pharmacie (chaque site du centre a son propre stock) et par lot, ce "
                "qui permet de retirer en priorité les lots les plus proches de la péremption.\n\n"
                "Le journal des mouvements retrace chaque entrée, dispensation, ajustement ou transfert de "
                "stock, avec la quantité avant et après chaque opération."
            ),
        }],
    },
    {
        'code': 'ordonnance', 'nom': "Ordonnances", 'icone': 'bi-file-medical-fill',
        'description': "Prescriptions médicales", 'ordre': 8,
        'articles': [{
            'titre': "Prescrire et dispenser",
            'contenu': (
                "Le module Ordonnances enregistre les prescriptions médicales délivrées à un patient : liste "
                "des médicaments, posologie et durée du traitement.\n\n"
                "Une ordonnance créée en consultation peut être directement dispensée en pharmacie, sans "
                "ressaisie.\n\n"
                "L'historique des ordonnances d'un patient reste consultable depuis sa fiche, utile pour "
                "vérifier les traitements en cours lors d'une nouvelle consultation."
            ),
        }],
    },
    {
        'code': 'facturation', 'nom': "Facturation", 'icone': 'bi-receipt-cutoff',
        'description': "Factures, paiements, co-paiement assurance", 'ordre': 9,
        'articles': [{
            'titre': "Facturer et encaisser",
            'contenu': (
                "Le module Facturation regroupe les factures générées pour les soins, hospitalisations et "
                "médicaments d'un patient.\n\n"
                "Une facture peut être réglée en espèces, en mobile money ou prise en charge (totalement ou "
                "partiellement) par une assurance : le montant se répartit alors entre part patient et part "
                "assurance.\n\n"
                "Le tableau de bord signale le nombre de factures impayées, pour garder un œil sur les "
                "paiements en attente."
            ),
        }],
    },
    {
        'code': 'caisse', 'nom': "Caisse", 'icone': 'bi-cash-coin',
        'description': "Sessions de caisse et transactions", 'ordre': 10,
        'articles': [{
            'titre': "Ouvrir et clôturer une session de caisse",
            'contenu': (
                "Le module Caisse encadre les opérations d'encaissement du centre : ouverture et fermeture de "
                "session de caisse, transactions en espèces ou en mobile money.\n\n"
                "Chaque session de caisse enregistre le fonds de départ et les mouvements de la journée, ce "
                "qui permet un rapprochement en fin de journée.\n\n"
                "Les ventes directes en pharmacie et les paiements de factures passent par la caisse active "
                "de l'utilisateur connecté."
            ),
        }],
    },
    {
        'code': 'gynecologie', 'nom': "Gynécologie", 'icone': 'bi-gender-female',
        'description': "Consultations, CPN, registre des naissances", 'ordre': 11,
        'articles': [{
            'titre': "Consultations et naissances",
            'contenu': (
                "Le module Gynécologie gère les rendez-vous et consultations spécialisées, avec un suivi "
                "particulier des consultations prénatales (CPN).\n\n"
                "Le registre des naissances enregistre chaque accouchement survenu au centre, indépendamment "
                "du reste du dossier d'hospitalisation.\n\n"
                "Les types de visite (CPN, consultation curative, planification familiale…) sont "
                "configurables pour s'adapter aux besoins du service."
            ),
        }],
    },
    {
        'code': 'planning', 'nom': "Planning", 'icone': 'bi-calendar3',
        'description': "Plannings hebdomadaires du personnel", 'ordre': 12,
        'articles': [{
            'titre': "Planifier le personnel",
            'contenu': (
                "Le module Planning organise les plannings hebdomadaires du personnel et des médecins de "
                "garde.\n\n"
                "Un planning publié génère une notification pour les personnes concernées, visible tant "
                "qu'elles ne l'ont pas consulté.\n\n"
                "Les statistiques du module permettent de visualiser rapidement la couverture par service et "
                "par créneau horaire."
            ),
        }],
    },
    {
        'code': 'achats', 'nom': "Achats", 'icone': 'bi-cart-fill',
        'description': "Fournisseurs et commandes", 'ordre': 13,
        'articles': [{
            'titre': "Commander auprès des fournisseurs",
            'contenu': (
                "Le module Achats gère les fournisseurs du centre et le suivi des commandes passées auprès "
                "d'eux, du brouillon jusqu'à la réception.\n\n"
                "Chaque commande suit un statut (brouillon, envoyé, reçu) qui reflète son avancement réel "
                "auprès du fournisseur.\n\n"
                "À la réception d'une commande, les quantités livrées viennent alimenter automatiquement le "
                "stock du module Stock."
            ),
        }],
    },
    {
        'code': 'stock', 'nom': "Stock", 'icone': 'bi-boxes',
        'description': "Gestion des stocks, dotations, inventaires", 'ordre': 14,
        'articles': [{
            'titre': "Dotations et inventaires",
            'contenu': (
                "Le module Stock suit les niveaux de stock des produits du centre, les dotations vers les "
                "services et les inventaires physiques.\n\n"
                "Le retrait du stock se fait en priorité sur les lots les plus proches de la péremption "
                "(méthode FEFO), pour limiter les pertes.\n\n"
                "Un inventaire permet de comparer le stock théorique au stock réellement compté et d'ajuster "
                "les écarts constatés."
            ),
        }],
    },
    {
        'code': 'employer', 'nom': "Ressources humaines", 'icone': 'bi-person-badge-fill',
        'description': "Dossiers employés, contrats, documents", 'ordre': 15,
        'articles': [{
            'titre': "Gérer les dossiers du personnel",
            'contenu': (
                "Le module Ressources humaines centralise les dossiers du personnel : informations "
                "personnelles, contrat de travail, documents administratifs.\n\n"
                "Une alerte apparaît automatiquement à l'approche de la fin d'un contrat ou de l'expiration "
                "d'un document, pour anticiper son renouvellement.\n\n"
                "Le dossier d'un employé se retrouve relié à sa fiche médecin ou à son historique de présence "
                "lorsque ces modules s'appliquent à lui."
            ),
        }],
    },
    {
        'code': 'presence', 'nom': "Présence", 'icone': 'bi-fingerprint',
        'description': "Pointage et assiduité du personnel", 'ordre': 16,
        'articles': [{
            'titre': "Le pointage au kiosque",
            'contenu': (
                "Le module Présence enregistre les pointages du personnel — arrivée et départ, matin comme "
                "soir — via le kiosque de pointage.\n\n"
                "Un retard est calculé automatiquement par rapport à l'horaire attendu, en tenant compte du "
                "planning de permanence en vigueur.\n\n"
                "Le registre et les rapports du module permettent de suivre l'assiduité par employé, par "
                "service ou sur une période donnée."
            ),
        }],
    },
    {
        'code': 'conges', 'nom': "Congés", 'icone': 'bi-airplane-fill',
        'description': "Demandes de congé et planification", 'ordre': 17,
        'articles': [{
            'titre': "Demander et valider un congé",
            'contenu': (
                "Le module Congés gère les demandes de congé du personnel, de la demande initiale jusqu'à son "
                "terme : demandé, approuvé ou refusé, puis en cours et terminé.\n\n"
                "Une notification prévient les responsables lorsqu'une nouvelle demande attend une décision, "
                "et prévient l'employé une fois la décision prise.\n\n"
                "La planification du module aide à visualiser les chevauchements de congés au sein d'un même "
                "service, avant validation."
            ),
        }],
    },
    {
        'code': 'rapports', 'nom': "Rapports", 'icone': 'bi-file-earmark-bar-graph-fill',
        'description': "Rapports médicaux et statistiques", 'ordre': 18,
        'articles': [{
            'titre': "Générer un rapport",
            'contenu': (
                "Le module Rapports génère les rapports d'activité du centre : rapports mensuels de "
                "maternité, de soins, de gynécologie ou de médecine générale, ainsi que des rapports "
                "personnalisés.\n\n"
                "Chaque rapport généré est conservé dans un historique, téléchargeable à nouveau sans avoir à "
                "le régénérer.\n\n"
                "C'est également ici que sont produits les documents destinés aux autorités sanitaires "
                "(registre de vaccination, statistiques CDIP)."
            ),
        }],
    },
    {
        'code': 'compte', 'nom': "Mon compte", 'icone': 'bi-person-gear',
        'description': "Profil, mot de passe, préférences d'affichage", 'ordre': 19,
        'articles': [{
            'titre': "Personnaliser son compte",
            'contenu': (
                "Depuis « Mon compte », chaque utilisateur peut modifier sa photo de profil, son mot de passe "
                "et sa couleur d'accent préférée.\n\n"
                "Le délai avant verrouillage automatique de session (en cas d'inactivité) s'ajuste également "
                "ici — un verrouillage protège le poste sans déconnecter complètement l'utilisateur.\n\n"
                "Le mode d'affichage sombre est disponible sur l'ensemble de l'application et se choisit "
                "indépendamment pour chaque utilisateur."
            ),
        }],
    },
    {
        'code': 'admin', 'nom': "Administration", 'icone': 'bi-gear-fill',
        'description': "Permissions, modules, paramètres système", 'ordre': 20,
        'articles': [{
            'titre': "Gérer les permissions et les modules",
            'contenu': (
                "Le module Administration (l'admin Django, réservé aux comptes autorisés) permet de gérer les "
                "utilisateurs, les groupes et les permissions d'accès à chaque module de l'application.\n\n"
                "C'est ici que l'on décide quels modules et quels éléments de menu sont visibles pour chaque "
                "groupe ou chaque utilisateur, individuellement si besoin.\n\n"
                "C'est également depuis l'administration que sont configurés les paramètres techniques du "
                "système et que sont consultées les sauvegardes."
            ),
        }],
    },
]


def creer_contenu(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideArticle = apps.get_model('guide', 'GuideArticle')
    for data in CATEGORIES:
        articles = data.pop('articles')
        categorie, _ = GuideCategorie.objects.get_or_create(
            code=data['code'], defaults=data,
        )
        for ordre, article in enumerate(articles):
            GuideArticle.objects.get_or_create(
                categorie=categorie, titre=article['titre'],
                defaults={'contenu': article['contenu'], 'ordre': ordre},
            )


def supprimer_contenu(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideCategorie.objects.filter(code__in=[c['code'] for c in CATEGORIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('guide', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(creer_contenu, supprimer_contenu),
    ]
