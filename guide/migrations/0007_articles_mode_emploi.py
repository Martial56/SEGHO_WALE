from django.db import migrations


# Un 4e article « Mode d'emploi » par catégorie : des instructions pas à pas
# (pas de la prose descriptive comme les 3 articles existants), avec un
# exemple de saisie concret — complète le guide avec le détail des boutons
# et des formulaires de saisie demandé par l'utilisateur.
ARTICLES = {
    'laboratoire': (
        "Mode d'emploi",
        "Depuis Laboratoire, cliquez sur « + Nouvelle demande ».\n"
        "1. Choisissez le Patient (recherche par nom, code ou téléphone).\n"
        "2. Type du test (Hématologie, Biochimie, Bactériologie...), Médecin "
        "demandeur et date/heure du prélèvement — facultatifs.\n"
        "3. Activez « Urgent » si besoin.\n"
        "4. Dans le tableau « Tests demandés », ajoutez au moins un test.\n"
        "5. Cliquez sur « Sauvegarder la demande ».\n\n"
        "Exemple : Patient « KOUASSI Adjoua », Type « Biochimie », Médecin demandeur "
        "« Dr BAMBA Awa », Tests « Glycémie à jeun » + « Numération Formule Sanguine ».\n\n"
        "Une demande suit le statut Brouillon → Demandé → Accepté → En cours → Terminé. "
        "Le bouton « Envoyer au labo » n'apparaît qu'une fois la demande facturée — "
        "impossible d'envoyer un prélèvement non payé.",
    ),
    'ordonnance': (
        "Mode d'emploi",
        "Depuis Ordonnances, cliquez sur « + Créer ».\n"
        "1. Choisissez le Patient et le Médecin prescripteur (obligatoires) — le bouton "
        "« Sauvegarder » reste grisé tant qu'ils ne sont pas renseignés.\n"
        "2. Type d'ordonnance (Interne/Externe) et Date d'expiration.\n"
        "3. Dans « Médicaments prescrits », recherchez chaque médicament dans le stock "
        "de la pharmacie du centre actif, précisez la Posologie (ex. « 1cp matin et "
        "soir »), la Durée et la Quantité.\n"
        "4. Cliquez sur « Sauvegarder ».\n\n"
        "Exemple : Patient « KOUASSI Adjoua », Médecin « Dr Coulibaly Kiyala Daouda », "
        "Médicament « Paracétamol 100mg », Posologie « 1 comprimé matin et soir », "
        "Durée « 5 jours », Quantité « 10 ».\n\n"
        "L'application refuse d'enregistrer une ligne si le médicament n'est pas en "
        "stock suffisant dans la pharmacie du centre actif, ou si le même médicament "
        "figure deux fois sur l'ordonnance.",
    ),
    'facturation': (
        "Mode d'emploi",
        "Depuis Facturation, cliquez sur « + Nouvelle facture » — ou passez directement "
        "par le bouton « Facturer » depuis une ordonnance, un rendez-vous, une demande "
        "d'examen ou un dossier d'hospitalisation, qui pré-remplit tout.\n"
        "1. Choisissez le Patient.\n"
        "2. Ajoutez chaque prestation ou produit : Désignation, Quantité, Prix unitaire "
        "(rempli automatiquement), Remise (%).\n"
        "3. Cliquez sur « Enregistrer la facture ».\n"
        "4. Depuis la fiche, cliquez sur « Valider la facture » pour la faire passer de "
        "brouillon à émise.\n"
        "5. Pour encaisser : « Enregistrer un paiement » → choisissez la Caisse, le "
        "Mode de paiement (Espèces, Chèque, Mobile Money, Virement, Assurance, Bon) et "
        "le Montant.\n\n"
        "Exemple : Patient « KOUASSI Adjoua », Désignation « Consultation Générale », "
        "Quantité 1, Prix « 3 000 FCFA », paiement « Espèces », Montant reçu "
        "« 3 000 FCFA ».\n\n"
        "Une facture suit le statut Brouillon → Émise → Payée. Le total encaissé d'une "
        "caisse (Configuration → Caisses) se recalcule à chaque consultation à partir "
        "des paiements réellement enregistrés, jamais un solde stocké qui pourrait "
        "dériver.",
    ),
    'caisse': (
        "Mode d'emploi",
        "La gestion des caisses se fait depuis Facturation → Configuration → Caisses.\n"
        "1. Cliquez sur « + Nouvelle caisse ».\n"
        "2. Renseignez le Nom et le Code de la caisse.\n"
        "3. Cochez les Modes de paiement autorisés pour cette caisse (Espèces, Chèque, "
        "Mobile Money, Virement, Assurance, Bon).\n"
        "4. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Nom « Caisse Pharmacie Walé Yamoussoukro », Code « CAISSE-PH-YAM », "
        "Modes autorisés « Espèces, Mobile Money ».\n\n"
        "Un encaissement (paiement d'une facture) ne peut se faire que depuis une "
        "caisse autorisant le mode de paiement choisi — une caisse qui n'accepte pas "
        "« Mobile Money » ne le proposera pas au moment d'encaisser.",
    ),
    'achats': (
        "Mode d'emploi",
        "Depuis Achats → Besoins, cliquez sur « + Nouveau besoin ».\n"
        "1. Titre du besoin (obligatoire), Date de livraison souhaitée.\n"
        "2. Ajoutez une ou plusieurs lignes : Produit du catalogue (ou désignation "
        "libre si hors catalogue), Quantité, Unité.\n"
        "3. Cliquez sur « Créer », puis « Soumettre » depuis la fiche pour le faire "
        "valider.\n\n"
        "Exemple : Titre « Réapprovisionnement médicaments novembre 2026 », Article "
        "« Ibuprofen », Quantité « 200 », Unité « boîte ».\n\n"
        "Un besoin validé se transforme ensuite en Proforma (devis fournisseur, à "
        "valider ou rejeter), puis en Commande d'achat une fois le proforma validé, "
        "puis en Réception à l'arrivée de la livraison — chaque étape a son propre "
        "numéro (BAC..., PRF..., CAC..., REC...) et son propre statut.",
    ),
    'demarrage': (
        "Mode d'emploi",
        "La barre du haut donne accès à :\n"
        "• La cloche de notifications — alertes stock, factures impayées, analyses en "
        "attente, congés à traiter...\n"
        "• Votre profil (en haut à droite) : si vous avez accès à plusieurs centres, un "
        "menu « Centre actif » permet de basculer de l'un à l'autre (sinon le centre est "
        "choisi automatiquement). « Mon compte » et « Déconnexion » sont dans ce même "
        "menu.\n\n"
        "Le tableau de bord affiche une tuile par module auquel vous avez accès "
        "(Patients, Pharmacie, Planning...) — cliquez sur une tuile pour l'ouvrir ; un "
        "badge rouge signale les éléments en attente (ex. nombre d'ordonnances à "
        "traiter). Pour revenir au tableau de bord depuis n'importe quel module, "
        "cliquez sur le logo en haut à gauche. Chaque module a ensuite son propre "
        "sous-menu, affiché juste sous la barre du haut.",
    ),
    'presence': (
        "Mode d'emploi",
        "Au kiosque de pointage :\n"
        "1. Tapez votre numéro matricule (ou scannez votre badge QR, ou utilisez "
        "l'empreinte digitale si le lecteur est configuré) puis validez.\n"
        "2. Votre fiche s'affiche avec l'action du moment (ex. « Arrivée matin »).\n"
        "3. Cliquez sur « Valider le pointage ». Un écran de confirmation s'affiche "
        "puis revient automatiquement à l'accueil.\n\n"
        "Exemple : Matricule « EMP20260034 » → « Arrivée matin » enregistrée.\n\n"
        "Côté responsable (Présence → Registre) :\n"
        "1. Choisissez le jour avec les flèches ou le calendrier.\n"
        "2. Les heures déjà pointées au kiosque apparaissent verrouillées (cadenas) ; "
        "complétez à la main les heures manquantes.\n"
        "3. Décochez « Présent » pour un absent — un champ « Motif d'absence » apparaît.\n"
        "4. Cliquez sur « Enregistrer le registre ».\n\n"
        "Une fois complet, le registre du jour se verrouille automatiquement — seul un "
        "administrateur peut le déverrouiller via le bouton « Déverrouiller ».",
    ),
    'rapports': (
        "Mode d'emploi",
        "Depuis Rapports, choisissez un rapport dans la liste (« Rapports spéciaux » ou "
        "« Rapports disponibles »).\n"
        "1. Renseignez la Date de début et la Date de fin (facultatives — laissez vide "
        "pour ne pas filtrer).\n"
        "2. Choisissez le format : Excel (.xlsx) ou CSV (.csv).\n"
        "3. Cliquez sur « Télécharger le rapport » — le fichier se télécharge "
        "directement, sans recharger la page.\n\n"
        "Exemple : Rapport « Rapport mensuel maternité », du 01/10/2026 au 31/10/2026, "
        "format Excel.\n\n"
        "Chaque génération est conservée dans l'historique (« Rapports récemment "
        "générés » sur la page d'accueil, ou « Tout afficher ») — vous pouvez "
        "retélécharger un rapport déjà généré sans le reconstruire.",
    ),
    'admin': (
        "Mode d'emploi",
        "L'administration se fait depuis l'interface d'administration Django (tuile "
        "« Paramètres » du tableau de bord, réservée aux comptes autorisés).\n"
        "1. Groupes (Groups) : cochez les modules autorisés pour un groupe, puis "
        "cliquez sur « 🗂️ Gérer les menus par module » pour choisir précisément quelles "
        "pages ce groupe peut voir.\n"
        "2. Utilisateurs (Users) : section « Centres d'affectation » pour donner accès "
        "à un ou plusieurs centres, et « Overrides de modules individuels » pour "
        "autoriser ou retirer un module à UN utilisateur précis, en plus de son groupe.\n"
        "3. Modules / NavItem : gère le catalogue des tuiles du tableau de bord et de "
        "leurs sous-menus.\n\n"
        "Exemple : pour qu'un utilisateur du groupe « Infirmiers » accède aussi à la "
        "Pharmacie sans changer tout le groupe, ouvrez sa fiche utilisateur → "
        "« Overrides de modules individuels » → ajoutez « Pharmacie ».",
    ),
    'patients': (
        "Mode d'emploi",
        "Depuis Patients, cliquez sur « + Créer ».\n"
        "1. Nom et Prénom(s) (mis en majuscules automatiquement).\n"
        "2. Genre, Date de naissance et Téléphone (obligatoires).\n"
        "3. Onglet Informations générales : Adresse (obligatoire), Ville, contact "
        "d'urgence.\n"
        "4. Onglet Médical : Groupe sanguin, Allergies connues, Antécédents médicaux.\n"
        "5. Onglet Assurance : si le patient a une mutuelle.\n"
        "6. Cliquez sur « Enregistrer » — le code patient (ex. PAT20260042) se génère "
        "automatiquement.\n\n"
        "Exemple : Nom « KOUASSI », Prénoms « AYA MARIE », Genre « Féminin », Date de "
        "naissance « 14/03/1994 », Téléphone « +225 07 01 02 03 04 », Adresse « Quartier "
        "Kokoko, Yamoussoukro », Groupe sanguin « O+ ».\n\n"
        "Un même patient (mêmes nom, prénoms, date de naissance et téléphone) ne peut pas "
        "être enregistré deux fois — l'application bloque les doublons exacts.",
    ),
    'services': (
        "Mode d'emploi",
        "Depuis Prestations / Services, cliquez sur « + Créer ».\n"
        "1. Nom de la prestation et Catégorie de prestation (obligatoires).\n"
        "2. Département concerné (facultatif).\n"
        "3. Onglet Information générale : Type de prestation, Unité de mesure, Prix de "
        "vente.\n"
        "4. Si le type est Consommable ou « Peut être stocké » : remplissez aussi la "
        "section Gestion du stock (prix d'achat, quantité, seuil d'alerte).\n"
        "5. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Nom « Consultation gynéco-obstétrique », Catégorie « Consultations "
        "(CS) », Département « Gynécologie », Prix de vente « 3 350 FCFA ».",
    ),
    'soins': (
        "Mode d'emploi",
        "Depuis Soins, cliquez sur « + Créer ».\n"
        "1. Choisissez le Patient (obligatoire).\n"
        "2. Dans le tableau « Lignes de soins », cliquez sur « + Ajouter un soin » : "
        "choisissez le service, le prix, l'infirmier et la date — au moins une ligne est "
        "obligatoire pour pouvoir enregistrer.\n"
        "3. Motif et Observations.\n"
        "4. Onglet Autres informations : statut et sévérité de la maladie, cases à cocher "
        "si applicable (maladie infectieuse, allergique...).\n"
        "5. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Patient « KOUASSI Aya Marie », Soin « Pansement simple », Prix "
        "« 5 000 FCFA », Infirmier « TRAORE Mamadou ».\n\n"
        "Le soin suit un statut (Brouillon → En attente de paiement → En cours → "
        "Terminé) : il passe automatiquement « En cours » dès que sa facture est payée. "
        "Le bouton « Annuler le soin » reste disponible tant qu'il n'est pas terminé.",
    ),
    'hospitalisation': (
        "Mode d'emploi",
        "Depuis Hospitalisation, cliquez sur « + Créer ».\n"
        "1. Choisissez le Patient et le Docteur (médecin traitant).\n"
        "2. Maladie et Date de la demande.\n"
        "3. Onglet Informations : nom et téléphone du parent/gardien du patient.\n"
        "4. Cliquez sur « Enregistrer » — le dossier est créé en brouillon, la chambre "
        "sera attribuée après confirmation.\n"
        "5. Depuis la fiche, cliquez sur « Confirmer la demande » pour générer la "
        "facturation ; une fois la facture payée, le patient est installé et le dossier "
        "passe « Hospitalisé ».\n"
        "6. À la sortie : « Décharger », puis « Clôturer le dossier » (bloqué tant que "
        "des prestations restent non facturées ou non payées).\n\n"
        "Exemple : Patient « KOUASSI Aya Marie », Docteur « Dr YAO Koffi », Maladie "
        "« Paludisme sévère ».",
    ),
    'gynecologie': (
        "Mode d'emploi",
        "Depuis Gynécologie → Rendez-vous, cliquez sur « + Nouveau rendez-vous ».\n"
        "1. Choisissez la patiente (ou créez-la depuis le champ si elle n'existe pas encore).\n"
        "2. Renseignez Département, Médecin, Date et heure.\n"
        "3. Type de visite CPN : choisissez CPN 1 à CPN 5 et plus (ou Autre).\n"
        "4. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Patiente « COULIBALY Aminata », Département « Gynécologie-Obstétrique », "
        "Médecin « Dr Coulibaly Aminata », Date « 15/10/2026 09h00 », Type de visite « CPN 2 ».\n\n"
        "Le jour du rendez-vous, ouvrez la fiche et cliquez sur « Démarrer » pour passer en "
        "« En consultation » (l'application retient qui a démarré l'examen). Remplissez le "
        "registre CPN affiché : constantes (poids, TA, périmètre brachial...), Statut VAT "
        "(Non vaccinée à VAT5, ou Incomplètement/Complètement vaccinée), Proposition de test VIH "
        "(Oui/Non/NA). Le champ « Durée » en haut du formulaire se remplit tout seul — c'est le "
        "temps cumulé entre la prise des constantes et la fin de la consultation, rien à saisir. "
        "Cliquez sur « Terminer » une fois l'examen achevé.",
    ),
    'planning': (
        "Mode d'emploi",
        "Depuis Planning, ouvrez un planning puis cliquez sur « Modifier ».\n"
        "1. Cliquez sur une cellule (bureau × créneau × jour) pour l'ouvrir.\n"
        "2. Recherchez et sélectionnez un médecin dans la liste — il apparaît sous forme "
        "de « puce » dans la cellule, avec un bouton pour la retirer.\n"
        "3. Clic droit sur une cellule déjà remplie : « Remplir la ligne » ou « Remplir la "
        "colonne » reproduit le même médecin sur tout le créneau ou toute la journée.\n"
        "4. Pour la permanence, cliquez sur « + Ajouter un créneau » en bas de la grille — "
        "chaque créneau a son propre médecin et ses propres horaires.\n"
        "5. Une fois complet, cliquez sur « Publier » pour rendre le planning visible à l'équipe.\n\n"
        "Exemple : cellule Bureau 1 / Matin / Lundi → médecin « Dr Coulibaly Kiyala Daouda ».\n\n"
        "Les jours fériés apparaissent grisés avec la mention « Jour férié, (nom du jour) » et "
        "sont verrouillés : impossible d'y affecter un médecin, ni en cliquant, ni via le "
        "remplissage de ligne/colonne.",
    ),
    'pharmacie': (
        "Mode d'emploi",
        "Pour démarrer une pharmacie avec le stock qu'elle a déjà en sa possession, sans "
        "créer chaque produit un par un :\n"
        "1. Depuis Pharmacie → Stock, cliquez sur « Importer stock initial ».\n"
        "2. Téléchargez le modèle Excel proposé — il liste déjà tous les produits du "
        "catalogue (code, nom, type, quantité à zéro, unité).\n"
        "3. Remplissez la colonne « quantité » pour chaque produit réellement en stock.\n"
        "4. Réimportez le fichier rempli.\n\n"
        "Exemple : ligne « MED20260003, Ibuprofen, medicament, 40, cp » pour déclarer 40 "
        "comprimés d'Ibuprofen déjà en stock.\n\n"
        "Pour dispenser une ordonnance : Pharmacie → Ordonnances → cliquez sur l'ordonnance "
        "du patient → « Dispenser ». Pour une vente directe sans ordonnance : Pharmacie → "
        "Caisse → « + Nouvelle vente », ajoutez les produits et quantités, puis « Encaisser ».",
    ),
    'stock': (
        "Mode d'emploi",
        "Depuis Stock → Produits, cliquez sur « + Créer ».\n"
        "1. Nom du produit (obligatoire).\n"
        "2. Type : Médicament, Consommable médical, ou Équipement & matériel.\n"
        "3. Catégorie : optionnelle — si elle n'existe pas encore, tapez son nom, elle "
        "sera créée automatiquement à l'enregistrement.\n"
        "4. Unité de mesure : choisissez dans la liste (cp, boîte, flacon...).\n"
        "5. Le code produit se génère automatiquement (ex. MED20260012) — rien à saisir.\n"
        "6. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Nom « Paracétamol 500mg », Type « Médicament », Catégorie « Antalgiques », "
        "Unité « cp ».\n\n"
        "Pour importer plusieurs produits d'un coup : Stock → Produits → « Export/Import » → "
        "téléchargez le modèle, remplissez une ligne par produit (code, nom, type, catégorie, "
        "unité, prix d'achat, prix de vente...), puis réimportez le fichier.",
    ),
    'conges': (
        "Mode d'emploi",
        "Depuis Congés & Absences, cliquez sur « + Nouvelle demande ».\n"
        "1. Choisissez l'employé concerné.\n"
        "2. Type de demande : un type Congé (ex. Congé annuel), Permission ou Absence, "
        "selon ce qui a été configuré.\n"
        "3. Date de début et date de fin.\n"
        "4. Motif (facultatif selon le type).\n"
        "5. Cliquez sur « Enregistrer » — la demande passe au statut « Demandé ».\n\n"
        "Exemple : Employé « TSAMOH ARMEL », Type « Congé annuel », Du 05/11/2026 au "
        "19/11/2026, Motif « Congé annuel ».\n\n"
        "Un responsable approuve ou refuse ensuite la demande depuis la cloche de "
        "notifications ou la liste des congés, avec les boutons « Approuver »/« Refuser ». "
        "Une fois approuvée, la demande suit automatiquement le statut « En cours » puis "
        "« Terminé » selon les dates. Le solde de congé de l'employé (visible dans sa fiche) "
        "se met à jour en conséquence.",
    ),
    'employer': (
        "Mode d'emploi",
        "Depuis Ressources humaines → Employés, cliquez sur « + Créer ».\n"
        "1. Renseignez l'état civil (nom, prénoms, date de naissance, nationalité...).\n"
        "2. Fonction et date d'embauche (obligatoires) ; Service et Type de contrat.\n"
        "3. Ajoutez les documents requis (pièce d'identité, diplôme, acte de naissance "
        "pour les enfants déclarés...) dans l'onglet Documents.\n"
        "4. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Nom « KOFFI », Prénoms « Marie Chantal », Fonction « Infirmier(ère) », "
        "Service « Soins », Date d'embauche « 01/09/2026 ».\n\n"
        "Si le nombre d'actes de naissance importés est inférieur au nombre d'enfants "
        "déclarés dans la fiche, une alerte apparaît pour le signaler. Les champs "
        "« Catégories de configuration » (Fonctions, Grades, Types de contrat, "
        "Nationalités, Services) se gèrent depuis l'onglet Configuration — chaque "
        "liste a son propre « + Créer », sa recherche et sa pagination.",
    ),
    'medecins': (
        "Mode d'emploi",
        "Depuis Médecins, cliquez sur « + Créer ».\n"
        "1. Matricule : tapez celui d'un employé déjà enregistré en RH — ses informations "
        "(nom, téléphone, photo...) se chargent automatiquement en lecture seule.\n"
        "2. Compte utilisateur : obligatoire, pour que le médecin puisse se connecter.\n"
        "3. Spécialité, Département (facultatif) et Service.\n"
        "4. Numéro d'ordre des médecins (si applicable).\n"
        "5. Cliquez sur « Enregistrer ».\n\n"
        "Exemple : Matricule d'un employé « Fonction : MEDECIN » déjà créé en RH, "
        "Spécialité « Gynécologie-Obstétrique », Service « Maternité ».\n\n"
        "Dans Configuration → Spécialités, le code (ex. GYNE) se génère automatiquement "
        "dès que vous tapez le nom — pas besoin de l'inventer. Une sage-femme (fonction RH "
        "« Sage-Femme ») est affichée avec le préfixe « SF » au lieu de « Dr » partout dans "
        "l'application.",
    ),
    'compte': (
        "Mode d'emploi",
        "Depuis le menu de votre compte (en haut à droite) → « Mon compte ».\n"
        "1. Onglet Profil : modifiez votre photo, téléphone, informations affichées.\n"
        "2. Onglet Sécurité : changez votre mot de passe (ancien mot de passe requis), "
        "et réglez le délai d'inactivité avant verrouillage automatique de la session.\n"
        "3. Onglet Apparence : choisissez le mode clair/sombre, la luminosité de "
        "l'interface (70 à 100 %) et la couleur d'accent de l'application.\n"
        "4. Cliquez sur « Enregistrer » dans chaque onglet concerné.\n\n"
        "Exemple : Délai d'inactivité « 15 minutes », Couleur d'accent « Vert ».\n\n"
        "Passé le délai d'inactivité choisi, l'application verrouille votre session (un "
        "écran demande votre mot de passe pour continuer) au lieu de vous déconnecter — "
        "vos saisies en cours ne sont pas perdues.",
    ),
}


def ajouter_articles(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideArticle = apps.get_model('guide', 'GuideArticle')
    for code, (titre, contenu) in ARTICLES.items():
        try:
            categorie = GuideCategorie.objects.get(code=code)
        except GuideCategorie.DoesNotExist:
            continue
        GuideArticle.objects.update_or_create(
            categorie=categorie, titre=titre,
            defaults={'contenu': contenu, 'icone': 'bi-list-ol', 'ordre': 3},
        )


def retirer_articles(apps, schema_editor):
    GuideArticle = apps.get_model('guide', 'GuideArticle')
    GuideArticle.objects.filter(titre="Mode d'emploi", categorie__code__in=ARTICLES.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('guide', '0006_regrouper_categories'),
    ]

    operations = [
        migrations.RunPython(ajouter_articles, retirer_articles),
    ]
