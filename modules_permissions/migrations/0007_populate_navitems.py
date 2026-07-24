from django.db import migrations

# Chaque entrée : (code, label, module_code ou None)
NAV_ITEMS = [
    # Tableau de bord (core)
    ('core.kpi_dashboard', "Vue d'ensemble", None),
    ('core.rapports_link', "Rapports", 'rapports'),

    # Patients
    ('patients.ordonnances', "Ordonnances", 'ordonnances'),
    ('patients.list', "Patients", 'patients'),
    ('patients.rdv', "Rendez-vous", 'rendezvous'),
    ('patients.pathologie_config', "Configurations (Diagnostic retenu)", 'patients'),

    # Médecins
    ('medecins.dashboard', "Tableau de bord", 'medecins'),
    ('medecins.list', "Médecins", 'medecins'),
    ('medecins.config', "Configuration (Spécialités, Départements)", 'medecins'),

    # Consultations
    ('consultations.list', "Consultations", 'consultations'),

    # Pharmacie
    ('pharmacie.dashboard', "Dashboard", 'pharmacie'),
    ('pharmacie.ordonnances', "Ordonnances", 'pharmacie'),
    ('pharmacie.caisse', "Caisse", 'pharmacie'),
    ('pharmacie.stock', "Stock", 'pharmacie'),
    ('pharmacie.livraisons', "Livraisons", 'pharmacie'),
    ('pharmacie.autres_pages', "Autres pages (menu grille)", 'pharmacie'),

    # Laboratoire
    ('laboratoire.list', "Analyses", 'laboratoire'),

    # Hospitalisation
    ('hospitalisation.list', "Hospitalisation", 'hospitalisation'),
    ('hospitalisation.config', "Configuration (Chambres, Décès, Listes de contrôle)", 'hospitalisation'),

    # Facturation
    ('facturation.list', "Factures", 'facturation'),

    # Caisse
    ('caisse.list', "Caisse", 'caisse'),

    # Ressources humaines (employer)
    ('rh.dashboard', "Tableau de bord", 'ressources_humaines'),
    ('rh.employes', "Employés", 'ressources_humaines'),
    ('rh.annuaire', "Annuaire", 'ressources_humaines'),
    ('rh.registre', "Registre", 'ressources_humaines'),
    ('rh.presence', "Présence", 'ressources_humaines'),
    ('rh.config', "Configuration (Grades, Fonctions, Contrats, Nationalités, Services)", 'ressources_humaines'),
    ('rh.import', "Import", 'ressources_humaines'),

    # Achats
    ('achats.dashboard', "Tableau de bord", 'achats'),
    ('achats.fournisseurs', "Fournisseurs", 'achats'),
    ('achats.besoins', "Besoins", 'achats'),
    ('achats.proformas', "Proformas", 'achats'),
    ('achats.commandes', "Commandes", 'achats'),

    # Congés
    ('conges.dashboard', "Tableau de bord", 'conges'),
    ('conges.liste', "Liste des congés", 'conges'),
    ('conges.retours', "Suivi retours", 'conges'),
    ('conges.calendrier', "Calendrier", 'conges'),
    ('conges.plus', "Plus d'options (Soldes, Planning équipe, Rapports, Vue direction, Export)", 'conges'),

    # Gynécologie
    ('gynecologie.patients', "Les patients", 'gynecologie'),
    ('gynecologie.rdv', "Rendez-vous", 'gynecologie'),
    ('gynecologie.naissances', "Registre des naissances", 'gynecologie'),
    ('gynecologie.config', "Configurations (Type de visite)", 'gynecologie'),

    # Planning
    ('planning.dashboard', "Tableau de bord", 'planning'),
    ('planning.liste', "Liste", 'planning'),
    ('planning.mensuel', "Mensuel", 'planning'),
    ('planning.par_medecin', "Par médecin", 'planning'),
    ('planning.stats', "Statistiques", 'planning'),
    ('planning.bureaux', "Bureaux", 'planning'),

    # Présence
    ('presence.registre', "Registre du jour", 'presence'),
    ('presence.recap', "Récap mensuel", 'presence'),
    ('presence.stats', "Statistiques", 'presence'),
    ('presence.rapport', "Rapport", 'presence'),
    ('presence.parametres', "Paramètres", 'presence'),
    ('presence.pointage', "Kiosque pointage", 'presence'),

    # Rapports
    ('rapports.hub', "Rapports", 'rapports'),

    # Services
    ('services.list', "Prestations", 'services'),
    ('services.categories', "Catégories", 'services'),

    # Soins
    ('soins.list', "Soins infirmiers", None),
    ('soins.procedures', "Liste des soins", None),

    # Stock
    ('stock.dashboard', "Tableau de bord", 'stock'),
    ('stock.produits', "Produits", 'stock'),
    ('stock.fiches_besoins', "Fiches besoins", 'stock'),
    ('stock.receptions', "Réceptions achats", 'stock'),
    ('stock.dotation', "Dotation", 'stock'),
    ('stock.config', "Configuration (Type/Catégorie de produit)", 'stock'),
    ('stock.autres_modules', "Autres modules (menu grille)", 'stock'),
]


def populate_navitems(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    NavItem = apps.get_model('modules_permissions', 'NavItem')

    for code, label, module_code in NAV_ITEMS:
        module = None
        if module_code:
            module = Module.objects.filter(code=module_code).first()
        NavItem.objects.get_or_create(
            code=code,
            defaults={'label': label, 'module': module},
        )


def unpopulate_navitems(apps, schema_editor):
    NavItem = apps.get_model('modules_permissions', 'NavItem')
    NavItem.objects.filter(code__in=[c for c, _, _ in NAV_ITEMS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0006_navitem_groupnavitemrestriction_usernavitemoverride'),
    ]

    operations = [
        migrations.RunPython(populate_navitems, unpopulate_navitems),
    ]
