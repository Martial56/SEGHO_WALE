"""Jeu de données de démonstration pour un centre déjà configuré.

Sert à remplir une base de test : du personnel, des médecins, puis des
rendez-vous, des soins et des demandes d'examen répartis sur des milliers de
patients, de quoi éprouver les listes, les filtres, les regroupements et la
pagination sur des volumes réalistes.

Rien de ce qui existe déjà n'est touché. Chaque étape regarde sa table : si
elle est déjà peuplée, l'étape est annoncée comme ignorée et la commande
enchaîne. On peut donc la relancer sur une base à moitié saisie à la main sans
écraser ce qui s'y trouve, et `--forcer-volumes` ne force que les données de
mouvement, jamais le référentiel.

Les enregistrements sont posés par `bulk_create`, ce qui court-circuite les
`save()` des modèles : les numéros (AP…, SN…, DP…, DEM…) sont donc calculés
ici, à partir du dernier posé, exactement comme le feraient ces `save()`.
C'est aussi ce qui évite de déverser des dizaines de milliers de lignes dans
le journal d'activité, qui écoute les signaux `post_save`.
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.middleware import centre_actif

NOMS = [
    'Kouassi', 'Koffi', 'Konan', 'Kouamé', 'Yao', "N'Guessan", 'Aka', 'Assi',
    'Brou', 'Kouadio', 'Traoré', 'Coulibaly', 'Ouattara', 'Diabaté', 'Bamba',
    'Touré', 'Koné', 'Cissé', 'Fofana', 'Doumbia', 'Sangaré', 'Camara',
    'Gnamien', 'Tanoh', 'Ehouman', 'Adjoumani', 'Djédjé', 'Zadi', 'Séri',
    'Loukou', 'Amani', 'Allou', 'Kacou', 'Beugré', 'Gbané', 'Soro', 'Dosso',
]
PRENOMS_M = [
    'Yves', 'Serge', 'Franck', 'Désiré', 'Armand', 'Hervé', 'Olivier',
    'Patrice', 'Ibrahim', 'Moussa', 'Souleymane', 'Abdoulaye', 'Jean-Baptiste',
    'Casimir', 'Félix', 'Landry', 'Wilfried', 'Arsène', 'Cyrille', 'Narcisse',
    'Emmanuel', 'Thierry', 'Boubacar', 'Rodrigue',
]
PRENOMS_F = [
    'Aya', 'Awa', 'Mariam', 'Fatoumata', 'Adjoua', 'Akissi', 'Affoué',
    'Amenan', 'Christelle', 'Nadège', 'Sylvie', 'Prisca', 'Rachelle', 'Carine',
    'Joséphine', 'Clarisse', 'Yolande', 'Bintou', 'Salimata', 'Épiphanie',
    'Georgette', 'Viviane', 'Olga', 'Mireille',
]

# Les fonctions médicales dont découlent les fiches Médecin. Le code SAGE-F
# n'est pas décoratif : medecins.Medecin.titre le lit pour afficher « SF »
# plutôt que « Dr ».
FONCTIONS = [
    ('Directeur',                       'DIR',    'direction',     1),
    ('Directeur adjoint',               'DIR-A',  'direction',     1),
    ('Administrateur',                  'ADMIN',  'direction',     1),
    ('Responsable qualité',             'QUAL',   'direction',     1),
    ('Médecin généraliste',             'MED-G',  'medical',       8),
    ('Médecin spécialiste',             'MED-S',  'medical',       6),
    ('Sage-femme',                      'SAGE-F', 'medical',       6),
    ('Chirurgien-dentiste',             'DENT',   'medical',       1),
    ("Infirmier diplômé d'État",        'IDE',    'paramedical',  12),
    ('Aide-soignant',                   'AS',     'paramedical',   8),
    ('Technicien de laboratoire',       'TECH-L', 'paramedical',   4),
    ('Préparateur en pharmacie',        'PREP-P', 'paramedical',   3),
    ('Manipulateur radio',              'MANIP',  'paramedical',   2),
    ('Kinésithérapeute',                'KINE',   'paramedical',   1),
    ('Caissier',                        'CAIS',   'support',       4),
    ("Agent d'accueil",                 'ACC',    'support',       3),
    ('Comptable',                       'COMPT',  'support',       2),
    ("Agent d'entretien",               'ENTR',   'support',       4),
    ('Agent de sécurité',               'SECU',   'support',       3),
    ('Chauffeur',                       'CHAUF',  'support',       2),
    ('Magasinier',                      'MAGA',   'support',       1),
    ('Agent de santé communautaire',    'ASC',    'communautaire', 2),
    ('Médiateur communautaire',         'MEDIAT', 'communautaire', 1),
]

GRADES = ['Débutant', 'Confirmé', 'Senior', "Chef d'équipe", 'Cadre']

# Fourchettes de salaire mensuel en francs CFA, par catégorie de fonction. Un
# tirage uniforme sur toute l'échelle donnait un agent d'entretien mieux payé
# qu'un médecin, ce qui fausse aussitôt tout test sur la masse salariale.
SALAIRES = {
    'direction':     (600000, 1800000),
    'medical':       (450000, 1500000),
    'paramedical':   (180000,  450000),
    'support':       ( 90000,  300000),
    'communautaire': ( 75000,  180000),
}

TYPES_CONTRAT = [
    ('Contrat à durée indéterminée', 'CDI', True),
    ('Contrat à durée déterminée', 'CDD', True),
    ('Stage', 'STG', True),
    ('Vacataire', 'VAC', False),
    ('Prestataire', 'PREST', False),
]

NATIONALITES = ['Ivoirienne', 'Burkinabè', 'Malienne', 'Guinéenne', 'Béninoise',
                'Sénégalaise', 'Togolaise', 'Nigériane', 'Ghanéenne', 'Française']

SPECIALITES = [
    ('Médecine générale', 'MEDG'), ('Gynécologie-obstétrique', 'GYNO'),
    ('Pédiatrie', 'PEDI'), ('Cardiologie', 'CARD'), ('Dermatologie', 'DERM'),
    ('Ophtalmologie', 'OPHT'), ('Oto-rhino-laryngologie', 'ORL'),
    ('Chirurgie générale', 'CHIR'), ('Radiologie', 'RADI'),
    ('Biologie médicale', 'BIOL'), ('Diabétologie', 'DIAB'),
    ('Gastro-entérologie', 'GAST'), ('Pneumologie', 'PNEU'),
    ('Neurologie', 'NEUR'), ('Urologie', 'URO'), ('Psychiatrie', 'PSY'),
]

SERVICES = [
    ('Accueil', 'ACC'), ('Consultations externes', 'CONS'), ('Urgences', 'URG'),
    ('Maternité', 'MAT'), ('Hospitalisation', 'HOSP'), ('Laboratoire', 'LAB'),
    ('Imagerie médicale', 'IMG'), ('Pharmacie', 'PHAR'),
    ('Bloc opératoire', 'BLOC'), ('Salle de soins', 'SOIN'), ('Caisse', 'CAIS'),
    ('Administration', 'ADM'), ('Ressources humaines', 'RH'),
    ('Maintenance', 'MAINT'),
]

# Un service plausible par fonction, pour que l'annuaire ne soit pas tiré au sort.
SERVICE_PAR_FONCTION = {
    'DIR': 'ADM', 'DIR-A': 'ADM', 'ADMIN': 'ADM', 'QUAL': 'ADM',
    'MED-G': 'CONS', 'MED-S': 'CONS', 'SAGE-F': 'MAT', 'DENT': 'CONS',
    'IDE': 'SOIN', 'AS': 'HOSP', 'TECH-L': 'LAB', 'PREP-P': 'PHAR',
    'MANIP': 'IMG', 'KINE': 'SOIN', 'CAIS': 'CAIS', 'ACC': 'ACC',
    'COMPT': 'ADM', 'ENTR': 'MAINT', 'SECU': 'MAINT', 'CHAUF': 'MAINT',
    'MAGA': 'PHAR', 'ASC': 'ACC', 'MEDIAT': 'ACC',
}

MOTIFS_RDV = [
    'Fièvre depuis trois jours', 'Céphalées persistantes', 'Douleurs abdominales',
    'Toux et gêne respiratoire', 'Contrôle de tension artérielle',
    'Suivi de grossesse', 'Douleurs lombaires', 'Vomissements répétés',
    'Plaie à surveiller', 'Suivi diabétique', 'Asthénie générale',
    'Démangeaisons cutanées', 'Contrôle post-opératoire', 'Bilan annuel',
    'Douleurs articulaires', 'Troubles du sommeil', 'Diarrhée persistante',
    'Vaccination de rappel', 'Consultation de routine', 'Saignements',
]

MOTIFS_SOIN = [
    'Pansement simple', 'Réfection de pansement', 'Injection intramusculaire',
    'Perfusion', 'Pose de sonde', 'Ablation de fils', 'Soins post-opératoires',
    'Prise de constantes', 'Surveillance glycémique', 'Nébulisation',
    'Soins de brûlure', 'Sondage urinaire',
]

OBSERVATIONS_SOIN = [
    'Patient calme, pas de douleur signalée.',
    'Plaie propre, bourgeonnement correct.',
    'Léger écoulement séreux, à revoir dans 48 h.',
    'Patient algique, antalgique administré avant le soin.',
    'Bonne tolérance au produit.',
    'Pansement refait, aucun signe inflammatoire.',
    'Patient informé des consignes de surveillance.',
]


def _sans_accent(texte):
    """Forme utilisable dans une adresse e-mail : sans accent, sans apostrophe."""
    import unicodedata
    plat = unicodedata.normalize('NFKD', texte)
    plat = ''.join(c for c in plat if not unicodedata.combining(c))
    return ''.join(c for c in plat.lower() if c.isalnum())


class Command(BaseCommand):
    help = ("Remplit une base de test : personnel, médecins, rendez-vous, soins "
            "et demandes d'examen. Ne touche à aucune donnée déjà présente.")

    def add_arguments(self, parser):
        parser.add_argument('--rdv', type=int, default=12000,
                            help='Nombre de rendez-vous à créer (défaut 12000).')
        parser.add_argument('--soins', type=int, default=5000,
                            help='Nombre de soins à créer (défaut 5000).')
        parser.add_argument('--demandes', type=int, default=4500,
                            help="Nombre de demandes d'examen à créer (défaut 4500).")
        parser.add_argument('--consultations-facturees', type=int, default=2500,
                            help="Nombre de consultations honorées à facturer (défaut 2500). "
                                 "Les soins et demandes d'examen terminés sont facturés "
                                 "intégralement, eux.")
        parser.add_argument('--patients', type=int, default=15000,
                            help='Taille du vivier de patients concernés (défaut 15000).')
        parser.add_argument('--centre', type=str, default=None,
                            help="Code du centre à peupler (défaut : celui qui porte le plus de patients).")
        parser.add_argument('--graine', type=int, default=2026,
                            help='Graine aléatoire, pour un tirage reproductible.')
        parser.add_argument('--forcer-volumes', action='store_true',
                            help="Ajoute rendez-vous, soins et demandes même si ces tables "
                                 "sont déjà peuplées (le référentiel, lui, n'est jamais retouché).")

    def handle(self, *args, **options):
        from centres.models import Centre
        from patients.models import Patient

        self.alea = random.Random(options['graine'])
        self.forcer = options['forcer_volumes']

        if options['centre']:
            centre = Centre.objects.filter(code=options['centre']).first()
            if centre is None:
                raise CommandError(f"Aucun centre de code « {options['centre']} ».")
        else:
            centre = self._centre_le_plus_peuple()
        self.centre = centre
        self._titre(f'Centre visé : {centre.nom}')

        vivier = list(Patient.all_objects.filter(centre=centre)
                      .order_by('?')
                      .values_list('pk', flat=True)[:options['patients']])
        if not vivier:
            raise CommandError(
                f"Aucun patient dans « {centre.nom} » : importez des patients avant "
                "de générer rendez-vous, soins et demandes.")
        self.patients = vivier
        self._info(f'{len(vivier)} patients tirés comme vivier.')

        # Hors requête, aucun centre n'est actif : les managers cloisonnés
        # (centres.ModeleCentre) renvoient alors le vide, et `soin.procedures`
        # ou `facture.lignes` ne remontent rien — une facture se serait bâtie
        # sur des prestations introuvables. Le gestionnaire de contexte prévu
        # pour les commandes rend le centre actif le temps du traitement.
        with centre_actif(centre):
            self._referentiel_rh()
            self._referentiel_medical()
            employes = self._employes()
            medecins = self._medecins(employes)
            self._rendez_vous(options['rdv'], medecins)
            self._soins(options['soins'], employes)
            self._demandes_examen(options['demandes'], medecins)
            self._facturation(options['consultations_facturees'])
        self._titre('Terminé.')

    # ── Sorties ───────────────────────────────────────────────────────────

    def _titre(self, texte):
        self.stdout.write(self.style.MIGRATE_HEADING(texte))

    def _info(self, texte):
        self.stdout.write(f'  {texte}')

    def _cree(self, texte):
        self.stdout.write(self.style.SUCCESS(f'  + {texte}'))

    def _ignore(self, texte):
        self.stdout.write(self.style.WARNING(f'  = {texte} — déjà présent, laissé tel quel'))

    # ── Outils ────────────────────────────────────────────────────────────

    def _centre_le_plus_peuple(self):
        from django.db.models import Count
        from patients.models import Patient
        ligne = (Patient.all_objects.values('centre')
                 .annotate(n=Count('id')).order_by('-n').first())
        if ligne and ligne['centre']:
            from centres.models import Centre
            return Centre.objects.get(pk=ligne['centre'])
        from centres.models import Centre
        centre = Centre.objects.filter(actif=True).first()
        if centre is None:
            raise CommandError('Aucun centre enregistré.')
        return centre

    def _suite_numeros(self, manager, champ, prefixe, largeur):
        """Rang suivant pour un numéro `prefixe + rang`, lu sur le dernier posé.

        Reproduit ce que fait le `save()` du modèle, que `bulk_create` ne
        déclenche pas. Lu une fois puis incrémenté en mémoire : le relire à
        chaque ligne rendrait la génération quadratique.
        """
        from django.db.models.functions import Length
        dernier = (manager.filter(**{f'{champ}__startswith': prefixe})
                   .order_by(Length(champ).desc(), f'-{champ}')
                   .values_list(champ, flat=True).first())
        rang = 1
        if dernier:
            try:
                rang = int(dernier[len(prefixe):]) + 1
            except ValueError:
                rang = manager.filter(**{f'{champ}__startswith': prefixe}).count() + 1

        def suivant():
            nonlocal rang
            code = f'{prefixe}{rang:0{largeur}d}'
            rang += 1
            return code
        return suivant

    def _moment(self, jour, debut=7, fin=17):
        """Un horodatage ouvré sur ce jour, aligné sur le quart d'heure."""
        heure = self.alea.randint(debut, fin)
        minute = self.alea.choice([0, 15, 30, 45])
        return timezone.make_aware(datetime.combine(jour, time(heure, minute)))

    def _articles(self, categorie):
        from services.models import Articleservice
        actifs = list(Articleservice.objects.filter(categorie__nom=categorie, actif=True))
        return actifs or list(Articleservice.objects.filter(categorie__nom=categorie))

    # ── Référentiels ──────────────────────────────────────────────────────

    def _referentiel_rh(self):
        from employer.models import Fonction, Grade, Nationalite, TypeContrat
        self._titre('Référentiel RH')

        if Nationalite.objects.exists():
            self._ignore('nationalités')
        else:
            Nationalite.objects.bulk_create([Nationalite(nom=n) for n in NATIONALITES])
            self._cree(f'{len(NATIONALITES)} nationalités')

        if Fonction.objects.exists():
            self._ignore('fonctions')
        else:
            Fonction.objects.bulk_create([
                Fonction(nom=nom, code=code, categorie=cat) for nom, code, cat, _ in FONCTIONS])
            self._cree(f'{len(FONCTIONS)} fonctions')

        if Grade.objects.exists():
            self._ignore('grades')
        else:
            Grade.objects.bulk_create([
                Grade(nom=g, code=g[:3].upper()) for g in GRADES])
            self._cree(f'{len(GRADES)} grades')

        if TypeContrat.objects.exists():
            self._ignore('types de contrat')
        else:
            TypeContrat.objects.bulk_create([
                TypeContrat(nom=nom, code=code, droit_au_conge=conge)
                for nom, code, conge in TYPES_CONTRAT])
            self._cree(f'{len(TYPES_CONTRAT)} types de contrat')

    def _referentiel_medical(self):
        from medecins.models import Service, Specialite
        self._titre('Référentiel médical')

        if Specialite.objects.exists():
            self._ignore('spécialités')
        else:
            Specialite.objects.bulk_create([
                Specialite(nom=nom, code=code) for nom, code in SPECIALITES])
            self._cree(f'{len(SPECIALITES)} spécialités')

        if Service.objects.exists():
            self._ignore('services')
        else:
            Service.objects.bulk_create([
                Service(nom=nom, code=code) for nom, code in SERVICES])
            self._cree(f'{len(SERVICES)} services')

    # ── Personnel ─────────────────────────────────────────────────────────

    def _employes(self):
        from employer.models import Employe, Fonction, Grade, Nationalite, TypeContrat
        from medecins.models import Service
        self._titre('Personnel')

        if Employe.objects.exists():
            self._ignore('employés')
            return list(Employe.objects.all())

        fonctions = {f.code: f for f in Fonction.objects.all()}
        services = {s.code: s for s in Service.objects.all()}
        grades = list(Grade.objects.all())
        contrats = list(TypeContrat.objects.all())
        nationalites = list(Nationalite.objects.all())
        ivoirienne = next((n for n in nationalites if n.nom == 'Ivoirienne'), nationalites[0])

        aujourdhui = date.today()

        # Statuts tirés d'une urne plutôt qu'au hasard ligne par ligne : sur un
        # effectif de cette taille, un tirage pondéré laissait régulièrement
        # « suspendu » à zéro, et le filtre par statut n'avait plus rien à
        # montrer — précisément ce qu'on vient tester.
        effectif_total = sum(n for *_, n in FONCTIONS)
        urne_statuts = (['suspendu'] * 3 + ['quitte'] * 6
                        + ['actif'] * (effectif_total - 9))
        self.alea.shuffle(urne_statuts)

        employes, utilises, sequence = [], set(), 1
        for nom_fonction, code, categorie, effectif in FONCTIONS:
            bas, haut = SALAIRES.get(categorie, (90000, 300000))
            for _ in range(effectif):
                sexe = self.alea.choice(['M', 'F'])
                nom = self.alea.choice(NOMS)
                prenoms = self.alea.choice(PRENOMS_M if sexe == 'M' else PRENOMS_F)
                while (nom, prenoms) in utilises:
                    prenoms = self.alea.choice(PRENOMS_M if sexe == 'M' else PRENOMS_F)
                    nom = self.alea.choice(NOMS)
                utilises.add((nom, prenoms))

                embauche = aujourdhui - timedelta(days=self.alea.randint(60, 4800))
                contrat = self.alea.choices(contrats, weights=[6, 3, 1, 2, 1][:len(contrats)])[0]
                # Un CDI n'a pas de fin ; les autres en ont une, parfois déjà passée.
                fin = None
                if contrat.code != 'CDI':
                    fin = embauche + timedelta(days=self.alea.choice([180, 365, 730]))
                statut = urne_statuts.pop()

                employes.append(Employe(
                    matricule=f'{embauche.year:04d}{sequence:03d}{nom[0].upper()}{prenoms[0].upper()}',
                    nom=nom, prenoms=prenoms, sexe=sexe,
                    date_naissance=aujourdhui - timedelta(days=self.alea.randint(8400, 22000)),
                    lieu_naissance=self.alea.choice([
                        'Yamoussoukro', 'Abidjan', 'Bouaké', 'Daloa', 'Korhogo',
                        'San-Pédro', 'Toumodi', 'Dimbokro']),
                    nationalite=self.alea.choices(
                        [ivoirienne] + nationalites, weights=[60] + [2] * len(nationalites))[0],
                    situation_matrimoniale=self.alea.choice(
                        ['celibataire', 'marie', 'marie', 'divorce', 'veuf']),
                    nombre_enfants=self.alea.choices([0, 1, 2, 3, 4, 5], weights=[30, 20, 20, 15, 10, 5])[0],
                    telephone=f'07{self.alea.randint(10000000, 99999999)}',
                    email=f'{_sans_accent(prenoms)}.{_sans_accent(nom)}@wale.ci',
                    adresse=f'Quartier {self.alea.choice(["Habitat", "Millionnaire", "Kokrenou", "N\'Zuessy", "Dioulakro"])}, Yamoussoukro',
                    service=services.get(SERVICE_PAR_FONCTION.get(code, 'ADM')),
                    fonction=fonctions.get(code),
                    grade=self.alea.choice(grades),
                    type_contrat=contrat,
                    date_embauche=embauche,
                    date_fin_contrat=fin,
                    # L'ancienneté pousse le salaire vers le haut de la fourchette.
                    salaire_base=self.alea.randrange(
                        bas, haut + 5000,
                        5000) + min(10, (aujourdhui - embauche).days // 365) * 5000,
                    statut=statut,
                    date_depart=(min(embauche + timedelta(days=self.alea.randint(200, 3000)),
                                     aujourdhui) if statut == 'quitte' else None),
                ))
                sequence += 1

        employes = Employe.objects.bulk_create(employes, batch_size=200)
        self._cree(f'{len(employes)} employés sur {len(FONCTIONS)} fonctions')
        return employes

    def _medecins(self, employes):
        from medecins.models import Departement, Medecin, Service, Specialite
        self._titre('Médecins')

        if Medecin.objects.exists():
            self._ignore('médecins')
            return list(Medecin.objects.select_related('employe').all())

        soignants = [e for e in employes
                     if e.fonction and e.fonction.code in ('MED-G', 'MED-S', 'SAGE-F', 'DENT')]
        if not soignants:
            self._info('aucun employé de fonction médicale — pas de fiche médecin créée')
            return []

        specialites = {s.code: s for s in Specialite.objects.all()}
        services = {s.code: s for s in Service.objects.all()}
        departements = list(Departement.objects.all())
        dep_gyn = next((d for d in departements if 'ynéco' in d.nom), None)
        dep_gen = next((d for d in departements if d is not dep_gyn), None)

        fiches = []
        for i, employe in enumerate(soignants, start=1):
            code_fonction = employe.fonction.code
            if code_fonction == 'SAGE-F':
                specialite, departement, service = specialites.get('GYNO'), dep_gyn or dep_gen, services.get('MAT')
            elif code_fonction == 'MED-G':
                specialite, departement, service = specialites.get('MEDG'), dep_gen or dep_gyn, services.get('CONS')
            elif code_fonction == 'DENT':
                specialite, departement, service = specialites.get('CHIR'), dep_gen or dep_gyn, services.get('CONS')
            else:
                specialite = self.alea.choice([s for c, s in specialites.items()
                                               if c not in ('MEDG', 'GYNO')] or list(specialites.values()))
                departement = dep_gen or dep_gyn
                service = services.get('CONS')

            fiches.append(Medecin(
                employe=employe, specialite=specialite,
                departement=departement, service=service,
                ordre_medecin=f'CI-{2000 + i:04d}',
                taux_honoraire=Decimal(self.alea.randrange(2000, 15000, 500)),
                actif=employe.statut == 'actif',
            ))

        fiches = Medecin.objects.bulk_create(fiches, batch_size=100)
        self._cree(f'{len(fiches)} médecins et sages-femmes')
        return fiches

    # ── Rendez-vous ───────────────────────────────────────────────────────

    def _rendez_vous(self, combien, medecins):
        from patients.models import RendezVous, TypeVisiteCurative
        from gynecologie.models import TypeVisite
        from medecins.models import Departement
        self._titre('Rendez-vous')

        if RendezVous.all_objects.exists() and not self.forcer:
            self._ignore('rendez-vous')
            return
        if not medecins:
            self._info('aucun médecin disponible — rendez-vous non générés')
            return

        consultations = self._articles('Consultations')
        departements = list(Departement.objects.all())
        dep_gyn = next((d for d in departements if 'ynéco' in d.nom), None)
        med_par_dep = {}
        for m in medecins:
            med_par_dep.setdefault(m.departement_id, []).append(m)

        visites_cur = list(TypeVisiteCurative.objects.filter(actif=True))
        visites_cpn = list(TypeVisite.objects.filter(actif=True))
        codes_cpn = [c for c, _ in RendezVous.TYPE_VISITE_CPN]

        numero = self._suite_numeros(RendezVous.all_objects, 'code_rdv', 'AP', 5)
        aujourdhui = date.today()
        lignes = []

        for _ in range(combien):
            # Surtout du passé — c'est là que vivent les historiques — et une
            # queue de rendez-vous à venir pour que l'agenda ne soit pas vide.
            decalage = self.alea.randint(-420, 21)
            jour = aujourdhui + timedelta(days=decalage)
            if jour.weekday() == 6:                      # pas de dimanche
                jour -= timedelta(days=1)

            departement = self.alea.choices(departements, weights=[3 if d is dep_gyn else 7
                                                                   for d in departements])[0]
            candidats = med_par_dep.get(departement.pk) or medecins
            medecin = self.alea.choice(candidats)

            if decalage < -1:
                statut = self.alea.choices(
                    ['termine', 'annule', 'absent'], weights=[82, 10, 8])[0]
            elif decalage <= 0:
                statut = self.alea.choice(['en_attente', 'en_consultation', 'termine'])
            else:
                statut = self.alea.choices(['planifie', 'confirme'], weights=[6, 4])[0]

            debut = self._moment(jour)
            constante = attente = consultation = 0
            if statut == 'termine':
                constante = self.alea.randint(3, 12)
                attente = self.alea.randint(5, 90)
                consultation = self.alea.randint(8, 45)

            est_gyn = departement is dep_gyn
            lignes.append(RendezVous(
                centre=self.centre,
                code_rdv=numero(),
                patient_id=self.alea.choice(self.patients),
                medecin=medecin,
                departement=departement,
                type_consultation=self.alea.choice(consultations) if consultations else None,
                salle_consultation=f'Salle {self.alea.randint(1, 8)}',
                date_heure=debut,
                duree_minutes=constante + attente + consultation,
                type_rdv=self.alea.choices(
                    ['consultation', 'controle', 'urgence', 'examen', 'vaccination'],
                    weights=[60, 18, 9, 8, 5])[0],
                niveau_urgence=self.alea.choices(
                    ['normal', 'urgent', 'tres_urgent'], weights=[85, 12, 3])[0],
                motif=self.alea.choice(MOTIFS_RDV),
                statut=statut,
                temps_constante_minutes=constante,
                temps_attente_minutes=attente,
                temps_consultation_minutes=consultation,
                date_confirme=debut - timedelta(days=1) if statut != 'planifie' else None,
                date_termine=(debut + timedelta(minutes=constante + attente + consultation)
                              if statut == 'termine' else None),
                type_visite_cpn=self.alea.choice(codes_cpn) if est_gyn else '',
                cpn_type_visite=self.alea.choice(visites_cpn) if (est_gyn and visites_cpn) else None,
                cpn_mode_entree=self.alea.choice(
                    ['venu_lui_meme', 'reference_centre', 'refere_tradipraticien']) if est_gyn else '',
                cur_type_visite=self.alea.choice(visites_cur) if (not est_gyn and visites_cur) else None,
                cur_mode_entree=self.alea.choice(
                    ['venu_lui_meme', 'reference_centre']) if not est_gyn else '',
            ))

        RendezVous.all_objects.bulk_create(lignes, batch_size=1000)
        self._cree(f'{len(lignes)} rendez-vous, du {aujourdhui - timedelta(days=420)} au {aujourdhui + timedelta(days=21)}')

    # ── Soins ─────────────────────────────────────────────────────────────

    def _soins(self, combien, employes):
        from patients.models import Pathologie, RendezVous
        from soins.models import ProcedureSoin, Soin
        from medecins.models import Departement
        self._titre('Soins')

        if Soin.all_objects.exists() and not self.forcer:
            self._ignore('soins')
            return

        infirmiers = [e for e in employes
                      if e.fonction and e.fonction.code in ('IDE', 'AS', 'SAGE-F')] or employes
        actes = self._articles('Soins')
        pathologies = list(Pathologie.objects.all()[:200])
        departements = list(Departement.objects.all())
        annee = timezone.now().strftime('%y')

        num_soin = self._suite_numeros(Soin.all_objects, 'numero', f'SN{annee}', 5)
        num_proc = self._suite_numeros(ProcedureSoin.all_objects, 'numero', f'DP{annee}', 5)
        aujourdhui = date.today()

        soins = []
        for _ in range(combien):
            jour = aujourdhui - timedelta(days=self.alea.randint(0, 400))
            # Pas d'« en attente de paiement » : cet état suppose une facture
            # émise et non réglée, or la génération n'en crée aucune. Il
            # laisserait des soins bloqués sur une facture introuvable.
            statut = self.alea.choices(
                ['termine', 'en_cours', 'brouillon', 'annule'],
                weights=[70, 16, 9, 5])[0]
            moment = self._moment(jour, 7, 18)
            soins.append(Soin(
                centre=self.centre,
                numero=num_soin(),
                patient_id=self.alea.choice(self.patients),
                infirmier=self.alea.choice(infirmiers),
                motif=self.alea.choice(MOTIFS_SOIN),
                observations=self.alea.choice(OBSERVATIONS_SOIN),
                statut=statut,
                date_heure=moment,
                departement=self.alea.choice(departements) if departements else None,
                statut_maladie=self.alea.choice(['', 'aigu', 'chronique', 'ameliorant', 'gueri']),
                severite=self.alea.choice(['', 'moderee', 'severe']),
                maladie_infectieuse=self.alea.random() < 0.12,
                maladie_allergique=self.alea.random() < 0.08,
                date_termine=moment + timedelta(minutes=self.alea.randint(10, 120))
                if statut == 'termine' else None,
            ))
        soins = Soin.all_objects.bulk_create(soins, batch_size=1000)
        self._cree(f'{len(soins)} soins')

        # Les procédures portent le détail facturable : un soin en compte une à
        # quatre, prises au catalogue « Soins » avec leur prix de vente.
        rdv_par_patient = {}
        for pk, patient_id in RendezVous.all_objects.filter(
                patient_id__in=self.patients).values_list('pk', 'patient_id')[:40000]:
            rdv_par_patient.setdefault(patient_id, []).append(pk)

        procedures = []
        for soin in soins:
            for _ in range(self.alea.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]):
                acte = self.alea.choice(actes) if actes else None
                rdvs = rdv_par_patient.get(soin.patient_id)
                procedures.append(ProcedureSoin(
                    centre=self.centre,
                    numero=num_proc(),
                    soin=soin,
                    patient_id=soin.patient_id,
                    infirmier=soin.infirmier,
                    soin_type=acte,
                    prix=(acte.prix_vente if acte and acte.prix_vente
                          else Decimal(self.alea.randrange(1000, 25000, 500))),
                    departement=soin.departement,
                    date=soin.date_heure,
                    maladie=self.alea.choice(pathologies) if pathologies and self.alea.random() < 0.6 else None,
                    rendez_vous_id=self.alea.choice(rdvs) if rdvs and self.alea.random() < 0.4 else None,
                    statut={'termine': 'termine', 'annule': 'annule',
                            'en_cours': 'en_cours'}.get(soin.statut, 'brouillon'),
                ))
        ProcedureSoin.all_objects.bulk_create(procedures, batch_size=1000)
        self._cree(f'{len(procedures)} procédures de soin')

    # ── Demandes d'examen ─────────────────────────────────────────────────

    def _demandes_examen(self, combien, medecins):
        from laboratoire.models import DemandeExamen, LigneDemandeExamen
        self._titre("Demandes d'examen")

        if DemandeExamen.all_objects.exists() and not self.forcer:
            self._ignore("demandes d'examen")
            return

        catalogue = []
        for categorie, type_test in [('Examens Biologiques', 'biochimie'),
                                     ('Radiologies', 'imagerie'),
                                     ('Echographies', 'imagerie'),
                                     ('Autres Examens', 'autre')]:
            for article in self._articles(categorie):
                catalogue.append((article, type_test))
        if not catalogue:
            self._info('aucun article d\'examen au catalogue — demandes non générées')
            return

        annee = timezone.now().year
        numero = self._suite_numeros(DemandeExamen.all_objects, 'numero', f'DEM{annee}', 6)
        aujourdhui = date.today()

        demandes, paniers = [], []
        for _ in range(combien):
            panier = self.alea.sample(catalogue, self.alea.choices([1, 2, 3, 4, 5], weights=[30, 28, 20, 14, 8])[0])
            total = sum((a.prix_vente or 0) for a, _ in panier)
            jour = aujourdhui - timedelta(days=self.alea.randint(0, 400))
            moment = self._moment(jour, 7, 16)
            demandes.append(DemandeExamen(
                centre=self.centre,
                numero=numero(),
                patient_id=self.alea.choice(self.patients),
                type_test=self.alea.choice([t for _, t in panier]),
                statut=self.alea.choices(
                    ['termine', 'en_cours', 'accepte', 'demande', 'brouillon'],
                    weights=[55, 15, 12, 12, 6])[0],
                date_prelevement=moment,
                medecin_prescripteur=self.alea.choice(medecins) if medecins else None,
                urgent=self.alea.random() < 0.15,
                montant_total=total,
                commentaire=self.alea.choice([
                    '', '', 'À jeun.', 'Prélèvement du matin.',
                    'Patient sous traitement antibiotique.', 'Contrôle après traitement.']),
            ))
            paniers.append(panier)

        demandes = DemandeExamen.all_objects.bulk_create(demandes, batch_size=1000)

        lignes = []
        for demande, panier in zip(demandes, paniers):
            for article, _type_test in panier:
                lignes.append(LigneDemandeExamen(
                    demande=demande, article_service=article,
                    libelle=article.nom, prix=article.prix_vente or 0,
                    origine=self.alea.choices(['medecin', 'caisse'], weights=[85, 15])[0],
                ))
        LigneDemandeExamen.objects.bulk_create(lignes, batch_size=1000)
        self._cree(f'{len(demandes)} demandes et {len(lignes)} lignes d\'examen')

    # ── Facturation ───────────────────────────────────────────────────────

    def _facturation(self, consultations_a_facturer):
        """Facture ce qui est terminé et encaisse, sans rien laisser en suspens.

        Trois sources alimentent la caisse : les soins terminés, les demandes
        d'examen terminées et une part des consultations honorées. Chacune
        donne une facture, ses lignes, et le paiement qui la solde — un soin
        rendu et jamais facturé est aussi faux qu'une facture sans prestation.

        Seul ce qui n'est pas déjà rattaché à une facture est repris : la
        commande peut donc tourner après coup sur un jeu déjà généré.
        """
        from facturation.models import Caisse, Facture, LigneFacture, Paiement
        from django.contrib.auth.models import User
        from laboratoire.models import DemandeExamen, LigneDemandeExamen
        from patients.models import RendezVous
        from soins.models import ProcedureSoin, Soin
        self._titre('Facturation')

        if Facture.all_objects.exists() and not self.forcer:
            self._ignore('factures')
            return

        caisses = list(Caisse.objects.filter(actif=True)) or list(Caisse.objects.all())
        if not caisses:
            self._info('aucune caisse enregistrée — facturation non générée')
            return
        encaisseurs = list(User.objects.all())

        annee = timezone.now().year
        # Le numéro reprend le format du modèle, mais daté du jour de la facture
        # plutôt que du jour de la génération : une facture d'octobre 2025 ne
        # peut pas porter la date d'aujourd'hui dans son propre numéro.
        rangs_du_jour = {}

        def numero_facture(moment):
            jour = moment.strftime('%y%m%d')
            rangs_du_jour[jour] = rangs_du_jour.get(jour, 0) + 1
            return f'VTES/{moment.year}/{jour}{rangs_du_jour[jour]:04d}'

        suite_paiement = self._suite_numeros(Paiement.all_objects, 'numero', f'PAI{annee}', 7)

        factures, lignes_prevues, liens = [], [], []

        # 1. Les soins terminés, détaillés par leurs procédures.
        soins = list(Soin.all_objects.filter(statut='termine', facture__isnull=True)
                     .prefetch_related('procedures'))
        for soin in soins:
            procedures = list(soin.procedures.all())
            if not procedures:
                continue
            total = sum((p.prix or 0) for p in procedures)
            if not total:
                continue
            facture = Facture(
                centre=self.centre, numero=numero_facture(soin.date_heure),
                patient_id=soin.patient_id, type_facture='soins',
                montant_total=total, montant_paye=total, statut='payee',
                cree_par=self.alea.choice(encaisseurs) if encaisseurs else None,
            )
            factures.append(facture)
            lignes_prevues.append([
                dict(article=p.soin_type, libelle=(p.soin_type.nom if p.soin_type else 'Soin'),
                     prix_unitaire=p.prix or 0)
                for p in procedures])
            liens.append(('soin', soin, procedures, soin.date_heure))

        # 2. Les demandes d'examen terminées, ligne à ligne.
        demandes = list(DemandeExamen.all_objects.filter(statut='termine', facture__isnull=True)
                        .prefetch_related('lignes'))
        for demande in demandes:
            lignes_demande = list(demande.lignes.all())
            total = sum((l.prix or 0) for l in lignes_demande)
            if not lignes_demande or not total:
                continue
            moment = demande.date_prelevement or demande.date_creation
            facture = Facture(
                centre=self.centre, numero=numero_facture(moment),
                patient_id=demande.patient_id,
                type_facture='imagerie' if demande.type_test == 'imagerie' else 'laboratoire',
                montant_total=total, montant_paye=total, statut='payee',
                cree_par=self.alea.choice(encaisseurs) if encaisseurs else None,
            )
            factures.append(facture)
            lignes_prevues.append([
                dict(article=l.article_service, libelle=l.libelle or 'Examen',
                     prix_unitaire=l.prix or 0, ligne_demande_examen=l)
                for l in lignes_demande])
            liens.append(('demande', demande, lignes_demande, moment))

        # 3. Une part des consultations honorées. Quelques-unes sont annulées —
        #    une facture annulée est close, elle n'attend aucun règlement.
        rdvs = list(RendezVous.all_objects
                    .filter(statut='termine', type_consultation__isnull=False, factures__isnull=True)
                    .select_related('type_consultation')
                    .order_by('?')[:consultations_a_facturer])
        for rdv in rdvs:
            prix = rdv.type_consultation.prix_vente or 0
            if not prix:
                continue
            annulee = self.alea.random() < 0.03
            facture = Facture(
                centre=self.centre, numero=numero_facture(rdv.date_heure),
                patient_id=rdv.patient_id, rendez_vous=rdv, type_facture='consultation',
                montant_total=prix, montant_paye=0 if annulee else prix,
                statut='annulee' if annulee else 'payee',
                notes='Facture annulée et réémise.' if annulee else '',
                cree_par=self.alea.choice(encaisseurs) if encaisseurs else None,
            )
            factures.append(facture)
            lignes_prevues.append([
                dict(article=rdv.type_consultation, libelle=rdv.type_consultation.nom,
                     prix_unitaire=prix)])
            liens.append(('rdv', rdv, None, rdv.date_heure))

        if not factures:
            self._info('rien à facturer — soins, demandes et consultations déjà rattachés')
            return

        factures = Facture.all_objects.bulk_create(factures, batch_size=1000)

        # date_emission est un auto_now_add : bulk_create l'a posée à maintenant.
        # On la ramène à la date de la prestation, sans quoi tout le chiffre
        # d'affaires de l'année tomberait sur aujourd'hui.
        for facture, (_genre, _objet, _detail, moment) in zip(factures, liens):
            facture.date_emission = moment
        Facture.all_objects.bulk_update(factures, ['date_emission'], batch_size=1000)

        lignes = []
        for facture, champs in zip(factures, lignes_prevues):
            for ligne in champs:
                lignes.append(LigneFacture(facture=facture, quantite=1, **ligne))
        LigneFacture.objects.bulk_create(lignes, batch_size=1000)

        # Les prestations pointent vers leur facture.
        soins_lies, procedures_liees, demandes_liees = [], [], []
        for facture, (genre, objet, detail, _moment) in zip(factures, liens):
            if genre == 'soin':
                objet.facture = facture
                soins_lies.append(objet)
                for procedure in detail:
                    procedure.facture = facture
                    procedures_liees.append(procedure)
            elif genre == 'demande':
                objet.facture = facture
                demandes_liees.append(objet)
        if soins_lies:
            Soin.all_objects.bulk_update(soins_lies, ['facture'], batch_size=1000)
        if procedures_liees:
            ProcedureSoin.all_objects.bulk_update(procedures_liees, ['facture'], batch_size=1000)
        if demandes_liees:
            DemandeExamen.all_objects.bulk_update(demandes_liees, ['facture'], batch_size=1000)

        # Le règlement, pour toute facture qui n'est pas annulée.
        modes = ['especes', 'mobile_money', 'virement', 'cheque', 'bon']
        poids = [55, 30, 8, 5, 2]
        paiements = []
        for facture, (_genre, _objet, _detail, moment) in zip(factures, liens):
            if facture.statut != 'payee':
                continue
            caisse = self.alea.choices(caisses, weights=[7] + [3] * (len(caisses) - 1))[0]
            acceptes = [m for m in modes if m in caisse.modes_paiement] or ['especes']
            mode = self.alea.choices(
                acceptes, weights=[poids[modes.index(m)] for m in acceptes])[0]
            # En espèces, le patient tend un billet : on note ce qu'il a donné,
            # arrondi au millier supérieur, pour que la monnaie rendue ait un sens.
            recu = None
            if mode == 'especes':
                montant = int(facture.montant_total)
                recu = Decimal(((montant + 999) // 1000) * 1000)
            paiements.append(Paiement(
                centre=self.centre, numero=suite_paiement(), facture=facture,
                montant=facture.montant_total, mode_paiement=mode, caisse=caisse,
                montant_recu=recu,
                reference='' if mode == 'especes' else f'{mode[:3].upper()}-{self.alea.randint(100000, 999999)}',
                recu_par=self.alea.choice(encaisseurs) if encaisseurs else None,
            ))
        paiements = Paiement.all_objects.bulk_create(paiements, batch_size=1000)

        regles = [f for f in factures if f.statut == 'payee']
        for paiement, facture in zip(paiements, regles):
            paiement.date_paiement = facture.date_emission + timedelta(minutes=self.alea.randint(2, 45))
        Paiement.all_objects.bulk_update(paiements, ['date_paiement'], batch_size=1000)

        annulees = len(factures) - len(regles)
        self._cree(f'{len(factures)} factures ({len(lignes)} lignes) — '
                   f'{len(regles)} payées, {annulees} annulées')
        self._cree(f'{len(paiements)} paiements encaissés')
