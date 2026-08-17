"""Injecte un jeu de données de démonstration couvrant tous les modules.

    python manage.py seed_demo              # volume standard
    python manage.py seed_demo --scale 2    # deux fois plus de dossiers
    python manage.py seed_demo --no-users   # sans créer les comptes de test

La commande AJOUTE des données, elle n'en supprime aucune : elle peut être
relancée, mais chaque exécution empile un nouveau lot. Faire une copie de
db.sqlite3 avant de l'utiliser sur une base qui compte.

Les dates sont réparties autour d'aujourd'hui (passé et futur) pour que les
filtres « aujourd'hui / cette semaine / ce mois » des listes aient de la
matière. Les champs auto_now_add sont réécrits après création (.update()),
seul moyen de les faire varier.
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# ── Vocabulaire ivoirien pour des dossiers crédibles ──────────────────────
NOMS = [
    "KOUASSI", "KOUAME", "YAO", "KONAN", "N'GUESSAN", "KOFFI", "ADJOUMANI",
    "BROU", "AKA", "ASSAMOI", "TANOH", "AMANI", "BEDIA", "GNAGNE", "TRAORE",
    "OUATTARA", "COULIBALY", "DIALLO", "BAMBA", "TOURE", "SANOGO", "CISSE",
    "DOUMBIA", "KEITA", "FOFANA", "SORO", "GBAGBO", "ZADI", "DAGO", "IRIE",
    "BOTI", "EHUI", "ANOH", "NIAMKE", "ABLE", "GOUAMENE", "SEKA", "LOBA",
]
PRENOMS_F = [
    "Amenan Grâce", "Akissi Rachelle", "Affoué Marie", "Adjoua Rebecca",
    "Ahou Christelle", "Aya Sylvie", "Amoin Prisca", "Awa Fatoumata",
    "Mariam", "Aminata", "Fatim", "Salimata", "Nadège", "Estelle",
    "Clarisse", "Béatrice", "Josiane", "Éliane", "Micheline", "Solange",
]
PRENOMS_M = [
    "Kouadio Serge", "Yao Emmanuel", "Konan Jean-Marc", "Koffi Bernard",
    "Brou Désiré", "Aka Landry", "Amani Christian", "Ibrahim", "Mamadou",
    "Souleymane", "Abdoulaye", "Seydou", "Vincent", "Arsène", "Franck",
    "Hervé", "Olivier", "Patrice", "Rodrigue", "Théodore",
]
QUARTIERS = [
    "Habitat", "Kokrenou", "Dioulakro", "N'Zuessy", "Millionnaire",
    "Morofé", "Assabou", "Bromakoté", "Sopim", "220 Logements",
    "Toumbokro centre", "Kossou", "Attiégouakro", "Didiévi",
]
PROFESSIONS = [
    "Cultivateur", "Commerçante", "Enseignant", "Élève", "Étudiante",
    "Couturière", "Chauffeur", "Maçon", "Ménagère", "Fonctionnaire",
    "Infirmier", "Coiffeuse", "Mécanicien", "Sans emploi", "Retraité",
]
GROUPES_SANGUINS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

MOTIFS_CONSULT = [
    "Fièvre depuis 3 jours", "Céphalées persistantes", "Douleurs abdominales",
    "Toux productive", "Asthénie généralisée", "Douleurs lombaires",
    "Vomissements et diarrhée", "Contrôle de tension artérielle",
    "Plaie infectée au pied", "Suivi de grossesse", "Prurit généralisé",
    "Dyspnée à l'effort", "Otalgie droite", "Conjonctivite bilatérale",
    "Suivi de diabète", "Vertiges au lever", "Douleurs articulaires",
]
DIAGNOSTICS_LIBRES = [
    "Paludisme simple", "Infection respiratoire aiguë", "Gastro-entérite",
    "Hypertension artérielle essentielle", "Anémie ferriprive",
    "Diabète de type 2", "Infection urinaire basse", "Dermatose prurigineuse",
    "Lombalgie mécanique", "Angine érythémateuse", "Parasitose intestinale",
]
POSOLOGIES = [
    "1 comprimé matin et soir", "2 comprimés par jour après repas",
    "1 cuillère à café 3 fois par jour", "1 injection IM par jour",
    "1 gélule toutes les 8 heures", "Application locale 2 fois par jour",
]
DUREES = ["3 jours", "5 jours", "7 jours", "10 jours", "1 mois"]

NOTES_RDV = [
    "", "",
    "Patient prévenu par téléphone.",
    "Prévoir un interprète (langue baoulé).",
    "Dossier papier à ressortir des archives.",
    "Régler le reste à charge avant la consultation.",
    "Patient à jeun demandé pour le bilan.",
]
MALADIES_RDV = [
    "", "",
    "Hypertension artérielle", "Diabète de type 2", "Asthme",
    "Drépanocytose", "Ulcère gastroduodénal", "Paludisme à répétition",
]
ANTECEDENTS_RDV = [
    "", "",
    "Aucun antécédent notable.",
    "Appendicectomie en 2019.",
    "Deux césariennes.",
    "Traitement antihypertenseur depuis 2021.",
    "Allergie documentée à la pénicilline.",
    "Hospitalisation pour paludisme grave l'an dernier.",
]
HISTORIQUE_RDV = [
    "", "",
    "Dernière consultation il y a 6 mois, évolution favorable.",
    "Suivi irrégulier, plusieurs rendez-vous manqués.",
    "Patient référé par le centre de santé de Kossou.",
    "Bilan biologique de contrôle réalisé le mois dernier.",
]

MEDICAMENTS = [
    ("Paracétamol 500 mg", "Paracétamol", "comprime", "500 mg", 50, 30),
    ("Amoxicilline 500 mg", "Amoxicilline", "gelule", "500 mg", 150, 95),
    ("Artéméther-Luméfantrine", "Artéméther/Luméfantrine", "comprime", "20/120 mg", 1200, 850),
    ("Métronidazole 500 mg", "Métronidazole", "comprime", "500 mg", 120, 70),
    ("Ibuprofène 400 mg", "Ibuprofène", "comprime", "400 mg", 90, 55),
    ("Ciprofloxacine 500 mg", "Ciprofloxacine", "comprime", "500 mg", 250, 160),
    ("Sirop antitussif", "Dextrométhorphane", "sirop", "15 mg/5 ml", 1500, 1000),
    ("Sérum glucosé 5%", "Glucose", "solution", "500 ml", 900, 600),
    ("Ceftriaxone 1 g", "Ceftriaxone", "injectable", "1 g", 2500, 1800),
    ("Oméprazole 20 mg", "Oméprazole", "gelule", "20 mg", 200, 130),
    ("Fer + acide folique", "Fumarate ferreux", "comprime", "200 mg", 60, 35),
    ("Amlodipine 5 mg", "Amlodipine", "comprime", "5 mg", 110, 70),
    ("Metformine 850 mg", "Metformine", "comprime", "850 mg", 130, 80),
    ("Salbutamol spray", "Salbutamol", "solution", "100 µg", 3500, 2600),
    ("Diclofénac gel", "Diclofénac", "pommade", "1%", 1800, 1200),
    ("Albendazole 400 mg", "Albendazole", "comprime", "400 mg", 300, 190),
    ("Vitamine C 500 mg", "Acide ascorbique", "comprime", "500 mg", 40, 22),
    ("Dexaméthasone injectable", "Dexaméthasone", "injectable", "4 mg", 700, 450),
    ("Sérum salé isotonique", "Chlorure de sodium", "solution", "500 ml", 850, 550),
    ("Gentamicine 80 mg", "Gentamicine", "injectable", "80 mg", 600, 380),
    ("Quinine injectable", "Quinine", "injectable", "600 mg", 1400, 950),
    ("Cotrimoxazole 480 mg", "Sulfaméthoxazole/Triméthoprime", "comprime", "480 mg", 80, 45),
    ("Bétadine dermique", "Povidone iodée", "solution", "10%", 2200, 1500),
    ("Pommade oculaire tétracycline", "Tétracycline", "pommade", "1%", 950, 600),
    ("Ocytocine injectable", "Ocytocine", "injectable", "5 UI", 800, 520),
]
CONSOMMABLES = [
    "Compresses stériles", "Sparadrap", "Gants d'examen (boîte)",
    "Seringue 5 ml", "Seringue 10 ml", "Cathéter veineux 22G",
    "Bandes de gaze", "Coton hydrophile", "Alcool 70°",
    "Lames de bistouri", "Sondes urinaires", "Perfuseur",
    "Masques chirurgicaux (boîte)", "Thermomètre digital",
    "Tubes EDTA", "Tubes secs", "Lancettes", "Bandelettes glycémie",
]
EXAMENS_LABO = [
    ("NFS", "Numération formule sanguine", "hematologie", 5000, 4),
    ("GE", "Goutte épaisse / densité parasitaire", "parasitologie", 3000, 2),
    ("TDR-PALU", "Test de diagnostic rapide paludisme", "parasitologie", 2000, 1),
    ("GLY", "Glycémie à jeun", "biochimie", 2500, 2),
    ("CREAT", "Créatininémie", "biochimie", 4000, 6),
    ("UREE", "Urémie", "biochimie", 3500, 6),
    ("TRANSA", "Transaminases ASAT/ALAT", "biochimie", 6000, 8),
    ("IONO", "Ionogramme sanguin", "biochimie", 8000, 8),
    ("CRP", "Protéine C réactive", "biochimie", 5000, 6),
    ("VS", "Vitesse de sédimentation", "hematologie", 2500, 4),
    ("GS-RH", "Groupe sanguin et rhésus", "hematologie", 3000, 2),
    ("ELECTRO", "Électrophorèse de l'hémoglobine", "hematologie", 12000, 48),
    ("TP-INR", "Taux de prothrombine / INR", "hematologie", 7000, 6),
    ("VIH", "Sérologie VIH", "serologie", 4000, 24),
    ("HEP-B", "Antigène HBs", "serologie", 6000, 24),
    ("HEP-C", "Sérologie hépatite C", "serologie", 7000, 24),
    ("TOXO", "Sérologie toxoplasmose", "serologie", 9000, 48),
    ("RUB", "Sérologie rubéole", "serologie", 9000, 48),
    ("WIDAL", "Sérodiagnostic de Widal", "serologie", 5000, 24),
    ("ASLO", "Antistreptolysine O", "serologie", 6000, 24),
    ("ECBU", "Examen cytobactériologique des urines", "bacteriologie", 8000, 48),
    ("COPRO", "Coproculture", "bacteriologie", 9000, 72),
    ("PV", "Prélèvement vaginal", "bacteriologie", 7000, 48),
    ("SPERMO", "Spermogramme", "bacteriologie", 12000, 24),
    ("BK", "Recherche de BAAR", "bacteriologie", 6000, 48),
    ("BW", "Sérologie syphilis (BW)", "serologie", 4000, 24),
    ("TEST-GROSS", "Test de grossesse urinaire", "biochimie", 2000, 1),
    ("URO", "Bandelette urinaire", "biochimie", 1500, 1),
    ("CHOL", "Cholestérol total", "biochimie", 4500, 6),
    ("TRIG", "Triglycérides", "biochimie", 4500, 6),
]
PARAMS_LABO = {
    "NFS": [("Hémoglobine", "g/dl", 11, 16), ("Leucocytes", "/mm3", 4000, 10000),
            ("Plaquettes", "/mm3", 150000, 400000), ("Hématocrite", "%", 35, 47)],
    "GLY": [("Glycémie", "g/l", 0.7, 1.1)],
    "CREAT": [("Créatinine", "mg/l", 6, 13)],
    "CRP": [("CRP", "mg/l", 0, 6)],
    "IONO": [("Sodium", "mmol/l", 135, 145), ("Potassium", "mmol/l", 3.5, 5.1),
             ("Chlore", "mmol/l", 98, 107)],
}
ACTES = [
    ("CONS-GEN", "Consultation de médecine générale", "Consultation", 3000),
    ("CONS-SPE", "Consultation spécialisée", "Consultation", 7000),
    ("CONS-URG", "Consultation d'urgence", "Consultation", 5000),
    ("CONS-CPN", "Consultation prénatale", "Consultation", 2500),
    ("PANS-SIMP", "Pansement simple", "Soins", 1500),
    ("PANS-COMP", "Pansement complexe", "Soins", 4000),
    ("INJ-IM", "Injection intramusculaire", "Soins", 1000),
    ("INJ-IV", "Injection intraveineuse", "Soins", 1500),
    ("PERF", "Pose de perfusion", "Soins", 3000),
    ("SUT", "Suture de plaie", "Soins", 8000),
    ("ABLA-FILS", "Ablation de fils", "Soins", 2000),
    ("SONDE-URIN", "Sondage urinaire", "Soins", 5000),
    ("PANS-BRUL", "Pansement de brûlure", "Soins", 6000),
    ("ACC-NORM", "Accouchement voie basse", "Maternité", 35000),
    ("CESAR", "Césarienne", "Maternité", 150000),
    ("EPISIO", "Épisiotomie", "Maternité", 10000),
    ("ECHO-OBS", "Échographie obstétricale", "Imagerie", 15000),
    ("ECHO-ABD", "Échographie abdominale", "Imagerie", 15000),
    ("RADIO-TH", "Radiographie thoracique", "Imagerie", 12000),
    ("RADIO-MEM", "Radiographie des membres", "Imagerie", 10000),
    ("HOSP-JOUR", "Journée d'hospitalisation (général)", "Hospitalisation", 7500),
    ("HOSP-LUXE", "Journée d'hospitalisation (luxe)", "Hospitalisation", 20000),
    ("HOSP-SI", "Journée de soins intensifs", "Hospitalisation", 45000),
    ("OXYGENE", "Oxygénothérapie (par heure)", "Hospitalisation", 2500),
    ("VACC-BCG", "Vaccination BCG", "Vaccination", 1000),
    ("VACC-VAT", "Vaccination antitétanique", "Vaccination", 1500),
    ("VACC-PENTA", "Vaccination pentavalent", "Vaccination", 2000),
    ("CERT-MED", "Certificat médical", "Administratif", 5000),
    ("CERT-DECES", "Certificat de décès", "Administratif", 3000),
    ("DOSSIER", "Ouverture de dossier médical", "Administratif", 1000),
    ("TRANSF-AMB", "Transport par ambulance", "Autre", 25000),
    ("PETIT-CHIR", "Petite chirurgie", "Chirurgie", 45000),
    ("HERNIE", "Cure de hernie inguinale", "Chirurgie", 180000),
    ("APPEND", "Appendicectomie", "Chirurgie", 200000),
    ("CIRCONC", "Circoncision", "Chirurgie", 30000),
]
SPECIALITES = [
    ("MG", "Médecine générale"), ("PED", "Pédiatrie"), ("GYN", "Gynécologie-obstétrique"),
    ("CHIR", "Chirurgie générale"), ("CARD", "Cardiologie"), ("DERM", "Dermatologie"),
    ("OPH", "Ophtalmologie"), ("ORL", "Oto-rhino-laryngologie"),
    ("RAD", "Radiologie"), ("BIO", "Biologie médicale"),
    ("ANES", "Anesthésie-réanimation"), ("PSY", "Psychiatrie"),
    ("TRAUM", "Traumatologie"), ("NEPH", "Néphrologie"),
]
# NB : pas d'entrée « Médecine générale » ici — le département existe déjà sous
# le code MEDGEN. En ajouter un second (MED) créait un doublon qui éclatait les
# médecins et les rendez-vous entre deux départements de même nom.
DEPARTEMENTS = [
    ("MAT", "Maternité"), ("PED", "Pédiatrie"),
    ("CHIR", "Chirurgie"), ("URG", "Urgences"), ("LAB", "Laboratoire"),
    ("IMG", "Imagerie médicale"), ("PHAR", "Pharmacie"), ("ADM", "Administration"),
]
SERVICES = [
    ("ACC", "Accueil / Réception"), ("CONS", "Consultations externes"),
    ("HOSP", "Hospitalisation"), ("BLOC", "Bloc opératoire"),
    ("LABO", "Laboratoire d'analyses"), ("PHAR", "Pharmacie"),
    ("MAT", "Maternité"), ("URG", "Urgences"), ("CAISSE", "Caisse"),
    ("RH", "Ressources humaines"), ("COMPTA", "Comptabilité"),
    ("MAINT", "Maintenance / Logistique"), ("STOCK", "Magasin / Stock"),
]
GRADES = [
    ("A1", "Cadre supérieur"), ("A2", "Cadre"), ("B1", "Agent de maîtrise"),
    ("B2", "Agent qualifié"), ("C1", "Agent d'exécution"), ("C2", "Stagiaire"),
]
FONCTIONS_SOIGNANTES = [
    "Médecin généraliste", "Sage-femme", "Infirmier diplômé d'État",
    "Aide-soignant", "Technicien de laboratoire", "Pharmacien",
    "Préparateur en pharmacie", "Caissier", "Agent d'accueil",
    "Gestionnaire de stock", "Comptable", "Agent d'entretien",
    "Chauffeur d'ambulance", "Assistant RH", "Technicien radiologie",
]
FOURNISSEURS = [
    ("LABOREX", "Laborex Côte d'Ivoire", "Abidjan", "Grossiste pharmaceutique"),
    ("COPHARMED", "Copharmed", "Abidjan", "Médicaments génériques"),
    ("DPCI", "Distribution Pharmaceutique de CI", "Abidjan", "Médicaments et consommables"),
    ("UBIPHARM", "Ubipharm CI", "Abidjan", "Grossiste répartiteur"),
    ("MEDIS-CI", "Médis Côte d'Ivoire", "Yamoussoukro", "Consommables médicaux"),
    ("TECHMED", "TechMed Équipements", "Abidjan", "Équipements et maintenance"),
    ("BUROSTOCK", "Buro Stock", "Yamoussoukro", "Fournitures de bureau"),
    ("ALIMPRO", "Alim Pro Services", "Yamoussoukro", "Restauration et hygiène"),
    ("GAZMED", "Gaz Médical CI", "Abidjan", "Oxygène médical"),
]
ZONES_IMAGERIE = [
    ("echographie", "Abdomen complet"), ("echographie", "Pelvis / obstétricale"),
    ("echographie", "Rénale bilatérale"), ("radiographie", "Thorax face"),
    ("radiographie", "Rachis lombaire"), ("radiographie", "Genou droit"),
    ("radiographie", "Poignet gauche"), ("radiographie", "Bassin"),
    ("scanner", "Crâne sans injection"), ("scanner", "Abdomino-pelvien"),
    ("irm", "Rachis cervical"), ("autre", "Doppler des membres inférieurs"),
]
ROLES = [
    ("Médecin", "medecin"), ("Infirmier", "infirmier"), ("Pharmacien", "pharmacien"),
    ("Laborantin", "laborantin"), ("Caissier", "caissier"), ("Accueil", "accueil"),
    ("Comptable", "comptable"), ("RH", "rh"), ("Directeur", "directeur"),
    ("Administrateur", "administrateur"),
]
CHECKLIST_ADMISSION = [
    "Bracelet d'identification posé", "Consentement éclairé signé",
    "Constantes d'entrée relevées", "Inventaire des effets personnels",
    "Dossier médical ouvert", "Personne à prévenir enregistrée",
    "Allergies documentées",
]
CHECKLIST_SERVICE = [
    "Lit préparé et désinfecté", "Perfusion en place",
    "Traitement du jour administré", "Repas adapté commandé",
    "Visite médicale effectuée", "Sortie préparée",
]
JOURS_FERIES = [
    ("01-01", "Jour de l'An"), ("05-01", "Fête du Travail"),
    ("08-07", "Fête de l'Indépendance"), ("08-15", "Assomption"),
    ("11-01", "Toussaint"), ("11-15", "Journée nationale de la Paix"),
    ("12-25", "Noël"),
]


class Command(BaseCommand):
    help = "Injecte un jeu de données de démonstration dans tous les modules."

    def add_arguments(self, parser):
        parser.add_argument('--scale', type=int, default=1,
                            help="Multiplicateur de volume (1 = standard).")
        parser.add_argument('--seed', type=int, default=20260814,
                            help="Graine aléatoire (même graine = même jeu).")
        parser.add_argument('--no-users', action='store_true',
                            help="Ne pas créer les comptes de test par rôle.")
        parser.add_argument('--corriger-rdv', action='store_true',
                            help="Ne rien créer : réparer les rendez-vous "
                                 "existants (type de consultation, département, "
                                 "médecins, champs laissés vides).")
        parser.add_argument('--aujourdhui', action='store_true',
                            help="Date tous les dossiers du jour même (alimente les "
                                 "filtres « aujourd'hui » des listes et du tableau "
                                 "de bord).")

    # ── Utilitaires ───────────────────────────────────────────────────────
    def _log(self, label, n):
        self.created[label] = self.created.get(label, 0) + n
        self.stdout.write(f"  {label:.<44} {n:>5}")

    def _dt(self, jours_avant, heure=None):
        """Datetime aware, `jours_avant` jours avant maintenant.

        Avec --aujourdhui, tout est ramené au jour même.

        Sinon le recul est plafonné au 1er janvier de l'année en cours :
        plusieurs modèles numérotent leurs dossiers en comptant les lignes de
        l'année (`filter(date_xxx__year=annee).count() + 1`). Antidater au-delà
        du 1er janvier sortirait ces lignes du comptage et produirait des
        numéros en double.
        """
        recul = 0 if self.today_only else min(jours_avant, self.jours_depuis_janvier)
        d = self.today - timedelta(days=recul)
        h = heure if heure is not None else self.rnd.randint(7, 18)
        naive = datetime.combine(d, time(h, self.rnd.choice([0, 15, 30, 45])))
        return timezone.make_aware(naive)

    def _pas(self, n):
        """Écart entre deux événements d'un même séjour.

        Un jour d'intervalle normalement ; en mode --aujourdhui on resserre à
        l'heure, sinon les visites d'un séjour ouvert aujourd'hui seraient
        datées de demain.
        """
        return timedelta(hours=n * 2) if self.today_only else timedelta(days=n)

    def _jour(self, jours_avant):
        """Date (sans heure) antidatée, ramenée au jour même avec --aujourdhui."""
        if self.today_only:
            return self.today
        return self.today - timedelta(days=jours_avant)

    def _tel(self):
        return f"+225 0{self.rnd.randint(1, 7)} {self.rnd.randint(10, 99)} " \
               f"{self.rnd.randint(10, 99)} {self.rnd.randint(10, 99)} " \
               f"{self.rnd.randint(10, 99)}"

    def _nom_prenom(self, sexe):
        prenoms = PRENOMS_F if sexe == 'F' else PRENOMS_M
        return self.rnd.choice(NOMS), self.rnd.choice(prenoms)

    def handle(self, *args, **opts):
        self.rnd = random.Random(opts['seed'])
        self.scale = max(1, opts['scale'])
        self.today_only = opts['aujourdhui']
        self.today = timezone.localdate()
        self.jours_depuis_janvier = (self.today - date(self.today.year, 1, 1)).days
        self.created = {}

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nSEED DEMO — échelle x{self.scale}, graine {opts['seed']}"
            + (f", tout daté du {self.today:%d/%m/%Y}" if self.today_only else "")
            + "\n"))

        self.admin = User.objects.filter(is_superuser=True).order_by('pk').first()
        if self.admin is None:
            self.stderr.write("Aucun superuser : créez-en un avant (createsuperuser).")
            return

        from centres.models import Centre
        self.centres = list(Centre.objects.order_by('pk'))
        if not self.centres:
            self.stderr.write("Aucun centre : créez au moins un centre avant.")
            return

        if opts['corriger_rdv']:
            from medecins.models import Medecin
            self.medecins = list(Medecin.objects.filter(actif=True))
            self.stdout.write(self.style.HTTP_INFO("\nRéparation des rendez-vous"))
            with transaction.atomic():
                self.reparer_rdv()
            self.stdout.write(self.style.SUCCESS(""))
            return

        steps = [
            ("Comptes et groupes", self.seed_users, not opts['no_users']),
            ("Référentiels médicaux", self.seed_referentiels, True),
            ("Personnel et médecins", self.seed_personnel, True),
            ("Patients", self.seed_patients, True),
            ("Rendez-vous et registres", self.seed_rendezvous, True),
            ("Consultations", self.seed_consultations, True),
            ("Laboratoire", self.seed_laboratoire, True),
            ("Imagerie", self.seed_imagerie, True),
            ("Chambres et hospitalisations", self.seed_hospitalisation, True),
            ("Soins", self.seed_soins, True),
            ("Facturation et paiements", self.seed_facturation, True),
            ("Caisse", self.seed_caisse, True),
            ("Stock et produits", self.seed_stock, True),
            ("Pharmacie", self.seed_pharmacie, True),
            ("Achats", self.seed_achats, True),
            ("Ressources humaines", self.seed_rh, True),
            ("Présence", self.seed_presence, True),
            ("Planning", self.seed_planning, True),
            ("Maternité et naissances", self.seed_maternite, True),
        ]
        for titre, fn, actif in steps:
            if not actif:
                continue
            self.stdout.write(self.style.HTTP_INFO(f"\n{titre}"))
            with transaction.atomic():
                fn()

        total = sum(self.created.values())
        self.stdout.write(self.style.SUCCESS(
            f"\n{total} enregistrements créés dans {len(self.created)} tables.\n"))

    # ═══════════════════════════════════════════════════════════════════
    # 1. Comptes et groupes
    # ═══════════════════════════════════════════════════════════════════
    def seed_users(self):
        n_g = n_u = 0
        self.role_users = {}
        for libelle, slug in ROLES:
            grp, cree = Group.objects.get_or_create(name=libelle)
            n_g += int(cree)
            u, cree = User.objects.get_or_create(
                username=slug,
                defaults=dict(first_name=libelle, last_name="Démo",
                              email=f"{slug}@wale.demo", is_staff=True),
            )
            if cree:
                u.set_password("wale2024")
                u.save()
                n_u += 1
            u.groups.add(grp)
            self.role_users[slug] = u
        self._log("Groupes", n_g)
        self._log("Comptes de test (mot de passe wale2024)", n_u)

    # ═══════════════════════════════════════════════════════════════════
    # 2. Référentiels
    # ═══════════════════════════════════════════════════════════════════
    def seed_referentiels(self):
        from achats.models import Fournisseur
        from consultations.models import DiagnosticCIM
        from employer.models import Fonction, Grade, JourFerie, Nationalite, TypeContrat
        from facturation.models import Acte
        from hospitalisation.models import (Batiment, ListeControleAdmission,
                                            ListeVerificationService)
        from laboratoire.models import TypeExamen
        from medecins.models import Departement, Service, Specialite
        from patients.models import Assurance

        n = 0
        for code, nom in SPECIALITES:
            _, c = Specialite.objects.get_or_create(code=code, defaults={'nom': nom})
            n += int(c)
        self._log("Spécialités", n)

        n = 0
        for code, nom in DEPARTEMENTS:
            _, c = Departement.objects.get_or_create(code=code, defaults={'nom': nom})
            n += int(c)
        self._log("Départements", n)

        n = 0
        for code, nom in SERVICES:
            _, c = Service.objects.get_or_create(code=code, defaults={'nom': nom})
            n += int(c)
        self._log("Services", n)

        n = 0
        for code, nom in GRADES:
            _, c = Grade.objects.get_or_create(code=code, defaults={'nom': nom})
            n += int(c)
        self._log("Grades", n)

        n = 0
        for nom in FONCTIONS_SOIGNANTES:
            _, c = Fonction.objects.get_or_create(nom=nom)
            n += int(c)
        self._log("Fonctions", n)

        n = 0
        for nom in ("CDI", "CDD", "Stage", "Prestation", "Fonctionnaire détaché"):
            _, c = TypeContrat.objects.get_or_create(nom=nom)
            n += int(c)
        self._log("Types de contrat", n)

        n = 0
        for nom in ("Ivoirienne", "Burkinabè", "Malienne", "Guinéenne", "Française"):
            _, c = Nationalite.objects.get_or_create(nom=nom)
            n += int(c)
        self._log("Nationalités", n)

        n = 0
        for nom, code, taux in [("CNAM", "CNAM", 70), ("MUGEFCI", "MUGEF", 80),
                                ("SUNU Assurances", "SUNU", 75),
                                ("NSIA Assurances", "NSIA", 80),
                                ("Ascoma CI", "ASCOMA", 65),
                                ("Allianz CI", "ALLIANZ", 85)]:
            _, c = Assurance.objects.get_or_create(
                code=code, defaults={'nom': nom, 'taux_prise_en_charge': taux})
            n += int(c)
        self._log("Assurances", n)

        n = 0
        for code, libelle, cat, prix in ACTES:
            _, c = Acte.objects.get_or_create(
                code=code, defaults={'libelle': libelle, 'categorie': cat, 'prix': prix})
            n += int(c)
        self._log("Actes médicaux", n)

        n = 0
        for code, nom, cat, prix, delai in EXAMENS_LABO:
            _, c = TypeExamen.objects.get_or_create(
                code=code, defaults={'nom': nom, 'categorie': cat,
                                     'prix': prix, 'delai_resultat_heures': delai})
            n += int(c)
        self._log("Types d'examen", n)

        n = 0
        for code, libelle in [
            ("A00", "Choléra"), ("A09", "Diarrhée et gastro-entérite"),
            ("B50", "Paludisme à Plasmodium falciparum"), ("B54", "Paludisme non précisé"),
            ("E11", "Diabète sucré de type 2"), ("E66", "Obésité"),
            ("I10", "Hypertension essentielle"), ("I50", "Insuffisance cardiaque"),
            ("J06", "Infection aiguë des voies respiratoires supérieures"),
            ("J18", "Pneumopathie"), ("J45", "Asthme"),
            ("K29", "Gastrite et duodénite"), ("K35", "Appendicite aiguë"),
            ("L03", "Cellulite"), ("M54", "Dorsalgie"),
            ("N39", "Infection des voies urinaires"), ("O80", "Accouchement normal"),
            ("D50", "Anémie par carence en fer"), ("H10", "Conjonctivite"),
            ("H66", "Otite moyenne"), ("R50", "Fièvre d'origine inconnue"),
            ("Z00", "Examen général de routine"),
        ]:
            _, c = DiagnosticCIM.objects.get_or_create(
                code=code, defaults={'libelle': libelle})
            n += int(c)
        self._log("Codes CIM-10", n)

        n = 0
        for code, nom, ville, spec in FOURNISSEURS:
            _, c = Fournisseur.objects.get_or_create(
                code=code, defaults={'nom': nom, 'ville': ville, 'specialites': spec,
                                     'telephone': self._tel(),
                                     'email': f"contact@{code.lower()}.ci",
                                     'conditions_paiement': self.rnd.choice(
                                         ["30 jours", "45 jours", "Comptant", "60 jours"]),
                                     'delai_livraison_moyen': self.rnd.randint(2, 21)})
            n += int(c)
        self._log("Fournisseurs", n)

        n = 0
        for nom in ("Bâtiment principal", "Pavillon maternité",
                    "Pavillon pédiatrie", "Aile chirurgicale"):
            _, c = Batiment.objects.get_or_create(
                nom=nom, defaults={'description': f"{nom} du centre médico-social."})
            n += int(c)
        self._log("Bâtiments", n)

        n = 0
        for item in CHECKLIST_ADMISSION:
            _, c = ListeControleAdmission.objects.get_or_create(item=item)
            n += int(c)
        for item in CHECKLIST_SERVICE:
            _, c = ListeVerificationService.objects.get_or_create(item=item)
            n += int(c)
        self._log("Listes de contrôle", n)

        n = 0
        annee = self.today.year
        for md, desc in JOURS_FERIES:
            m, d = md.split('-')
            _, c = JourFerie.objects.get_or_create(
                date=date(annee, int(m), int(d)), defaults={'description': desc})
            n += int(c)
        self._log("Jours fériés", n)

    # ═══════════════════════════════════════════════════════════════════
    # 3. Personnel
    # ═══════════════════════════════════════════════════════════════════
    def seed_personnel(self):
        from employer.models import Employe, Fonction, Grade, Nationalite, TypeContrat
        from medecins.models import Departement, Medecin, Service, Specialite

        fonctions = list(Fonction.objects.all())
        grades = list(Grade.objects.all())
        contrats = list(TypeContrat.objects.all())
        nationalites = list(Nationalite.objects.all())
        services = list(Service.objects.all())
        specialites = list(Specialite.objects.all())
        departements = list(Departement.objects.all())

        f_medecin = Fonction.objects.filter(nom__icontains="Médecin").first()
        f_sage = Fonction.objects.filter(nom__icontains="Sage-femme").first()
        f_infirmier = Fonction.objects.filter(nom__icontains="Infirmier").first()

        employes = []
        n_emp = 40 * self.scale
        for i in range(n_emp):
            sexe = self.rnd.choice(['M', 'F'])
            nom, prenoms = self._nom_prenom(sexe)
            if i < 14 * self.scale:
                fonction = f_medecin
            elif i < 20 * self.scale:
                fonction = f_sage or f_infirmier
            elif i < 28 * self.scale:
                fonction = f_infirmier
            else:
                fonction = self.rnd.choice(fonctions)
            emb = self.today - timedelta(days=self.rnd.randint(120, 4000))
            contrat = self.rnd.choice(contrats)
            fin = None
            if contrat and contrat.nom in ("CDD", "Stage"):
                fin = self.today + timedelta(days=self.rnd.choice([20, 45, 200, 400]))
            e = Employe(
                nom=nom, prenoms=prenoms, sexe=sexe,
                date_naissance=self.today - timedelta(days=self.rnd.randint(8000, 21000)),
                lieu_naissance=self.rnd.choice(["Yamoussoukro", "Bouaké", "Abidjan",
                                                "Daloa", "Toumbokro", "Korhogo"]),
                nationalite=self.rnd.choice(nationalites) if nationalites else None,
                situation_matrimoniale=self.rnd.choice(
                    ['celibataire', 'marie', 'divorce', 'veuf']),
                nombre_enfants=self.rnd.randint(0, 5),
                telephone=self._tel(), email="",
                adresse=f"{self.rnd.choice(QUARTIERS)}, Yamoussoukro",
                service=self.rnd.choice(services) if services else None,
                fonction=fonction,
                grade=self.rnd.choice(grades) if grades else None,
                type_contrat=contrat,
                date_embauche=emb, date_fin_contrat=fin,
                salaire_base=self.rnd.choice([120000, 150000, 200000, 280000,
                                              350000, 450000, 600000]),
                statut=self.rnd.choices(['actif', 'suspendu', 'quitte'],
                                        weights=[88, 6, 6])[0],
            )
            if e.statut == 'quitte':
                e.date_depart = self.today - timedelta(days=self.rnd.randint(10, 500))
            e.save()
            employes.append(e)
        self._log("Employés", len(employes))
        self.employes = list(Employe.objects.all())

        # Médecins : un dossier Medecin par employé « médecin / sage-femme »
        n_med = 0
        for e in employes[:18 * self.scale]:
            if Medecin.objects.filter(employe=e).exists():
                continue
            Medecin.objects.create(
                employe=e,
                specialite=self.rnd.choice(specialites) if specialites else None,
                departement=self.rnd.choice(departements) if departements else None,
                service=e.service,
                ordre_medecin=f"CNOM-{self.rnd.randint(10000, 99999)}-{e.pk}",
                taux_honoraire=self.rnd.choice([0, 10, 15, 20, 25]),
                actif=e.statut == 'actif',
            )
            n_med += 1
        self._log("Médecins", n_med)
        self.medecins = list(Medecin.objects.filter(actif=True))
        self.infirmiers = [e for e in self.employes if e.fonction and
                           ('nfirmier' in e.fonction.nom or 'ide-soignant' in e.fonction.nom)]

        # Chefs de service
        n = 0
        for s in Service.objects.filter(chef_service__isnull=True):
            if self.medecins:
                s.chef_service = self.rnd.choice(self.medecins)
                s.save(update_fields=['chef_service'])
                n += 1
        self._log("Chefs de service désignés", n)

    # ═══════════════════════════════════════════════════════════════════
    # 4. Patients
    # ═══════════════════════════════════════════════════════════════════
    def seed_patients(self):
        from patients.models import Assurance, Patient

        assurances = list(Assurance.objects.all())
        patients = []
        for i in range(120 * self.scale):
            sexe = self.rnd.choice(['M', 'F'])
            nom, prenoms = self._nom_prenom(sexe)
            centre = self.centres[0] if self.rnd.random() < 0.75 else \
                self.rnd.choice(self.centres)
            ass = self.rnd.choice(assurances) if self.rnd.random() < 0.35 else None
            p = Patient(
                centre=centre, nom=nom, prenoms=prenoms,
                date_naissance=self.today - timedelta(days=self.rnd.randint(200, 30000)),
                lieu_naissance=self.rnd.choice(["Yamoussoukro", "Toumbokro", "Bouaké",
                                                "Abidjan", "Didiévi", "Kossou"]),
                sexe=sexe, profession=self.rnd.choice(PROFESSIONS),
                telephone=self._tel(),
                telephone2=self._tel() if self.rnd.random() < 0.25 else "",
                adresse=f"{self.rnd.choice(QUARTIERS)}",
                ville="Yamoussoukro" if centre == self.centres[0] else "Toumbokro",
                groupe_sanguin=self.rnd.choice(GROUPES_SANGUINS)
                if self.rnd.random() < 0.6 else "",
                allergies=self.rnd.choice(["", "", "", "Pénicilline", "Aspirine",
                                           "Arachide", "Sulfamides"]),
                antecedents=self.rnd.choice(["", "", "HTA connue depuis 5 ans",
                                             "Diabète type 2", "Asthme dans l'enfance",
                                             "Drépanocytose AS", "Ulcère gastrique"]),
                assurance=ass,
                numero_assurance=f"{ass.code}-{self.rnd.randint(100000, 999999)}"
                if ass else "",
                date_expiration_assurance=self.today + timedelta(
                    days=self.rnd.randint(-60, 700)) if ass else None,
                contact_urgence_nom=f"{self.rnd.choice(NOMS)} "
                                    f"{self.rnd.choice(PRENOMS_M + PRENOMS_F)}",
                contact_urgence_telephone=self._tel(),
            )
            p.save()
            patients.append(p)
            Patient.all_objects.filter(pk=p.pk).update(
                date_creation=self._dt(self.rnd.randint(0, 300)))
        self._log("Patients", len(patients))
        self.patients = list(Patient.all_objects.all())

    # ═══════════════════════════════════════════════════════════════════
    # 5. Rendez-vous et registres
    # ═══════════════════════════════════════════════════════════════════
    def reparer_rdv(self):
        """Rend cohérents les rendez-vous déjà enregistrés.

        Un rendez-vous dont le type de consultation sort de la catégorie « CS »,
        ou dont le médecin appartient à un autre département que celui du
        rendez-vous, s'ouvre avec des listes déroulantes vides : la valeur
        stockée est filtrée à l'affichage. On réattribue donc un trio cohérent
        et on renseigne les champs restés vides.
        """
        from medecins.models import Departement
        from patients.models import RendezVous
        from services.models import Articleservice

        self._fusionner_departement_double()
        self._departementer_consultations()

        types_cons = list(Articleservice.objects.filter(
            actif=True, categorie__code='CS', departement__isnull=False)
            .select_related('departement'))
        departements = list(Departement.objects.all())
        if not types_cons:
            self.stderr.write("Aucune prestation de catégorie CS : rien à faire.")
            return

        valides = {a.pk for a in types_cons}
        n_trio = n_champs = 0
        for r in RendezVous.objects.all().iterator():
            champs = []
            incoherent = (
                r.type_consultation_id not in valides
                or (r.medecin_id and r.departement_id
                    and r.medecin.departement_id != r.departement_id)
            )
            if incoherent:
                t, d, m, jr = self._trio_rdv(types_cons, departements)
                r.type_consultation, r.departement = t, d
                r.medecin, r.docteur_jr = m, jr
                champs += ['type_consultation', 'departement', 'medecin', 'docteur_jr']
                n_trio += 1
            elif r.docteur_jr_id is None and self.rnd.random() < 0.4:
                equipe = [x for x in self.medecins
                          if x.departement_id == r.departement_id and x.pk != r.medecin_id]
                if equipe:
                    r.docteur_jr = self.rnd.choice(equipe)
                    champs.append('docteur_jr')

            if not r.notes:
                r.notes = self.rnd.choice(NOTES_RDV); champs.append('notes')
            if not r.maladies:
                r.maladies = self.rnd.choice(MALADIES_RDV); champs.append('maladies')
            if not r.antecedents_maladie:
                r.antecedents_maladie = self.rnd.choice(ANTECEDENTS_RDV)
                champs.append('antecedents_maladie')
            if not r.historique_passee:
                r.historique_passee = self.rnd.choice(HISTORIQUE_RDV)
                champs.append('historique_passee')
            if not r.principales_plaintes:
                r.principales_plaintes = self.rnd.choice(MOTIFS_CONSULT)
                champs.append('principales_plaintes')
            if not r.salle_consultation:
                r.salle_consultation = f"Salle {self.rnd.randint(1, 8)}"
                champs.append('salle_consultation')
            if r.date_suivi is None and self.rnd.random() < 0.35:
                r.date_suivi = r.date_heure + timedelta(
                    days=self.rnd.choice([7, 15, 30]))
                champs.append('date_suivi')
            if not r.rdv_exterieur and self.rnd.random() < 0.12:
                r.rdv_exterieur = True; champs.append('rdv_exterieur')

            if champs:
                # update_fields : ne pas déclencher le recalcul de duree_minutes
                # du save() complet, qui écraserait les durées déjà en place.
                r.save(update_fields=list(dict.fromkeys(champs)))
                n_champs += 1
        self._log("Rendez-vous rendus cohérents (type/dépt/médecins)", n_trio)
        self._log("Rendez-vous complétés", n_champs)

    def _fusionner_departement_double(self):
        """Supprime le département « Médecine générale » (MED) créé en doublon
        d'un MEDGEN préexistant, en rapatriant ce qui y pointe."""
        from medecins.models import Departement, Medecin
        from patients.models import Pathologie, RendezVous
        from services.models import Articleservice
        from soins.models import ProcedureSoin, Soin

        double = Departement.objects.filter(code='MED').first()
        cible = Departement.objects.filter(code='MEDGEN').first()
        if not double or not cible:
            return
        n = 0
        for modele in (Medecin, Articleservice, Pathologie, RendezVous, Soin,
                       ProcedureSoin):
            n += modele._base_manager.filter(departement=double).update(
                departement=cible)
        double.delete()
        self._log("Rattachements au département en doublon repris", n)

    def _departementer_consultations(self):
        """Rattache un département aux types de consultation qui n'en ont pas.

        Le formulaire de rendez-vous masque — et vide — toute option dont le
        département ne correspond pas exactement à celui choisi (voir le filtre
        JS de rendez_vous_form.html). Une prestation sans département est donc
        inutilisable dès qu'un département est sélectionné.
        """
        from medecins.models import Departement
        from services.models import Articleservice

        par_code = {d.code: d for d in Departement.objects.all()}
        defaut = par_code.get('MEDGEN') or par_code.get('MED')
        regles = [
            (('GYNECO', 'PRENATALE', 'OBSTETRIQUE', 'POSTNATAL'), 'GYN'),
            (('ENFANT', 'NOURRISSON', 'PEDIATR'), 'PED'),
            (('URGENCE', 'PERMANENCE'), 'URG'),
            (('ACCOUCHEMENT',), 'MAT'),
        ]
        n = 0
        for a in Articleservice.objects.filter(actif=True, categorie__code='CS',
                                               departement__isnull=True):
            nom = a.nom.upper()
            dept = next((par_code.get(code) for mots, code in regles
                         if any(m in nom for m in mots) and par_code.get(code)), None)
            dept = dept or defaut
            if dept:
                a.departement = dept
                a.save(update_fields=['departement'])
                n += 1
        self._log("Types de consultation rattachés à un département", n)

    def _trio_rdv(self, types_cons, departements):
        """Type de consultation, département et médecins cohérents entre eux.

        Le formulaire de rendez-vous n'affiche que les médecins et les types
        rattachés au département choisi (attribut data-departement-id posé par
        DepartementFiltreSelect, filtré en JS). Tirer les trois au hasard
        indépendamment donnait donc des rendez-vous dont les listes déroulantes
        s'ouvraient vides : la valeur enregistrée était masquée par le filtre.
        """
        from medecins.models import Medecin

        type_cons = self.rnd.choice(types_cons) if types_cons else None
        dept = type_cons.departement if type_cons and type_cons.departement_id else None
        if dept is None:
            # Un département qui compte au moins un médecin actif, sinon le
            # sélecteur de médecin se retrouve vide une fois filtré.
            candidats = [d for d in departements
                         if any(m.departement_id == d.pk for m in self.medecins)]
            dept = self.rnd.choice(candidats) if candidats else (
                self.rnd.choice(departements) if departements else None)
        equipe = [m for m in self.medecins if dept and m.departement_id == dept.pk]
        if not equipe:
            equipe = self.medecins
        medecin = self.rnd.choice(equipe) if equipe else None
        autres = [m for m in equipe if m != medecin]
        medecin_jr = self.rnd.choice(autres) if autres and self.rnd.random() < 0.4 else None
        return type_cons, dept, medecin, medecin_jr

    def seed_rendezvous(self):
        from gynecologie.models import TypeVisite
        from medecins.models import Departement
        from patients.models import (RegistreAccouchement, RegistreCPN,
                                     RegistreCuratif, RegistrePostnatale,
                                     RendezVous, TypeVisiteCurative)
        from services.models import Articleservice

        departements = list(Departement.objects.all())
        # Le formulaire n'accepte comme type de consultation que les prestations
        # de la catégorie « CS » (voir patients.forms.RendezVousForm) : prendre
        # ailleurs produit un rendez-vous dont le champ paraît vide à l'écran,
        # car la valeur enregistrée n'est pas dans la liste déroulante.
        types_cons = list(Articleservice.objects.filter(
            actif=True, categorie__code='CS').select_related('departement'))
        tv_cpn = list(TypeVisite.objects.all())
        tv_cur = list(TypeVisiteCurative.objects.all())
        femmes = [p for p in self.patients if p.sexe == 'F']

        rdvs = []
        for i in range(160 * self.scale):
            p = self.rnd.choice(self.patients)
            # −45 jours … +20 jours pour alimenter passé, aujourd'hui et à venir
            decalage = 0 if self.today_only else self.rnd.randint(-45, 20)
            dt = timezone.make_aware(datetime.combine(
                self.today + timedelta(days=decalage),
                time(self.rnd.randint(7, 17), self.rnd.choice([0, 15, 30, 45]))))
            if decalage < -1:
                statut = self.rnd.choices(
                    ['termine', 'annule', 'absent'], weights=[75, 12, 13])[0]
            elif decalage <= 0:
                statut = self.rnd.choice(
                    ['confirme', 'en_attente', 'en_consultation', 'termine'])
            else:
                statut = self.rnd.choices(['planifie', 'confirme'], weights=[60, 40])[0]
            type_rdv = self.rnd.choices(
                ['consultation', 'controle', 'urgence', 'examen', 'vaccination'],
                weights=[55, 18, 10, 10, 7])[0]
            type_cons, dept, medecin, medecin_jr = self._trio_rdv(types_cons,
                                                                  departements)
            r = RendezVous(
                patient=p,
                medecin=medecin, docteur_jr=medecin_jr,
                departement=dept,
                type_consultation=type_cons,
                salle_consultation=f"Salle {self.rnd.randint(1, 8)}",
                date_heure=dt, duree_minutes=self.rnd.choice([15, 20, 30, 45, 60]),
                date_suivi=dt + timedelta(days=self.rnd.choice([7, 15, 30]))
                if self.rnd.random() < 0.35 else None,
                type_rdv=type_rdv,
                niveau_urgence=self.rnd.choices(
                    ['normal', 'urgent', 'tres_urgent'], weights=[80, 15, 5])[0],
                motif=self.rnd.choice(MOTIFS_CONSULT), statut=statut,
                notes=self.rnd.choice(NOTES_RDV),
                maladies=self.rnd.choice(MALADIES_RDV),
                principales_plaintes=self.rnd.choice(MOTIFS_CONSULT),
                antecedents_maladie=self.rnd.choice(ANTECEDENTS_RDV),
                historique_passee=self.rnd.choice(HISTORIQUE_RDV),
                rdv_exterieur=self.rnd.random() < 0.12,
                temps_constante_minutes=self.rnd.randint(2, 12),
                temps_attente_minutes=self.rnd.randint(5, 90),
                temps_consultation_minutes=self.rnd.randint(8, 45),
            )
            if statut in ('confirme', 'en_attente', 'en_consultation', 'termine'):
                r.date_confirme = dt - timedelta(hours=self.rnd.randint(2, 48))
            if statut in ('en_attente', 'en_consultation', 'termine'):
                r.date_en_attente = dt
            if statut in ('en_consultation', 'termine'):
                r.date_en_consultation = dt + timedelta(minutes=r.temps_attente_minutes)
            if statut == 'termine':
                r.date_termine = dt + timedelta(
                    minutes=r.temps_attente_minutes + r.temps_consultation_minutes)
            r.save()
            RendezVous.objects.filter(pk=r.pk).update(
                date_creation=dt - timedelta(
                    days=0 if self.today_only else self.rnd.randint(0, 20)))
            rdvs.append(r)
        self._log("Rendez-vous", len(rdvs))
        self.rdvs = rdvs

        # ── Registres (consultation curative / CPN / accouchement / postnatal) ──
        n_cur = n_cpn = n_acc = n_post = 0
        for r in rdvs:
            if r.statut != 'termine':
                continue
            if r.patient.sexe == 'F' and self.rnd.random() < 0.30 and tv_cpn:
                r.cpn_type_visite = self.rnd.choice(tv_cpn)
                r.cpn_mode_entree = self.rnd.choice(
                    ['venu_lui_meme', 'reference_centre', 'refere_tradipraticien'])
                r.type_visite_cpn = self.rnd.choice(
                    ['cpn1', 'cpn2', 'cpn3', 'cpn4', 'cpn5plus'])
                r.save(update_fields=['cpn_type_visite', 'cpn_mode_entree',
                                      'type_visite_cpn'])
                RegistreCPN.objects.get_or_create(
                    rdv=r, defaults={'donnees': self._donnees_cpn()})
                n_cpn += 1
                if self.rnd.random() < 0.30:
                    RegistreAccouchement.objects.get_or_create(
                        rdv=r, defaults={'donnees': self._donnees_accouchement()})
                    n_acc += 1
                if self.rnd.random() < 0.25:
                    RegistrePostnatale.objects.get_or_create(
                        rdv=r, defaults={'donnees': {
                            'post_jours_post_partum': str(self.rnd.randint(1, 42)),
                            'post_etat_general': self.rnd.choice(['Bon', 'Passable']),
                            'post_involution_uterine': 'Normale',
                            'post_lochies': self.rnd.choice(['Normales', 'Abondantes']),
                            'post_allaitement': self.rnd.choice(['Exclusif', 'Mixte']),
                            'post_remarques': '',
                        }})
                    n_post += 1
            elif self.rnd.random() < 0.45 and tv_cur:
                r.cur_type_visite = self.rnd.choice(tv_cur)
                r.cur_mode_entree = self.rnd.choice(
                    ['venu_lui_meme', 'reference_centre'])
                r.save(update_fields=['cur_type_visite', 'cur_mode_entree'])
                RegistreCuratif.objects.get_or_create(
                    rdv=r, defaults={'donnees': self._donnees_curatif(r)})
                n_cur += 1
        self._log("Registres consultation curative", n_cur)
        self._log("Registres CPN", n_cpn)
        self._log("Registres accouchement", n_acc)
        self._log("Registres postnatal", n_post)

    def _donnees_curatif(self, rdv):
        from patients.models import Pathologie
        patho = list(Pathologie.objects.values_list('pk', flat=True)[:60])
        return {
            'cur_mode_entree': rdv.cur_mode_entree or 'venu_lui_meme',
            'cur_mode_entree_autre': '',
            'cur_type_population': self.rnd.choice(
                ['population_generale', 'scolaire', 'personnel']),
            'cur_type_visite': str(rdv.cur_type_visite_id or ''),
            'cur_motif_consultation': self.rnd.choice(MOTIFS_CONSULT),
            'cur_examen_physique': self.rnd.choice([
                "Bon état général, conjonctives colorées.",
                "Fébrile à 38,7 °C, abdomen souple.",
                "Auscultation pulmonaire : râles crépitants à la base droite.",
            ]),
            'cur_diagnostic': [str(x) for x in self.rnd.sample(
                patho, min(2, len(patho)))] if patho else [],
            'cur_traitement': self.rnd.choice([
                "ACT 3 jours + paracétamol", "Amoxicilline 7 jours",
                "Réhydratation orale + zinc", "Antihypertenseur en continu",
            ]),
            'cur_issue_consultation': self.rnd.choice(
                ['gueri', 'ameliorant', 'refere', 'hospitalise']),
            'cur_traitement_anterieur': '',
            'cur_atcd_autres': '', 'cur_atcd_chirurgicaux': '',
            'cur_atcd_obstetricaux': '', 'cur_ddr': '',
            'cur_tdr_paludisme': self.rnd.choice(['positif', 'negatif', '']),
            'cur_goutte_epaisse': '', 'cur_code_depistage': '',
            'cur_glycemie': str(round(self.rnd.uniform(0.7, 1.9), 2)),
            'cur_autres_examens': '', 'cur_duree_mo': '00:00',
            'cur_date_debut_mo': '', 'cur_date_fin_mo': '',
            'cur_remarques': '',
        }

    def _donnees_cpn(self):
        poids = round(self.rnd.uniform(48, 92), 1)
        taille = round(self.rnd.uniform(1.5, 1.78), 2)
        return {
            'cpn_numero_gestante': str(self.rnd.randint(1, 500)),
            'cpn_poids': str(poids), 'cpn_taille': str(taille),
            'cpn_imc': str(round(poids / (taille * taille), 1)),
            'cpn_temperature': str(round(self.rnd.uniform(36.2, 38.5), 1)),
            'cpn_pouls': str(self.rnd.randint(62, 105)),
            'cpn_freq_resp': str(self.rnd.randint(14, 24)),
            'cpn_ta_gauche': f"{self.rnd.randint(95, 145)}/{self.rnd.randint(60, 95)}",
            'cpn_ta_droit': f"{self.rnd.randint(95, 145)}/{self.rnd.randint(60, 95)}",
            'cpn_perimetre_brachial_cm': str(round(self.rnd.uniform(21, 33), 1)),
            'cpn_statut_vat': self.rnd.choice(['vat1', 'vat2', 'complet']),
            'cpn_statut_vih_accueil': self.rnd.choice(['negatif', 'inconnu']),
            'cpn_hu': str(self.rnd.randint(12, 38)),
            'cpn_age_gestationnel': str(self.rnd.randint(8, 40)),
            'cpn_semaines_amenorrhee': str(self.rnd.randint(8, 40)),
            'cpn_presentation': self.rnd.choice(['cephalique', 'siege', 'transverse']),
            'cpn_bdcf': str(self.rnd.randint(120, 160)),
            'cpn_gestite': str(self.rnd.randint(1, 7)),
            'cpn_parite': str(self.rnd.randint(0, 6)),
            'cpn_enfants_vivants': str(self.rnd.randint(0, 5)),
            'cpn_enfants_decedes': '0',
            'cpn_groupe_sanguin': self.rnd.choice(GROUPES_SANGUINS),
            'cpn_taux_hemoglobine': str(round(self.rnd.uniform(8.5, 13.5), 1)),
            'cpn_etat_nutritionnel': self.rnd.choice(['bon', 'moyen']),
            'cpn_remarques': '',
        }

    def _donnees_accouchement(self):
        return {
            'acc_mode': self.rnd.choice(['voie_basse', 'cesarienne']),
            'acc_duree_travail': f"{self.rnd.randint(2, 18)} h",
            'acc_delivrance': self.rnd.choice(['complete', 'dirigee']),
            'acc_perte_sanguine': f"{self.rnd.randint(150, 600)} ml",
            'acc_episiotomie': self.rnd.choice(['oui', 'non']),
            'acc_etat_mere': self.rnd.choice(['Bon', 'Bon', 'Passable']),
            'acc_apgar_1': str(self.rnd.randint(6, 10)),
            'acc_apgar_5': str(self.rnd.randint(8, 10)),
            'acc_remarques': '',
        }

    # ═══════════════════════════════════════════════════════════════════
    # 6. Consultations
    # ═══════════════════════════════════════════════════════════════════
    def seed_consultations(self):
        from consultations.models import (Constante, Consultation, Diagnostic,
                                          DiagnosticCIM, ExamenDemande,
                                          LigneOrdonnance, Ordonnance)
        from pharmacie.models import Medicament
        from stock.models import Produit

        cims = list(DiagnosticCIM.objects.all())
        produits = list(Produit.objects.filter(actif=True)[:80])
        medicaments = list(Medicament.objects.all()[:80])
        rdvs_dispo = [r for r in self.rdvs if r.statut == 'termine'
                      and not hasattr(r, 'consultation')]

        consultations, ordonnances = [], []
        n_diag = n_const = n_lignes = n_exam = 0
        for i in range(100 * self.scale):
            rdv = rdvs_dispo.pop() if rdvs_dispo and self.rnd.random() < 0.7 else None
            p = rdv.patient if rdv else self.rnd.choice(self.patients)
            dt = rdv.date_heure if rdv else self._dt(self.rnd.randint(0, 120))
            c = Consultation(
                patient=p,
                medecin=self.rnd.choice(self.medecins) if self.medecins else None,
                rendez_vous=rdv, motif=self.rnd.choice(MOTIFS_CONSULT),
                anamnese=self.rnd.choice([
                    "Début brutal, pas de notion de contage.",
                    "Symptomatologie évoluant depuis une semaine, automédication.",
                    "Patient suivi pour pathologie chronique, observance correcte.",
                    "",
                ]),
                statut=self.rnd.choices(['termine', 'en_cours', 'annule'],
                                        weights=[85, 10, 5])[0],
                cree_par=self.admin,
            )
            c.save()
            Consultation.objects.filter(pk=c.pk).update(date_heure=dt)
            consultations.append(c)

            Constante.objects.create(
                consultation=c,
                poids=round(self.rnd.uniform(3, 110), 1),
                taille=round(self.rnd.uniform(0.5, 1.95), 2),
                temperature=round(self.rnd.uniform(35.8, 40.2), 1),
                tension_systolique=self.rnd.randint(85, 175),
                tension_diastolique=self.rnd.randint(50, 105),
                pouls=self.rnd.randint(55, 130),
                frequence_respiratoire=self.rnd.randint(12, 34),
                saturation_oxygene=round(self.rnd.uniform(88, 100), 1),
                glycemie=round(self.rnd.uniform(0.6, 2.4), 2),
                niveau_douleur=self.rnd.randint(0, 10),
            )
            n_const += 1

            for k in range(self.rnd.randint(1, 3)):
                Diagnostic.objects.create(
                    consultation=c,
                    cim=self.rnd.choice(cims) if cims and self.rnd.random() < 0.7 else None,
                    libelle_libre=self.rnd.choice(DIAGNOSTICS_LIBRES)
                    if self.rnd.random() < 0.5 else "",
                    type_diagnostic='principal' if k == 0 else
                    self.rnd.choice(['associe', 'differentiel']),
                    notes="",
                )
                n_diag += 1

            if self.rnd.random() < 0.75:
                o = Ordonnance(
                    consultation=c, patient=p, medecin=c.medecin,
                    date_expiration=(dt + timedelta(days=90)).date(),
                    statut=self.rnd.choices(
                        ['emise', 'delivree', 'partielle', 'expiree'],
                        weights=[40, 40, 12, 8])[0],
                    type_ordonnance=self.rnd.choices(
                        ['interne', 'externe'], weights=[80, 20])[0],
                    notes="",
                )
                o.save()
                Ordonnance.objects.filter(pk=o.pk).update(date_emission=dt)
                ordonnances.append(o)
                for _ in range(self.rnd.randint(1, 5)):
                    prod = self.rnd.choice(produits) if produits else None
                    med = self.rnd.choice(medicaments) if medicaments else None
                    LigneOrdonnance.objects.create(
                        ordonnance=o,
                        produit=prod if self.rnd.random() < 0.6 else None,
                        medicament=med if self.rnd.random() < 0.3 else None,
                        medicament_libre="" if prod else self.rnd.choice(
                            [m[0] for m in MEDICAMENTS]),
                        posologie=self.rnd.choice(POSOLOGIES),
                        duree=self.rnd.choice(DUREES),
                        quantite=self.rnd.choice([1, 2, 6, 10, 14, 20, 30]),
                    )
                    n_lignes += 1

            for _ in range(self.rnd.choice([0, 0, 1, 1, 2])):
                type_ex = self.rnd.choices(
                    ['laboratoire', 'imagerie', 'autre'], weights=[70, 25, 5])[0]
                libelle = self.rnd.choice(EXAMENS_LABO)[1] \
                    if type_ex == 'laboratoire' else self.rnd.choice(ZONES_IMAGERIE)[1]
                ExamenDemande.objects.create(
                    consultation=c, type_examen=type_ex, libelle=libelle,
                    urgence=self.rnd.random() < 0.2,
                    statut=self.rnd.choice(['demande', 'en_cours', 'resultat', 'valide']),
                )
                n_exam += 1

        self._log("Consultations", len(consultations))
        self._log("Constantes", n_const)
        self._log("Diagnostics", n_diag)
        self._log("Ordonnances", len(ordonnances))
        self._log("Lignes d'ordonnance", n_lignes)
        self._log("Examens demandés", n_exam)
        self.consultations = consultations
        self.ordonnances = ordonnances

    # ═══════════════════════════════════════════════════════════════════
    # 7. Laboratoire
    # ═══════════════════════════════════════════════════════════════════
    def seed_laboratoire(self):
        from consultations.models import ExamenDemande
        from laboratoire.models import (AnalyseLaboratoire, DemandeExamen,
                                        LigneDemandeExamen, ResultatAnalyse,
                                        TypeExamen)

        types = list(TypeExamen.objects.all())
        techniciens = [self.admin] + list(
            User.objects.filter(username__in=['laborantin', 'medecin']))

        # ── Demandes d'examens (workflow brouillon → terminé) ──
        n_lignes = 0
        demandes = []
        for i in range(70 * self.scale):
            p = self.rnd.choice(self.patients)
            statut = self.rnd.choices(
                ['brouillon', 'demande', 'accepte', 'en_cours', 'termine'],
                weights=[20, 20, 15, 20, 25])[0]
            d = DemandeExamen(
                centre=p.centre or self.centres[0], patient=p,
                type_test=self.rnd.choice(['hematologie', 'biochimie', 'bacteriologie',
                                           'serologie', 'parasitologie', 'imagerie']),
                statut=statut,
                date_prelevement=self._dt(self.rnd.randint(0, 60))
                if statut != 'brouillon' else None,
                technicien=self.rnd.choice(techniciens),
                medecin_prescripteur=self.rnd.choice(self.medecins)
                if self.medecins else None,
                commentaire=self.rnd.choice(
                    ["", "", "Patient à jeun depuis 12 h.",
                     "Prélèvement à réaliser avant toute antibiothérapie.",
                     "Résultats à transmettre en urgence au médecin traitant."]),
                urgent=self.rnd.random() < 0.2,
                cree_par=self.admin,
            )
            d.save()
            total = Decimal('0')
            for te in self.rnd.sample(types, self.rnd.randint(1, 5)):
                LigneDemandeExamen.objects.create(
                    demande=d, type_examen=te, libelle=te.nom, prix=te.prix,
                    instructions=self.rnd.choice(
                        ["", "", "Tube EDTA", "Tube sec", "À jeun",
                         "Prélèvement le matin", "2 tubes"]),
                )
                total += te.prix
                n_lignes += 1
            d.montant_total = total
            d.save(update_fields=['montant_total'])
            DemandeExamen.all_objects.filter(pk=d.pk).update(
                date_creation=self._dt(self.rnd.randint(0, 60)))
            demandes.append(d)
        self._log("Demandes d'examens", len(demandes))
        self._log("Lignes de demande", n_lignes)
        self.demandes_examens = demandes

        # ── Analyses + résultats ──
        exams_labo = list(ExamenDemande.objects.filter(
            type_examen='laboratoire', analyselaboratoire__isnull=True)[:60 * self.scale])
        analyses, n_res = [], 0
        for i in range(60 * self.scale):
            p = self.rnd.choice(self.patients)
            te = self.rnd.choice(types)
            statut = self.rnd.choices(
                ['recu', 'en_analyse', 'resultat', 'valide', 'envoye'],
                weights=[18, 22, 20, 30, 10])[0]
            ed = exams_labo.pop() if exams_labo and self.rnd.random() < 0.5 else None
            a = AnalyseLaboratoire(
                patient=ed.consultation.patient if ed else p,
                examen_demande=ed, type_examen=te, statut=statut,
                technicien=self.rnd.choice(techniciens),
                validateur=self.admin if statut in ('valide', 'envoye') else None,
                date_resultat=self._dt(self.rnd.randint(0, 40))
                if statut in ('resultat', 'valide', 'envoye') else None,
                commentaire=self.rnd.choice(["", "", "Hémolyse légère du prélèvement.",
                                             "Contrôle recommandé dans 15 jours."]),
                urgent=self.rnd.random() < 0.18,
            )
            a.save()
            AnalyseLaboratoire.objects.filter(pk=a.pk).update(
                date_prelevement=self._dt(self.rnd.randint(0, 45)))
            analyses.append(a)

            if statut in ('resultat', 'valide', 'envoye'):
                params = PARAMS_LABO.get(te.code, [(te.nom, "", 0, 1)])
                for nom, unite, mini, maxi in params:
                    if maxi > 1:
                        val = round(self.rnd.uniform(mini * 0.75, maxi * 1.3), 2)
                        if val < mini:
                            interp = 'bas'
                        elif val > maxi:
                            interp = 'eleve' if val < maxi * 1.2 else 'critique'
                        else:
                            interp = 'normal'
                        valeur = str(int(val) if val > 1000 else val)
                        vmin, vmax = str(mini), str(maxi)
                    else:
                        valeur = self.rnd.choice(["Positif", "Négatif", "Négatif"])
                        interp = 'normal' if valeur == "Négatif" else 'eleve'
                        vmin = vmax = ""
                    ResultatAnalyse.objects.create(
                        analyse=a, parametre=nom, valeur=valeur, unite=unite,
                        valeur_normale_min=vmin, valeur_normale_max=vmax,
                        interpretation=interp)
                    n_res += 1
        self._log("Analyses de laboratoire", len(analyses))
        self._log("Résultats d'analyse", n_res)

    # ═══════════════════════════════════════════════════════════════════
    # 8. Imagerie
    # ═══════════════════════════════════════════════════════════════════
    def seed_imagerie(self):
        from consultations.models import ExamenDemande
        from laboratoire.models import ExamenImagerie

        exams = list(ExamenDemande.objects.filter(
            type_examen='imagerie', examenimagerie__isnull=True)[:40 * self.scale])
        n = 0
        for i in range(30 * self.scale):
            type_img, zone = self.rnd.choice(ZONES_IMAGERIE)
            ed = exams.pop() if exams and self.rnd.random() < 0.5 else None
            statut = self.rnd.choices(['recu', 'en_cours', 'resultat', 'valide'],
                                      weights=[20, 20, 25, 35])[0]
            e = ExamenImagerie(
                patient=ed.consultation.patient if ed else self.rnd.choice(self.patients),
                examen_demande=ed, type_imagerie=type_img, zone_examinee=zone,
                statut=statut,
                compte_rendu="" if statut in ('recu', 'en_cours') else self.rnd.choice([
                    "Pas d'anomalie décelable sur l'ensemble des coupes explorées.",
                    "Épanchement pleural de faible abondance à droite.",
                    "Grossesse évolutive monofœtale, biométrie concordante.",
                    "Lithiase rénale droite de 6 mm sans dilatation.",
                ]),
                conclusion="" if statut in ('recu', 'en_cours') else self.rnd.choice([
                    "Examen normal.", "À contrôler dans un mois.",
                    "Avis spécialisé recommandé.",
                ]),
                radiologue=self.admin, urgent=self.rnd.random() < 0.15,
            )
            e.save()
            ExamenImagerie.objects.filter(pk=e.pk).update(
                date_examen=self._dt(self.rnd.randint(0, 60)))
            n += 1
        self._log("Examens d'imagerie", n)

    # ═══════════════════════════════════════════════════════════════════
    # 9. Chambres et hospitalisations
    # ═══════════════════════════════════════════════════════════════════
    def seed_hospitalisation(self):
        from hospitalisation.models import (Chambre, ChecklistAdmission,
                                            ChecklistVerification,
                                            EvaluationClinique, FicheVisite,
                                            Hospitalisation,
                                            LogActiviteHospitalisation,
                                            RegistreDeces, ResumeDecharge,
                                            ServiceAFacturer, VisiteDocteur,
                                            VisiteInfirmiere)
        from patients.models import Pathologie
        from services.models import Articleservice
        from stock.models import UniteMesure

        types_ch = ['general', 'semi_special', 'luxe', 'super_luxe', 'suite',
                    'partage', 'soins_intensifs', 'dialyse', 'salle_reveil']
        chambres = []
        for centre in self.centres:
            for i in range(14 if centre == self.centres[0] else 8):
                tc = self.rnd.choice(types_ch)
                c = Chambre(
                    centre=centre,
                    nom=f"Chambre {i + 1:02d}" if tc != 'soins_intensifs'
                    else f"Box SI {i + 1}",
                    type_chambre=tc, statut=self.rnd.random() < 0.92,
                    nombre_lits=1 if tc in ('luxe', 'super_luxe', 'suite')
                    else self.rnd.choice([2, 2, 3, 4, 6]),
                    prive=tc in ('luxe', 'super_luxe', 'suite'),
                    genre=self.rnd.choice(['unisexe', 'masculin', 'feminin']),
                    acces_internet=tc in ('luxe', 'super_luxe', 'suite'),
                    climatisation=tc != 'general',
                    salle_bains_privee=tc in ('luxe', 'super_luxe', 'suite',
                                              'semi_special'),
                    television=tc in ('luxe', 'super_luxe', 'suite'),
                    telephone_chambre=tc in ('super_luxe', 'suite'),
                    lit_visiteur=tc in ('suite', 'super_luxe'),
                    refrigerateur=tc in ('suite', 'super_luxe'),
                    danger_biologique=tc == 'dialyse',
                    description=f"{tc.replace('_', ' ').capitalize()} — {centre.nom}",
                )
                c.save()
                chambres.append(c)
        self._log("Chambres", len(chambres))

        pathologies = list(Pathologie.objects.filter(actif=True)[:80])
        soins_art = list(Articleservice.objects.all()[:60])
        unites = list(UniteMesure.objects.all())
        hospis = []
        n_fv = n_vi = n_vd = n_saf = n_ev = n_rd = n_ck = n_log = 0

        for i in range(32 * self.scale):
            p = self.rnd.choice(self.patients)
            statut = self.rnd.choices(
                ['brouillon', 'confirme', 'hospitalise', 'decharge', 'termine', 'annule'],
                weights=[10, 12, 30, 18, 25, 5])[0]
            jours = self.rnd.randint(1, 25)
            admission = self._dt(jours, heure=self.rnd.randint(8, 20))
            ch = self.rnd.choice(chambres)
            h = Hospitalisation(
                statut=statut, patient=p,
                medecin_traitant=self.rnd.choice(self.medecins) if self.medecins else None,
                medecin_referent=self.rnd.choice(self.medecins) if self.medecins else None,
                maladie=self.rnd.choice(pathologies) if pathologies else None,
                date_admission=admission,
                chambre=ch, numero_lit=self.rnd.randint(1, max(1, ch.nombre_lits)),
                infirmiere_primaire=self.rnd.choice(self.medecins)
                if self.medecins else None,
                nom_parent_gardien=f"{self.rnd.choice(NOMS)} "
                                   f"{self.rnd.choice(PRENOMS_F + PRENOMS_M)}",
                phone_parent_gardien=self._tel(),
                cas_legal=self.rnd.random() < 0.1,
                motif_admission=self.rnd.choice([
                    "Paludisme grave avec anémie sévère.",
                    "Surveillance post-opératoire.",
                    "Décompensation cardiaque.",
                    "Déshydratation sévère sur gastro-entérite.",
                    "Menace d'accouchement prématuré.",
                    "Traumatisme fermé de jambe.",
                ]),
                notes="", cree_par=self.admin,
            )
            if statut in ('hospitalise', 'decharge', 'termine'):
                h.heure_entree = admission
            if statut in ('decharge', 'termine'):
                h.heure_sortie = admission + self._pas(
                    self.rnd.randint(1, max(1, jours)))
            h.save()
            if h.heure_entree:
                Hospitalisation.objects.filter(pk=h.pk).update(
                    heure_entree=h.heure_entree, heure_sortie=h.heure_sortie)
            hospis.append(h)

            EvaluationClinique.objects.create(
                hospitalisation=h,
                poids=round(self.rnd.uniform(8, 105), 1),
                taille=round(self.rnd.uniform(0.6, 1.9), 2),
                temperature=round(self.rnd.uniform(36, 40.5), 1),
                frequence_respiratoire=self.rnd.randint(12, 36),
                tension_systolique=self.rnd.randint(80, 180),
                tension_diastolique=self.rnd.randint(45, 110),
                saturation_o2=round(self.rnd.uniform(85, 100), 1),
                glycemie=round(self.rnd.uniform(0.5, 2.8), 2),
                niveau_douleur=self.rnd.randint(0, 10),
            )
            n_ev += 1

            if statut in ('hospitalise', 'decharge', 'termine'):
                for j in range(self.rnd.randint(1, 5)):
                    fv = FicheVisite(
                        hospitalisation=h,
                        medecin=self.rnd.choice(self.medecins) if self.medecins else None,
                        observation=self.rnd.choice([
                            "Apyrétique, bon état général, alimentation reprise.",
                            "Persistance de la fièvre, hémocultures en cours.",
                            "Douleur contrôlée sous antalgiques palier 2.",
                            "Pansement refait, plaie propre, pas d'écoulement.",
                        ]),
                        evolution=self.rnd.choice(["Favorable", "Stationnaire",
                                                   "Lentement favorable"]),
                        prescriptions=self.rnd.choice([
                            "Poursuite du traitement en cours.",
                            "Ajout de fer par voie orale.",
                            "Ablation de la perfusion, relais oral.",
                        ]),
                        constantes={'temperature': round(self.rnd.uniform(36, 39.5), 1),
                                    'ta': f"{self.rnd.randint(90, 160)}/"
                                          f"{self.rnd.randint(55, 100)}",
                                    'pouls': self.rnd.randint(58, 120)},
                    )
                    fv.save()
                    FicheVisite.objects.filter(pk=fv.pk).update(
                        date_visite=admission + self._pas(j))
                    n_fv += 1

                for j in range(self.rnd.randint(2, 6)):
                    VisiteInfirmiere.objects.create(
                        hospitalisation=h,
                        date=admission + self._pas(j) + timedelta(
                            minutes=self.rnd.randint(0, 90)),
                        soin=self.rnd.choice(soins_art) if soins_art else None,
                        quantite=self.rnd.choice([1, 1, 2, 3]),
                        unite_mesure=self.rnd.choice(unites) if unites else None,
                        infirmiere=self.rnd.choice(self.medecins)
                        if self.medecins else None,
                        remarques=self.rnd.choice(["", "", "Bien toléré."]),
                        ordre=j,
                    )
                    n_vi += 1
                for j in range(self.rnd.randint(1, 3)):
                    VisiteDocteur.objects.create(
                        hospitalisation=h,
                        date=admission + self._pas(j),
                        soin=self.rnd.choice(soins_art) if soins_art else None,
                        instruction=self.rnd.choice([
                            "Surveiller la diurèse toutes les 6 h.",
                            "Perfusion de sérum salé 1 litre sur 8 h.",
                            "Bilan de contrôle demain matin à jeun.",
                        ]),
                        docteur=self.rnd.choice(self.medecins) if self.medecins else None,
                        ordre=j,
                    )
                    n_vd += 1
                for j in range(self.rnd.randint(1, 4)):
                    ServiceAFacturer.objects.create(
                        hospitalisation=h,
                        service=self.rnd.choice(soins_art) if soins_art else None,
                        unite_mesure=self.rnd.choice(unites) if unites else None,
                        quantite=self.rnd.choice([1, 1, 2, 4, 7]),
                        date=(admission + self._pas(j)).date(),
                        source=self.rnd.choice(['visite_infirmiere', 'visite_docteur',
                                                'soin', 'meo', 'manuel']),
                        ordre=j,
                    )
                    n_saf += 1
                for item in self.rnd.sample(CHECKLIST_ADMISSION, 4):
                    ChecklistAdmission.objects.create(
                        hospitalisation=h, item=item,
                        verifie=self.rnd.random() < 0.8, ordre=n_ck)
                    n_ck += 1
                for item in self.rnd.sample(CHECKLIST_SERVICE, 3):
                    ChecklistVerification.objects.create(
                        hospitalisation=h, item=item,
                        termine=self.rnd.random() < 0.7, ordre=n_ck)
                    n_ck += 1
                for msg, typ in [("Admission enregistrée", 'statut'),
                                 ("Constantes d'entrée saisies", 'note'),
                                 ("Chambre attribuée", 'modif')]:
                    LogActiviteHospitalisation.objects.create(
                        hospitalisation=h, user=self.admin, type=typ, message=msg)
                    n_log += 1

            if statut in ('decharge', 'termine'):
                ResumeDecharge.objects.create(
                    hospitalisation=h,
                    transfert=self.rnd.random() < 0.15,
                    diagnostic_decharge=self.rnd.choice(DIAGNOSTICS_LIBRES),
                    plan_sortie="Contrôle en consultation externe dans 7 jours.",
                    instructions="Poursuivre le traitement, repos 5 jours, "
                                 "revenir en cas de fièvre.",
                )
                n_rd += 1

        self._log("Hospitalisations", len(hospis))
        self._log("Évaluations cliniques", n_ev)
        self._log("Fiches de visite", n_fv)
        self._log("Visites infirmières", n_vi)
        self._log("Visites médicales", n_vd)
        self._log("Services à facturer", n_saf)
        self._log("Résumés de décharge", n_rd)
        self._log("Éléments de checklist", n_ck)
        self._log("Journal d'activité", n_log)
        self.hospitalisations = hospis

        n = 0
        for h in self.rnd.sample(hospis, min(3, len(hospis))):
            RegistreDeces.objects.create(
                patient=h.patient, date_deces=self.today - timedelta(
                    days=self.rnd.randint(1, 200)),
                hospitalisation=h,
                medecin=self.rnd.choice(self.medecins) if self.medecins else None,
                raison_deces=self.rnd.choice([
                    "Choc septique réfractaire.",
                    "Insuffisance respiratoire aiguë.",
                    "Paludisme grave forme neurologique.",
                ]),
                statut=self.rnd.choice(['brouillon', 'termine']),
            )
            n += 1
        self._log("Registre des décès", n)

    # ═══════════════════════════════════════════════════════════════════
    # 10. Soins
    # ═══════════════════════════════════════════════════════════════════
    def seed_soins(self):
        from medecins.models import Departement
        from patients.models import Pathologie
        from services.models import Articleservice
        from soins.models import ProcedureSoin, Soin

        departements = list(Departement.objects.all())
        pathologies = list(Pathologie.objects.filter(actif=True)[:60])
        arts = list(Articleservice.objects.all()[:60])
        infirmiers = self.infirmiers or self.employes

        soins, n_proc = [], 0
        for i in range(40 * self.scale):
            p = self.rnd.choice(self.patients)
            s = Soin(
                nom=self.rnd.choice(["Pansement", "Injection", "Perfusion",
                                     "Suture", "Prise de constantes", "Aérosol"]),
                patient=p,
                infirmier=self.rnd.choice(infirmiers) if infirmiers else None,
                motif=self.rnd.choice(["Plaie du pied", "Fièvre", "Suivi post-op",
                                       "Douleur abdominale", "Abcès"]),
                observations=self.rnd.choice([
                    "Soin réalisé sans incident.",
                    "Patient algique pendant le soin, antalgique administré.",
                    "Plaie en voie de cicatrisation.", "",
                ]),
                statut=self.rnd.choices(
                    ['brouillon', 'en_attente_de_paiement', 'en_cours',
                     'termine', 'annule'], weights=[10, 15, 20, 50, 5])[0],
                date_heure=self._dt(self.rnd.randint(0, 60)),
                departement=self.rnd.choice(departements) if departements else None,
                statut_maladie=self.rnd.choice(['aigu', 'chronique', 'ameliorant',
                                                'gueri', 'inchange']),
                severite=self.rnd.choice(['', 'moderee', 'severe']),
                maladie_infectieuse=self.rnd.random() < 0.2,
                maladie_allergique=self.rnd.random() < 0.1,
                cree_par=self.admin,
            )
            s.save()
            Soin.objects.filter(pk=s.pk).update(date_creation=s.date_heure)
            soins.append(s)

            for _ in range(self.rnd.randint(1, 3)):
                art = self.rnd.choice(arts) if arts else None
                pr = ProcedureSoin(
                    soin=s, patient=p,
                    infirmier=s.infirmier, soin_type=art,
                    prix=art.prix_vente if art and art.prix_vente else
                    self.rnd.choice([1500, 3000, 5000, 8000]),
                    departement=s.departement, date=s.date_heure,
                    maladie=self.rnd.choice(pathologies) if pathologies else None,
                    statut=self.rnd.choices(
                        ['brouillon', 'en_cours', 'termine', 'annule'],
                        weights=[10, 20, 65, 5])[0],
                    cree_par=self.admin,
                )
                pr.save()
                n_proc += 1
        self._log("Soins", len(soins))
        self._log("Procédures de soin", n_proc)
        self.soins = soins

    # ═══════════════════════════════════════════════════════════════════
    # 11. Facturation
    # ═══════════════════════════════════════════════════════════════════
    def seed_facturation(self):
        from facturation.models import Acte, Facture, LigneFacture, Paiement

        actes = list(Acte.objects.filter(actif=True))
        caissiers = [self.admin] + list(User.objects.filter(
            username__in=['caissier', 'comptable']))
        factures, n_lignes, n_paie = [], 0, 0

        sources = (
            [('consultation', c) for c in self.consultations[:60 * self.scale]] +
            [('hospitalisation', h) for h in self.hospitalisations] +
            [('laboratoire', d) for d in self.demandes_examens[:30 * self.scale]] +
            [('soins', s) for s in self.soins[:25 * self.scale]] +
            [('pharmacie', None)] * (15 * self.scale) +
            [('imagerie', None)] * (10 * self.scale) +
            [('autre', None)] * (5 * self.scale)
        )
        self.rnd.shuffle(sources)

        for type_fac, src in sources:
            if type_fac == 'consultation':
                patient, kw = src.patient, {'consultation': src}
            elif type_fac == 'hospitalisation':
                patient, kw = src.patient, {'hospitalisation': src}
            elif type_fac == 'laboratoire':
                patient, kw = src.patient, {}
            elif type_fac == 'soins':
                patient, kw = src.patient, {}
            else:
                patient, kw = self.rnd.choice(self.patients), {}

            statut = self.rnd.choices(['brouillon', 'emise', 'payee', 'annulee'],
                                      weights=[15, 30, 50, 5])[0]
            f = Facture(patient=patient, type_facture=type_fac, statut=statut,
                        date_echeance=self.today + timedelta(
                            days=self.rnd.choice([0, 7, 15, 30])),
                        notes="", cree_par=self.rnd.choice(caissiers), **kw)
            f.save()

            total = Decimal('0')
            for _ in range(self.rnd.randint(1, 4)):
                acte = self.rnd.choice(actes)
                qte = Decimal(self.rnd.choice([1, 1, 1, 2, 3, 5]))
                remise = Decimal(self.rnd.choice([0, 0, 0, 5, 10]))
                LigneFacture.objects.create(
                    facture=f, acte=acte, libelle=acte.libelle, quantite=qte,
                    prix_unitaire=acte.prix, remise=remise)
                total += qte * acte.prix * (1 - remise / 100)
                n_lignes += 1

            f.montant_total = round(total, 2)
            if patient.assurance:
                taux = patient.assurance.taux_prise_en_charge or Decimal('0')
                f.montant_assurance = round(f.montant_total * taux / 100, 2)
                f.ticket_moderateur = f.montant_total - f.montant_assurance
            if statut == 'payee':
                f.montant_paye = f.montant_total
            elif statut == 'emise' and self.rnd.random() < 0.35:
                f.montant_paye = round(f.montant_total / 2, 2)
            f.save()
            Facture.objects.filter(pk=f.pk).update(
                date_emission=self._dt(self.rnd.randint(0, 90)))
            factures.append(f)

            if f.montant_paye:
                reste = f.montant_paye
                for k in range(self.rnd.randint(1, 2)):
                    montant = reste if k else round(reste / self.rnd.choice([1, 1, 2]), 2)
                    if montant <= 0:
                        break
                    mode = self.rnd.choices(
                        ['especes', 'mobile_money', 'assurance', 'cheque',
                         'virement', 'bon'], weights=[45, 30, 12, 5, 5, 3])[0]
                    p = Paiement(facture=f, montant=montant, mode_paiement=mode,
                                 reference=f"{mode[:3].upper()}-"
                                           f"{self.rnd.randint(100000, 999999)}"
                                 if mode != 'especes' else "",
                                 recu_par=self.rnd.choice(caissiers))
                    p.save()
                    Paiement.objects.filter(pk=p.pk).update(
                        date_paiement=self._dt(self.rnd.randint(0, 90)))
                    n_paie += 1
                    reste -= montant
                    if reste <= 0:
                        break
        self._log("Factures", len(factures))
        self._log("Lignes de facture", n_lignes)
        self._log("Paiements", n_paie)
        self.factures = factures

        # Rattacher quelques demandes d'examens et soins à leurs factures
        from laboratoire.models import DemandeExamen
        from soins.models import Soin
        n = 0
        labo_fac = [f for f in factures if f.type_facture == 'laboratoire']
        for d, f in zip(self.demandes_examens, labo_fac):
            DemandeExamen.all_objects.filter(pk=d.pk).update(facture=f)
            n += 1
        soin_fac = [f for f in factures if f.type_facture == 'soins']
        for s, f in zip(self.soins, soin_fac):
            Soin.objects.filter(pk=s.pk).update(facture=f)
            n += 1
        self._log("Rattachements facture ↔ dossier", n)

    # ═══════════════════════════════════════════════════════════════════
    # 12. Caisse
    # ═══════════════════════════════════════════════════════════════════
    def seed_caisse(self):
        from caisse.models import Caisse, SessionCaisse, TransactionCaisse

        caissiers = [self.admin] + list(User.objects.filter(
            username__in=['caissier', 'comptable']))
        caisses = []
        for nom, code in [("Caisse principale", "CP01"),
                          ("Caisse pharmacie", "CPH1"),
                          ("Caisse laboratoire", "CLB1"),
                          ("Caisse Toumbokro", "CTB1")]:
            c, cree = Caisse.objects.get_or_create(
                code=code, defaults={'nom': nom,
                                     'responsable': self.rnd.choice(caissiers),
                                     'solde_actuel': self.rnd.randint(50000, 900000)})
            caisses.append(c)
        self._log("Caisses", len(caisses))

        factures_payees = [f for f in getattr(self, 'factures', [])
                           if f.montant_paye]
        sessions, n_tr = [], 0
        for jour in range(12 * self.scale):
            caisse = self.rnd.choice(caisses)
            ouverture = self._dt(jour, heure=7)
            # En mode --aujourdhui toutes les sessions sont du jour : on en laisse
            # une partie ouverte, le reste clôturé, pour couvrir les deux états.
            fermee = self.rnd.random() < 0.6 if self.today_only else jour > 0
            s = SessionCaisse(
                caisse=caisse, caissier=self.rnd.choice(caissiers),
                solde_ouverture=self.rnd.choice([20000, 50000, 100000]),
                statut='fermee' if fermee else 'ouverte',
                notes=self.rnd.choice(["", "", "Fond de caisse vérifié."]),
            )
            if fermee:
                s.date_fermeture = ouverture + timedelta(hours=11)
            s.save()
            SessionCaisse.objects.filter(pk=s.pk).update(date_ouverture=ouverture)
            sessions.append(s)

            total = Decimal(s.solde_ouverture)
            for _ in range(self.rnd.randint(4, 12)):
                type_tr = self.rnd.choices(
                    ['encaissement', 'decaissement', 'transfert'],
                    weights=[75, 18, 7])[0]
                fac = self.rnd.choice(factures_payees) if factures_payees and \
                    type_tr == 'encaissement' and self.rnd.random() < 0.6 else None
                montant = fac.montant_paye if fac else Decimal(
                    self.rnd.choice([1000, 2500, 3000, 5000, 7500, 12000, 25000]))
                t = TransactionCaisse(
                    session=s, type_transaction=type_tr,
                    mode_paiement=self.rnd.choices(
                        ['especes', 'mobile_money', 'cheque', 'virement'],
                        weights=[60, 30, 5, 5])[0],
                    montant=montant, facture=fac,
                    description={'encaissement': "Règlement patient",
                                 'decaissement': "Achat de fournitures",
                                 'transfert': "Transfert vers coffre"}[type_tr],
                    cree_par=s.caissier,
                )
                t.save()
                TransactionCaisse.objects.filter(pk=t.pk).update(
                    date_transaction=ouverture + timedelta(
                        hours=self.rnd.randint(1, 10)))
                total += montant if type_tr == 'encaissement' else -montant
                n_tr += 1
            if fermee:
                SessionCaisse.objects.filter(pk=s.pk).update(solde_fermeture=total)
        self._log("Sessions de caisse", len(sessions))
        self._log("Transactions de caisse", n_tr)

    # ═══════════════════════════════════════════════════════════════════
    # 13. Stock
    # ═══════════════════════════════════════════════════════════════════
    def seed_stock(self):
        from achats.models import Fournisseur
        from stock.models import (CategorieStock, CommandeStock, DemandePharmacie,
                                  FicheBesoins, Inventaire, LigneCommande,
                                  LigneDemande, LigneFicheBesoins, LigneInventaire,
                                  LotProduit, MouvementStock, Produit, UniteMesure)

        fournisseurs = list(Fournisseur.objects.filter(actif=True))
        unites = list(UniteMesure.objects.filter(actif=True)) or \
            list(UniteMesure.objects.all())
        cat_med = CategorieStock.objects.filter(type='medicament').first() or \
            CategorieStock.objects.create(nom="Médicaments", type='medicament')
        cat_cons = CategorieStock.objects.filter(type='consommable').first() or \
            CategorieStock.objects.create(nom="Consommables", type='consommable')

        produits = []
        for nom, dci, forme, dosage, pv, pa in MEDICAMENTS:
            p, cree = Produit.objects.get_or_create(
                nom=nom,
                defaults=dict(
                    type='medicament', categorie=cat_med, dci=dci,
                    dosage=dosage,
                    forme=forme if forme in ('comprime', 'gelule', 'sirop',
                                             'injectable', 'pommade') else 'autre',
                    unite_mesure=self.rnd.choice(unites) if unites else None,
                    fournisseur_principal=self.rnd.choice(fournisseurs)
                    if fournisseurs else None,
                    prescription_obligatoire=self.rnd.random() < 0.6,
                    stock_actuel=self.rnd.randint(0, 600),
                    stock_alerte=50, stock_minimum=20,
                    prix_achat=pa, prix_vente=pv,
                ))
            if cree:
                produits.append(p)
        for nom in CONSOMMABLES:
            p, cree = Produit.objects.get_or_create(
                nom=nom,
                defaults=dict(
                    type='consommable', categorie=cat_cons,
                    unite_mesure=self.rnd.choice(unites) if unites else None,
                    fournisseur_principal=self.rnd.choice(fournisseurs)
                    if fournisseurs else None,
                    stock_actuel=self.rnd.randint(0, 900),
                    stock_alerte=100, stock_minimum=40,
                    prix_achat=self.rnd.choice([200, 500, 1200, 2500]),
                    prix_vente=self.rnd.choice([400, 900, 2000, 4000]),
                ))
            if cree:
                produits.append(p)
        self._log("Produits", len(produits))
        tous_produits = list(Produit.objects.filter(actif=True))

        n_lots = 0
        for p in tous_produits:
            for _ in range(self.rnd.randint(1, 3)):
                qi = self.rnd.randint(50, 800)
                LotProduit.objects.create(
                    produit=p, numero_lot=f"LOT{self.rnd.randint(10000, 99999)}",
                    date_fabrication=self.today - timedelta(
                        days=self.rnd.randint(200, 900)),
                    # quelques lots périmés / bientôt périmés pour la page Péremptions
                    date_peremption=self.today + timedelta(
                        days=self.rnd.choice([-90, -20, 10, 25, 60, 150, 400, 700])),
                    quantite_initiale=qi,
                    quantite_actuelle=self.rnd.randint(0, qi),
                    fournisseur=self.rnd.choice(fournisseurs) if fournisseurs else None,
                    date_reception=self._jour(self.rnd.randint(1, 300)),
                    prix_achat_lot=p.prix_achat,
                )
                n_lots += 1
        self._log("Lots de produits", n_lots)

        n_mv = 0
        for _ in range(180 * self.scale):
            p = self.rnd.choice(tous_produits)
            lot = LotProduit.objects.filter(produit=p).order_by('?').first()
            type_mv = self.rnd.choices(
                ['entree', 'livraison', 'prescription', 'ajustement',
                 'peremption', 'retour'], weights=[25, 20, 35, 8, 5, 7])[0]
            qte = self.rnd.randint(1, 60)
            avant = self.rnd.randint(0, 500)
            apres = avant + qte if type_mv in ('entree', 'retour') else max(0, avant - qte)
            MouvementStock.objects.create(
                produit=p, lot=lot, type=type_mv,
                motif=self.rnd.choice(['achat', 'livraison', 'prescription',
                                       'inventaire', 'peremption', 'retour', 'don']),
                pharmacie=self.rnd.choice(['wale_yamoussoukro', 'wale_toumbokro']),
                quantite=qte, stock_avant=avant, stock_apres=apres,
                date=self._dt(self.rnd.randint(0, 120)),
                reference=f"REF{self.rnd.randint(1000, 9999)}",
                cree_par=self.admin,
            )
            n_mv += 1
        self._log("Mouvements de stock", n_mv)

        n_cmd = n_lc = 0
        for _ in range(10 * self.scale):
            statut = self.rnd.choices(
                ['brouillon', 'envoye', 'partiel', 'recu', 'annule'],
                weights=[15, 25, 15, 40, 5])[0]
            cmd = CommandeStock(
                fournisseur=self.rnd.choice(fournisseurs), statut=statut,
                date_commande=self._jour(self.rnd.randint(1, 120)),
                date_livraison_prevue=self.today + timedelta(
                    days=self.rnd.randint(-30, 30)),
                notes="",
            )
            if statut in ('recu', 'partiel'):
                cmd.date_reception = cmd.date_commande + (
                    timedelta(0) if self.today_only
                    else timedelta(days=self.rnd.randint(2, 20)))
            cmd.cree_par = self.admin
            cmd.save()
            total = Decimal('0')
            for p in self.rnd.sample(tous_produits, self.rnd.randint(2, 7)):
                qc = Decimal(self.rnd.randint(20, 400))
                qr = qc if statut == 'recu' else (
                    qc / 2 if statut == 'partiel' else Decimal('0'))
                LigneCommande.objects.create(
                    commande=cmd, produit=p, quantite_commandee=qc,
                    quantite_recue=qr, prix_unitaire=p.prix_achat)
                total += qc * p.prix_achat
                n_lc += 1
            cmd.montant_total = total
            cmd.save(update_fields=['montant_total'])
            n_cmd += 1
        self._log("Commandes de stock", n_cmd)
        self._log("Lignes de commande", n_lc)

        n_inv = n_li = 0
        for _ in range(4 * self.scale):
            inv = Inventaire(
                date_inventaire=self._jour(self.rnd.randint(1, 180)),
                statut=self.rnd.choice(['brouillon', 'valide', 'valide']),
                notes="Inventaire tournant.", cree_par=self.admin)
            inv.save()
            for p in self.rnd.sample(tous_produits, min(12, len(tous_produits))):
                th = Decimal(self.rnd.randint(0, 400))
                reel = th + Decimal(self.rnd.randint(-15, 10))
                LigneInventaire.objects.create(
                    inventaire=inv, produit=p, stock_theorique=th,
                    stock_reel=max(Decimal('0'), reel), ecart=reel - th)
                n_li += 1
            n_inv += 1
        self._log("Inventaires", n_inv)
        self._log("Lignes d'inventaire", n_li)

        n_dp = n_ld = 0
        for _ in range(10 * self.scale):
            dp = DemandePharmacie(
                pharmacie=self.rnd.choice(['wale_yamoussoukro', 'wale_toumbokro']),
                statut=self.rnd.choices(
                    ['en_attente', 'en_livraison', 'approuvee', 'partielle', 'refusee'],
                    weights=[25, 15, 35, 15, 10])[0],
                notes="Réapprovisionnement hebdomadaire.", cree_par=self.admin)
            dp.save()
            for p in self.rnd.sample(tous_produits, self.rnd.randint(3, 9)):
                qd = Decimal(self.rnd.randint(5, 120))
                LigneDemande.objects.create(
                    demande=dp, produit=p, quantite_demandee=qd,
                    quantite_approuvee=qd if dp.statut == 'approuvee' else
                    (qd / 2 if dp.statut == 'partielle' else Decimal('0')))
                n_ld += 1
            n_dp += 1
        self._log("Demandes pharmacie", n_dp)
        self._log("Lignes de demande", n_ld)

        n_fb = n_lfb = 0
        for k in range(4 * self.scale):
            debut = self.today.replace(day=1) - timedelta(days=30 * k)
            fb = FicheBesoins(
                pharmacie=self.rnd.choice(['wale_yamoussoukro', 'wale_toumbokro']),
                periode_debut=debut, periode_fin=debut + timedelta(days=29),
                statut=self.rnd.choice(['brouillon', 'soumis', 'valide', 'rejete']),
                notes="", cree_par=self.admin)
            fb.save()
            for p in self.rnd.sample(tous_produits, min(10, len(tous_produits))):
                cmm = Decimal(self.rnd.randint(10, 90))
                LigneFicheBesoins.objects.create(
                    fiche=fb, produit=p,
                    stock_initial=Decimal(self.rnd.randint(0, 300)),
                    qte_recue=Decimal(self.rnd.randint(0, 200)),
                    qte_dispensee=Decimal(self.rnd.randint(0, 150)),
                    cmm=cmm, qte_commander=cmm * 2,
                    qte_accordee=cmm * Decimal('1.5'))
                n_lfb += 1
            n_fb += 1
        self._log("Fiches de besoins", n_fb)
        self._log("Lignes de fiche de besoins", n_lfb)
        self.produits = tous_produits

    # ═══════════════════════════════════════════════════════════════════
    # 14. Pharmacie
    # ═══════════════════════════════════════════════════════════════════
    def seed_pharmacie(self):
        from achats.models import Fournisseur
        from pharmacie.models import (CategorieMedicament, CommandePharmacies,
                                      DispensationOrdonnance, InventairePharmacie,
                                      LigneDispensation, LigneInventairePharmacie,
                                      LigneVente, LotMedicament, Medicament,
                                      MouvementPharmacie, MouvementStock,
                                      StockPharmacie, VentePharmacie)

        fournisseurs = list(Fournisseur.objects.filter(actif=True))
        pharmacies = ['wale_yamoussoukro', 'wale_toumbokro']

        n = 0
        cats = {}
        for nom, code in [("Antalgiques", "ANTAL"), ("Antibiotiques", "ANTIB"),
                          ("Antipaludiques", "ANTIP"), ("Antihypertenseurs", "ANTIH"),
                          ("Antidiabétiques", "ANTID"), ("Solutés", "SOLUT"),
                          ("Vitamines", "VITAM"), ("Dermatologie", "DERMA")]:
            c, cree = CategorieMedicament.objects.get_or_create(
                code=code, defaults={'nom': nom})
            cats[code] = c
            n += int(cree)
        self._log("Catégories de médicaments", n)

        meds = []
        for i, (nom, dci, forme, dosage, pv, pa) in enumerate(MEDICAMENTS):
            m, cree = Medicament.objects.get_or_create(
                code=f"MED{i + 1:04d}",
                defaults=dict(
                    designation=nom, dci=dci, forme=forme, dosage=dosage,
                    categorie=self.rnd.choice(list(cats.values())),
                    prix_vente=pv, prix_achat=pa,
                    # une partie sous le seuil d'alerte pour la page Alertes réappro
                    stock_actuel=self.rnd.choice([0, 5, 18, 40, 120, 300, 650]),
                    stock_alerte=50, stock_minimum=20,
                ))
            meds.append(m)
        self._log("Médicaments (catalogue)", len(meds))

        n_lots = n_mv = 0
        for m in meds:
            for _ in range(self.rnd.randint(1, 3)):
                qi = self.rnd.randint(50, 700)
                LotMedicament.objects.create(
                    medicament=m, numero_lot=f"L{self.rnd.randint(10000, 99999)}",
                    date_fabrication=self.today - timedelta(
                        days=self.rnd.randint(180, 800)),
                    date_peremption=self.today + timedelta(
                        days=self.rnd.choice([-60, -10, 15, 45, 120, 365, 640])),
                    quantite_initiale=qi, quantite_actuelle=self.rnd.randint(0, qi),
                    fournisseur=self.rnd.choice(fournisseurs) if fournisseurs else None,
                )
                n_lots += 1
            for _ in range(self.rnd.randint(1, 4)):
                type_mv = self.rnd.choices(
                    ['entree', 'sortie', 'ajustement', 'peremption'],
                    weights=[35, 50, 10, 5])[0]
                qte = self.rnd.randint(1, 80)
                avant = self.rnd.randint(0, 400)
                apres = avant + qte if type_mv == 'entree' else max(0, avant - qte)
                mv = MouvementStock(
                    medicament=m, type_mouvement=type_mv,
                    motif=self.rnd.choice(['achat', 'vente', 'hospitalisation',
                                           'urgence', 'inventaire', 'perte']),
                    quantite=qte, stock_avant=avant, stock_apres=apres,
                    reference=f"MV{self.rnd.randint(1000, 9999)}", cree_par=self.admin)
                mv.save()
                MouvementStock.objects.filter(pk=mv.pk).update(
                    date_mouvement=self._dt(self.rnd.randint(0, 120)))
                n_mv += 1
        self._log("Lots de médicaments", n_lots)
        self._log("Mouvements (catalogue médicaments)", n_mv)

        n_cmd = 0
        for _ in range(8 * self.scale):
            c = CommandePharmacies(
                fournisseur=self.rnd.choice(fournisseurs) if fournisseurs else None,
                date_livraison_prevue=self.today + timedelta(
                    days=self.rnd.randint(-20, 30)),
                statut=self.rnd.choices(
                    ['brouillon', 'envoye', 'recu', 'partiel', 'annule'],
                    weights=[15, 30, 35, 15, 5])[0],
                montant_total=self.rnd.randint(150000, 4500000),
                notes="", cree_par=self.admin)
            c.save()
            CommandePharmacies.objects.filter(pk=c.pk).update(
                date_commande=self._jour(self.rnd.randint(1, 120)))
            n_cmd += 1
        self._log("Commandes pharmacie", n_cmd)

        # ── Stock par pharmacie ──
        # La création d'un produit crée déjà ses lignes de stock (à zéro) pour
        # chaque pharmacie : on complète les manquantes puis on valorise celles
        # restées vides, sinon toutes les pages pharmacie affichent 0.
        n_sp = n_mp = n_val = 0
        produits = getattr(self, 'produits', [])
        for ph in pharmacies:
            for p in produits:
                _, cree = StockPharmacie.objects.get_or_create(
                    pharmacie=ph, produit=p,
                    defaults={'quantite': self.rnd.randint(0, 400)})
                n_sp += int(cree)
        self._log("Stocks par pharmacie créés", n_sp)
        for sp in StockPharmacie.objects.filter(quantite=0):
            sp.quantite = self.rnd.choice([0, 8, 25, 60, 150, 320, 480])
            sp.save(update_fields=['quantite'])
            n_val += 1
        self._log("Stocks par pharmacie valorisés", n_val)

        for _ in range(120 * self.scale):
            p = self.rnd.choice(produits)
            type_mv = self.rnd.choices(
                ['entree', 'dispensation', 'vente', 'retour', 'ajustement'],
                weights=[22, 35, 30, 8, 5])[0]
            qte = Decimal(self.rnd.randint(1, 40))
            avant = Decimal(self.rnd.randint(0, 350))
            apres = avant + qte if type_mv in ('entree', 'retour') else \
                max(Decimal('0'), avant - qte)
            mp = MouvementPharmacie(
                pharmacie=self.rnd.choice(pharmacies), produit=p, type=type_mv,
                quantite=qte, stock_avant=avant, stock_apres=apres,
                reference=f"PH{self.rnd.randint(1000, 9999)}", cree_par=self.admin)
            mp.save()
            MouvementPharmacie.objects.filter(pk=mp.pk).update(
                date=self._dt(self.rnd.randint(0, 90)))
            n_mp += 1
        self._log("Mouvements pharmacie", n_mp)

        # ── Ventes au comptoir ──
        n_v = n_lv = 0
        for _ in range(50 * self.scale):
            v = VentePharmacie(
                pharmacie=self.rnd.choice(pharmacies),
                patient=self.rnd.choice(self.patients)
                if self.rnd.random() < 0.7 else None,
                mode_paiement=self.rnd.choices(
                    ['especes', 'mobile_money', 'assurance'], weights=[60, 32, 8])[0],
                statut=self.rnd.choices(['payee', 'annulee'], weights=[93, 7])[0],
                cree_par=self.admin)
            v.save()
            total = Decimal('0')
            for p in self.rnd.sample(produits, self.rnd.randint(1, 5)):
                qte = Decimal(self.rnd.randint(1, 12))
                LigneVente.objects.create(
                    vente=v, produit=p, quantite=qte,
                    prix_unitaire=p.prix_vente, montant=qte * p.prix_vente)
                total += qte * p.prix_vente
                n_lv += 1
            remise = Decimal(self.rnd.choice([0, 0, 0, 500, 1000]))
            VentePharmacie.objects.filter(pk=v.pk).update(
                montant_total=total, remise=remise, montant_net=total - remise,
                date_vente=self._dt(self.rnd.randint(0, 60)))
            n_v += 1
        self._log("Ventes pharmacie", n_v)
        self._log("Lignes de vente", n_lv)

        # ── Dispensations d'ordonnances ──
        n_d = n_ldp = 0
        for o in self.ordonnances[:30 * self.scale]:
            if o.statut not in ('delivree', 'partielle'):
                continue
            if DispensationOrdonnance.objects.filter(ordonnance=o).exists():
                continue
            d = DispensationOrdonnance(
                pharmacie=self.rnd.choice(pharmacies), ordonnance=o,
                statut='complete' if o.statut == 'delivree' else 'partielle',
                notes="", dispense_par=self.admin)
            d.save()
            DispensationOrdonnance.objects.filter(pk=d.pk).update(
                date=self._dt(self.rnd.randint(0, 60)))
            for lo in o.lignes.all():
                qp = lo.quantite or 1
                LigneDispensation.objects.create(
                    dispensation=d, produit=lo.produit,
                    medicament_libre=lo.medicament_libre,
                    quantite_prescrite=qp,
                    quantite_dispensee=qp if d.statut == 'complete'
                    else self.rnd.randint(0, qp),
                    achete_ailleurs=self.rnd.random() < 0.1)
                n_ldp += 1
            n_d += 1
        self._log("Dispensations", n_d)
        self._log("Lignes de dispensation", n_ldp)

        # ── Inventaires pharmacie ──
        n_i = n_lip = 0
        for _ in range(4 * self.scale):
            inv = InventairePharmacie(
                pharmacie=self.rnd.choice(pharmacies),
                date_inventaire=self._jour(self.rnd.randint(1, 150)),
                statut=self.rnd.choice(['brouillon', 'valide']),
                notes="", cree_par=self.admin)
            inv.save()
            if inv.statut == 'valide':
                InventairePharmacie.objects.filter(pk=inv.pk).update(
                    valide_par=self.admin, date_validation=timezone.now())
            for p in self.rnd.sample(produits, min(12, len(produits))):
                th = Decimal(self.rnd.randint(0, 300))
                LigneInventairePharmacie.objects.create(
                    inventaire=inv, produit=p, stock_theorique=th,
                    stock_reel=max(Decimal('0'),
                                   th + Decimal(self.rnd.randint(-12, 8))))
                n_lip += 1
            n_i += 1
        self._log("Inventaires pharmacie", n_i)
        self._log("Lignes d'inventaire pharmacie", n_lip)

    # ═══════════════════════════════════════════════════════════════════
    # 15. Achats
    # ═══════════════════════════════════════════════════════════════════
    def seed_achats(self):
        from achats.models import (BesoinAchat, CommandeAchat, Fournisseur,
                                   LigneBesoin, LigneCommandeAchat, LigneProforma,
                                   LigneReceptionAchat, Proforma, ReceptionAchat)

        fournisseurs = list(Fournisseur.objects.filter(actif=True))
        produits = getattr(self, 'produits', [])
        n_b = n_lb = n_p = n_lp = n_c = n_lc = n_r = n_lr = 0

        for k in range(14 * self.scale):
            statut = self.rnd.choices(
                ['brouillon', 'soumis', 'en_cours', 'satisfait', 'annule'],
                weights=[12, 20, 28, 36, 4])[0]
            b = BesoinAchat(
                titre=self.rnd.choice([
                    "Réapprovisionnement médicaments essentiels",
                    "Consommables bloc opératoire",
                    "Réactifs de laboratoire",
                    "Fournitures de bureau trimestrielles",
                    "Matériel de nettoyage",
                    "Pièces de rechange groupe électrogène",
                    "Oxygène médical",
                ]) + f" — lot {k + 1}",
                date_besoin_souhaite=self.today + timedelta(
                    days=self.rnd.randint(-20, 45)),
                statut=statut, notes="", cree_par=self.admin)
            b.save()
            lignes = []
            for p in self.rnd.sample(produits, self.rnd.randint(2, 6)):
                lb = LigneBesoin.objects.create(
                    besoin=b, produit=p, designation=p.nom,
                    quantite=Decimal(self.rnd.randint(10, 300)),
                    unite=p.unite_mesure.code if p.unite_mesure else "U")
                lignes.append(lb)
                n_lb += 1
            n_b += 1

            if statut == 'brouillon':
                continue
            # 1 à 3 proformas concurrentes par besoin
            proformas = []
            concurrents = self.rnd.sample(
                fournisseurs, min(len(fournisseurs), self.rnd.randint(1, 3)))
            for rang, f in enumerate(concurrents):
                # Un besoin en cours ou satisfait a forcément retenu une offre :
                # sans cela la chaîne s'arrête et les pages Commandes/Réceptions
                # restent vides.
                if rang == 0 and statut in ('en_cours', 'satisfait'):
                    st = 'valide'
                else:
                    st = self.rnd.choices(['en_attente', 'valide', 'rejete'],
                                          weights=[35, 30, 35])[0]
                pf = Proforma(
                    besoin=b, fournisseur=f,
                    date_reception=self._jour(self.rnd.randint(1, 40)),
                    reference_fournisseur=f"PRO-{self.rnd.randint(1000, 9999)}",
                    statut=st, notes="", soumis_par=self.admin)
                pf.save()
                total = Decimal('0')
                for lb in lignes:
                    pu = Decimal(self.rnd.randint(200, 12000))
                    LigneProforma.objects.create(
                        proforma=pf, ligne_besoin=lb, designation=lb.designation,
                        quantite=lb.quantite, prix_unitaire=pu)
                    total += lb.quantite * pu
                    n_lp += 1
                pf.montant_total = total
                if st == 'valide':
                    pf.valide_par = self.admin
                    pf.date_validation = timezone.now()
                pf.save()
                proformas.append(pf)
                n_p += 1

            # Commande sur la proforma validée
            validees = [p for p in proformas if p.statut == 'valide']
            if not validees:
                continue
            pf = validees[0]
            if statut == 'satisfait':
                st_cmd = 'recue'
            else:
                st_cmd = self.rnd.choices(
                    ['brouillon', 'envoyee', 'en_livraison', 'recue', 'annulee'],
                    weights=[12, 30, 28, 25, 5])[0]
            cmd = CommandeAchat(
                proforma=pf, fournisseur=pf.fournisseur,
                date_commande=self._jour(self.rnd.randint(1, 35)),
                date_livraison_prevue=self.today + timedelta(
                    days=self.rnd.randint(-15, 25)),
                statut=st_cmd, montant_total=pf.montant_total,
                notes="", cree_par=self.admin)
            cmd.save()
            lignes_cmd = []
            for lp in pf.lignes.all():
                lc = LigneCommandeAchat.objects.create(
                    commande=cmd, ligne_proforma=lp, designation=lp.designation,
                    quantite_commandee=lp.quantite, prix_unitaire=lp.prix_unitaire)
                lignes_cmd.append(lc)
                n_lc += 1
            n_c += 1

            if st_cmd != 'recue':
                continue
            rec = ReceptionAchat(
                commande=cmd,
                date_reception=self._jour(self.rnd.randint(0, 20)),
                statut=self.rnd.choices(['conforme', 'partielle', 'non_conforme'],
                                        weights=[65, 25, 10])[0],
                notes="", receptionne_par=self.admin,
                integre_en_stock=self.rnd.random() < 0.6)
            rec.save()
            if rec.integre_en_stock:
                ReceptionAchat.objects.filter(pk=rec.pk).update(
                    date_integration=timezone.now(), integre_par=self.admin)
            for lc in lignes_cmd:
                qr = lc.quantite_commandee if rec.statut == 'conforme' else \
                    lc.quantite_commandee / 2
                LigneReceptionAchat.objects.create(
                    reception=rec, ligne_commande=lc, quantite_recue=qr,
                    conforme=rec.statut != 'non_conforme',
                    numero_lot=f"LOT{self.rnd.randint(10000, 99999)}",
                    date_peremption=self.today + timedelta(
                        days=self.rnd.randint(90, 800)))
                n_lr += 1
            n_r += 1

        self._log("Besoins d'achat", n_b)
        self._log("Lignes de besoin", n_lb)
        self._log("Proformas", n_p)
        self._log("Lignes de proforma", n_lp)
        self._log("Commandes d'achat", n_c)
        self._log("Lignes de commande d'achat", n_lc)
        self._log("Réceptions", n_r)
        self._log("Lignes de réception", n_lr)

    # ═══════════════════════════════════════════════════════════════════
    # 16. Ressources humaines
    # ═══════════════════════════════════════════════════════════════════
    def seed_rh(self):
        from employer.models import (AlerteContrat, Conge, Employe,
                                     HistoriqueConge, HistoriqueEmploye,
                                     InfoSupplementaire, SoldeConge)

        employes = list(Employe.objects.all())
        annee = self.today.year

        # Un signal RH crée déjà un solde à l'embauche : on complète les
        # manquants (employés non actifs) puis on remplit les compteurs, laissés
        # à zéro par le signal.
        n = n_maj = 0
        for e in employes:
            _, cree = SoldeConge.objects.get_or_create(
                employe=e, annee=annee, defaults={'quota': 26})
            n += int(cree)
        self._log("Soldes de congés créés", n)
        for s in SoldeConge.objects.filter(annee=annee, jours_pris=0):
            s.jours_pris = self.rnd.randint(0, 22)
            s.jours_reporter = self.rnd.choice([0, 0, 0, 2, 5])
            s.save(update_fields=['jours_pris', 'jours_reporter'])
            n_maj += 1
        self._log("Soldes de congés renseignés", n_maj)

        types = ['annuel', 'annuel', 'annuel', 'maladie', 'maternite', 'paternite',
                 'exceptionnel', 'mariage_employe', 'deces_parent',
                 'naissance_enfant', 'sans_solde']
        n_c = n_h = 0
        for _ in range(50 * self.scale):
            e = self.rnd.choice(employes)
            debut = self.today if self.today_only else \
                self.today + timedelta(days=self.rnd.randint(-200, 40))
            duree = self.rnd.choice([1, 2, 3, 5, 7, 10, 14, 21, 30])
            fin = debut + timedelta(days=duree)
            if fin < self.today:
                statut = self.rnd.choices(['termine', 'refuse'], weights=[85, 15])[0]
            elif debut <= self.today <= fin:
                statut = 'en_cours'
            else:
                statut = self.rnd.choices(
                    ['demande', 'valide_service', 'approuve', 'refuse'],
                    weights=[35, 20, 35, 10])[0]
            c = Conge(
                employe=e, type_conge=self.rnd.choice(types),
                date_debut=debut, date_fin=fin,
                motif=self.rnd.choice(["Congé annuel", "Raisons familiales",
                                       "Repos médical", "Événement familial", ""]),
                statut=statut, deduit_du_solde=self.rnd.random() < 0.8,
                nb_jours_ouvres=max(1, int(duree * 5 / 7)),
                commentaire_rh=self.rnd.choice(["", "", "Accord de la direction."]),
            )
            if statut in ('approuve', 'en_cours', 'termine'):
                c.approuve_par = self.admin
                c.date_approbation = timezone.make_aware(datetime.combine(
                    debut - timedelta(days=5), time(9, 0)))
            if statut in ('valide_service', 'approuve', 'en_cours', 'termine'):
                c.valide_par_service = self.admin
                c.date_validation_service = timezone.make_aware(datetime.combine(
                    debut - timedelta(days=8), time(9, 0)))
            c.save()
            Conge.objects.filter(pk=c.pk).update(
                date_demande=timezone.make_aware(datetime.combine(
                    debut - timedelta(days=self.rnd.randint(10, 40)), time(10, 0))))
            n_c += 1
            actions = ['soumis']
            if statut in ('valide_service', 'approuve', 'en_cours', 'termine'):
                actions.append('valide_service')
            if statut in ('approuve', 'en_cours', 'termine'):
                actions.append('approuve')
            if statut == 'en_cours':
                actions.append('mis_en_cours')
            if statut == 'termine':
                actions += ['mis_en_cours', 'termine']
            if statut == 'refuse':
                actions.append('refuse')
            for a in actions:
                HistoriqueConge.objects.create(
                    conge=c, action=a, fait_par=self.admin, commentaire="")
                n_h += 1
        self._log("Congés", n_c)
        self._log("Historique des congés", n_h)

        n = 0
        for e in employes:
            HistoriqueEmploye.objects.create(
                employe=e, type_changement='creation',
                nouvelle_valeur="Dossier créé", fait_par=self.admin)
            n += 1
            if self.rnd.random() < 0.35:
                HistoriqueEmploye.objects.create(
                    employe=e, type_changement='salaire',
                    ancienne_valeur=str(e.salaire_base),
                    nouvelle_valeur=str(int(e.salaire_base * Decimal('1.1'))),
                    note="Révision annuelle", fait_par=self.admin)
                n += 1
        self._log("Historique employés", n)

        n = 0
        for e in self.rnd.sample(employes, min(30, len(employes))):
            for cle, val in [("Personne à prévenir",
                              f"{self.rnd.choice(NOMS)} — {self._tel()}"),
                             ("Numéro CNPS", str(self.rnd.randint(1000000, 9999999))),
                             ("Banque", self.rnd.choice(
                                 ["SGCI", "BICICI", "NSIA Banque", "Ecobank"]))]:
                InfoSupplementaire.objects.get_or_create(
                    employe=e, cle=cle, defaults={'valeur': val})
                n += 1
        self._log("Informations complémentaires", n)

        n = 0
        for e in Employe.objects.filter(date_fin_contrat__isnull=False,
                                        statut='actif'):
            jours = (e.date_fin_contrat - self.today).days
            if 0 < jours <= 62:
                ech = '1_mois' if jours <= 31 else '2_mois'
                _, cree = AlerteContrat.objects.get_or_create(
                    employe=e, echeance=ech,
                    defaults={'date_fin_contrat': e.date_fin_contrat})
                n += int(cree)
        self._log("Alertes de fin de contrat", n)

    # ═══════════════════════════════════════════════════════════════════
    # 17. Présence
    # ═══════════════════════════════════════════════════════════════════
    def seed_presence(self):
        from employer.models import Employe, Presence
        from presence.models import (AffectationPermanence, PlanningPermanence,
                                     RegistreVerrou)

        employes = list(Employe.objects.filter(statut='actif'))
        n = 0
        for j in range(1 if self.today_only else 45):
            jour = self.today - timedelta(days=j)
            if jour.weekday() >= 5 and self.rnd.random() < 0.7:
                continue
            for e in employes:
                if self.rnd.random() < 0.06:
                    continue  # pas de fiche ce jour-là
                present = self.rnd.random() < 0.9
                kw = {}
                if present:
                    kw = dict(
                        heure_arrivee_matin=time(self.rnd.choice([7, 7, 8]),
                                                 self.rnd.choice([0, 5, 12, 25, 40])),
                        heure_depart_matin=time(12, self.rnd.choice([0, 15, 30])),
                        heure_arrivee_soir=time(self.rnd.choice([13, 14]),
                                                self.rnd.choice([0, 10, 30])),
                        heure_depart_soir=time(self.rnd.choice([16, 17, 18]),
                                               self.rnd.choice([0, 15, 30, 45])),
                    )
                _, cree = Presence.objects.get_or_create(
                    employe=e, date=jour,
                    defaults=dict(present=present,
                                  permanence=self.rnd.random() < 0.08,
                                  motif_absence="" if present else self.rnd.choice(
                                      ["Congé", "Maladie", "Mission",
                                       "Absence injustifiée"]),
                                  **kw))
                n += int(cree)
        self._log("Fiches de présence", n)

        n = 0
        for j in range(0, 28, 7):
            semaine = self.today - timedelta(days=self.today.weekday() + j)
            for type_p in ('personnel', 'medecins'):
                pp, cree = PlanningPermanence.objects.get_or_create(
                    semaine_du=semaine, type_permanence=type_p,
                    defaults={'cree_par': self.admin})
                n += int(cree)
                if cree:
                    for d in range(7):
                        jour = semaine + timedelta(days=d)
                        for e in self.rnd.sample(employes, min(2, len(employes))):
                            # Unicité sur (employé, date) : un même agent ne peut
                            # pas être de permanence deux fois le même jour, quel
                            # que soit le planning (personnel ou médecins).
                            AffectationPermanence.objects.get_or_create(
                                employe=e, date=jour, defaults={'planning': pp})
        self._log("Plannings de permanence", n)

        n = 0
        for j in range(20, 45):
            _, cree = RegistreVerrou.objects.get_or_create(
                date=self.today - timedelta(days=j),
                defaults={'verrouille_par': self.admin})
            n += int(cree)
        self._log("Registres verrouillés", n)

    # ═══════════════════════════════════════════════════════════════════
    # 18. Planning
    # ═══════════════════════════════════════════════════════════════════
    def seed_planning(self):
        from planning.models import (Affectation, GabaritAffectation, Bureau,
                                     LignePermanence, MedecinSignataire,
                                     PlageHoraire, PlanningGabarit,
                                     PlanningHebdomadaire, PlanningModification,
                                     PlanningVu)

        n = 0
        for m in self.medecins[:6]:
            _, cree = MedecinSignataire.objects.get_or_create(
                nom=str(m), defaults={'ordre': n})
            n += int(cree)
        self._log("Médecins signataires", n)

        bureaux = list(Bureau.objects.filter(actif=True))
        if not bureaux:
            for i, nom in enumerate(["Bureau 1", "Bureau 2", "Bureau 3",
                                     "Salle de soins", "Maternité"]):
                bureaux.append(Bureau.objects.create(nom=nom, ordre=i))
            self._log("Bureaux", len(bureaux))
        plages = list(PlageHoraire.objects.all())
        if not plages:
            for b in bureaux:
                for i, code in enumerate(["Matin", "Après-midi", "Garde"]):
                    plages.append(PlageHoraire.objects.create(
                        bureau=b, code=code, ordre=i))
            self._log("Plages horaires", len(plages))

        noms_personnel = [f"{e.nom} {e.prenoms.split()[0]}"
                          for e in self.employes[:25]] or ["Équipe A", "Équipe B"]
        signataires = list(MedecinSignataire.objects.all())

        n_pl = n_af = n_lp = n_vu = n_mod = 0
        lundi = self.today - timedelta(days=self.today.weekday())
        for k in range(-4, 3):
            semaine = lundi + timedelta(weeks=k)
            pl, cree = PlanningHebdomadaire.objects.get_or_create(
                semaine_debut=semaine,
                defaults={'cree_par': self.admin, 'publie': k <= 0,
                          'signataire': self.rnd.choice(signataires)
                          if signataires else None,
                          'note': "Planning hebdomadaire de service."})
            if not cree:
                continue
            n_pl += 1
            for plage in plages:
                for jour in range(6):
                    if self.rnd.random() < 0.45:
                        continue
                    Affectation.objects.get_or_create(
                        planning=pl, plage=plage, jour=jour,
                        defaults={'personnel': self.rnd.choice(noms_personnel),
                                  'note': self.rnd.choice(["", "", "sur appel"])})
                    n_af += 1
            for jour in range(6):
                LignePermanence.objects.get_or_create(
                    planning=pl, jour=jour,
                    defaults={'personnel': self.rnd.choice(noms_personnel)})
                n_lp += 1
            PlanningVu.objects.get_or_create(user=self.admin, planning=pl)
            n_vu += 1
            if self.rnd.random() < 0.4:
                PlanningModification.objects.create(
                    planning=pl, modifie_par=self.admin,
                    resume="Permutation de deux agents sur la garde du vendredi.")
                n_mod += 1
        self._log("Plannings hebdomadaires", n_pl)
        self._log("Affectations", n_af)
        self._log("Lignes de permanence", n_lp)
        self._log("Plannings vus", n_vu)
        self._log("Modifications de planning", n_mod)

        n_g = n_ga = 0
        for nom in ("Gabarit semaine standard", "Gabarit période de garde"):
            g, cree = PlanningGabarit.objects.get_or_create(
                nom=nom, defaults={'cree_par': self.admin})
            if not cree:
                continue
            n_g += 1
            for plage in plages:
                for jour in range(6):
                    if self.rnd.random() < 0.5:
                        continue
                    GabaritAffectation.objects.get_or_create(
                        gabarit=g, plage=plage, jour=jour,
                        defaults={'personnel': self.rnd.choice(noms_personnel)})
                    n_ga += 1
        self._log("Gabarits de planning", n_g)
        self._log("Affectations de gabarit", n_ga)

    # ═══════════════════════════════════════════════════════════════════
    # 19. Maternité
    # ═══════════════════════════════════════════════════════════════════
    def seed_maternite(self):
        from patients.models import Naissance

        femmes = [p for p in self.patients if p.sexe == 'F']
        n = 0
        for _ in range(18 * self.scale):
            mere = self.rnd.choice(femmes)
            sexe = self.rnd.choice(['M', 'F'])
            nom, prenoms = self._nom_prenom(sexe)
            statut = self.rnd.choices(['vivant', 'mort_ne'], weights=[95, 5])[0]
            nb_g = self.rnd.randint(0, 4)
            nb_f = self.rnd.randint(0, 4)
            Naissance.objects.create(
                mere=mere,
                medecin=self.rnd.choice(self.medecins) if self.medecins else None,
                date_accouchement=self._dt(self.rnd.randint(0, 300),
                                           heure=self.rnd.randint(0, 23)),
                lieu_naissance=self.rnd.choice(["CMS Walé Yamoussoukro",
                                                "CMS Walé Toumbokro", "Domicile"]),
                mode_accouchement=self.rnd.choices(
                    ['voie_basse', 'cesarienne', 'forceps', 'ventouse'],
                    weights=[70, 22, 5, 3])[0],
                nom_enfant=mere.nom, prenoms_enfant=prenoms, sexe_enfant=sexe,
                poids_naissance=round(self.rnd.uniform(1.6, 4.4), 2),
                taille_naissance=round(self.rnd.uniform(42, 55), 1),
                groupe_sanguin_enfant=self.rnd.choice(GROUPES_SANGUINS)
                if self.rnd.random() < 0.5 else "",
                taux_hemoglobine=round(self.rnd.uniform(9, 16), 1),
                apgar_1min=self.rnd.randint(4, 10), apgar_5min=self.rnd.randint(7, 10),
                statut=statut,
                education_mere=self.rnd.choice(
                    ['aucun', 'primaire', 'secondaire', 'superieur']),
                age_mere=self.rnd.randint(16, 44),
                parite=nb_g + nb_f, nombre_garcons=nb_g, nombre_filles=nb_f,
                remarques="", statut_dossier=self.rnd.choice(['brouillon', 'termine']),
            )
            n += 1
        self._log("Naissances", n)
