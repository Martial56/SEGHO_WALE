from django.db import migrations

# Achats et Stock sont devenus deux modules totalement indépendants (chacun
# son propre Fournisseur, Achats a son propre catalogue d'Articles) ; Stock a
# gagné un stock initial à la création d'un produit et un bouton Réception ;
# Pharmacie vérifie désormais la péremption sur les lots propres à chaque
# pharmacie plutôt que sur le stock central, et la Recette compte aussi les
# ordonnances facturées. Met à jour les articles du guide en conséquence.

MISES_A_JOUR = {
    'stock': {
        "Mode d'emploi": (
            "Depuis Stock → Produits, cliquez sur « + Créer ».\n"
            "1. Nom du produit (obligatoire).\n"
            "2. Type : Médicament, Consommable médical, ou Équipement & matériel.\n"
            "3. Catégorie : optionnelle — si elle n'existe pas encore, tapez son nom, elle sera créée "
            "automatiquement à l'enregistrement.\n"
            "4. Unité de mesure : choisissez dans la liste (cp, boîte, flacon...).\n"
            "5. Fournisseur principal : optionnel.\n"
            "6. Si ce produit existe déjà physiquement en stock, renseignez son « N° de lot » et sa "
            "« Quantité initiale » — un lot et un mouvement d'entrée sont créés automatiquement. Un "
            "numéro de lot déjà utilisé par un autre produit est refusé.\n"
            "7. Le code produit se génère automatiquement (ex. MED20260012) — rien à saisir.\n"
            "8. Cliquez sur « Enregistrer ».\n\n"
            "Exemple : Nom « Paracétamol 500mg », Type « Médicament », Catégorie « Antalgiques », "
            "Unité « cp », N° de lot « LOT-2026-014 », Quantité initiale « 200 ».\n\n"
            "Pour importer plusieurs produits d'un coup : Stock → Produits → « Export/Import » → "
            "téléchargez le modèle, remplissez une ligne par produit (code, nom, type, catégorie, "
            "unité, prix d'achat, prix de vente...), puis réimportez le fichier.\n\n"
            "Pour réapprovisionner un produit déjà créé (livraison reçue hors commande) : Stock → "
            "Produits → « Réception » → saisissez les quantités reçues par produit, avec lot et date "
            "de péremption."
        ),
        "Bon à savoir": (
            "La méthode FEFO (premier périmé, premier sorti) prime sur l'ordre d'arrivée : un lot "
            "plus récent mais périmant plus tôt sera proposé avant un lot plus ancien à péremption "
            "plus lointaine.\n\n"
            "Un inventaire non validé ne modifie pas le stock théorique — c'est la validation qui "
            "applique réellement les écarts constatés.\n\n"
            "Le fournisseur est optionnel partout dans Stock (produit, lot, commande, réception) — "
            "Stock gère son propre carnet de fournisseurs, indépendant de celui du module Achats.\n\n"
            "Une fiche de besoins suit son propre cycle, entièrement dans Stock : brouillon → soumise "
            "pour validation → validée ou rejetée par un responsable (qui peut ajuster les quantités "
            "accordées). Elle ne dépend plus du module Achats."
        ),
    },
    'achats': {
        "Vue d'ensemble": (
            "Le module Achats gère ses propres fournisseurs et son propre catalogue d'articles, et "
            "suit les commandes passées auprès d'eux, du brouillon jusqu'à la réception.\n\n"
            "Chaque commande suit un statut (brouillon, envoyé, reçu) qui reflète son avancement réel "
            "auprès du fournisseur.\n\n"
            "Achats fonctionne de façon totalement indépendante du module Stock : fournisseurs, "
            "catalogue d'articles et réceptions n'alimentent pas automatiquement le stock du centre."
        ),
        "Bon à savoir": (
            "La réception d'une commande n'alimente pas automatiquement le stock du module Stock — "
            "Achats et Stock fonctionnent de façon indépendante. Pour faire entrer physiquement une "
            "livraison dans le stock du centre, utilisez le bouton « Réception » du module Stock "
            "(Stock → Produits → Réception)."
        ),
        "Mode d'emploi": (
            "Depuis Achats → Besoins, cliquez sur « + Nouveau besoin ».\n"
            "1. Titre du besoin (obligatoire), Date de livraison souhaitée.\n"
            "2. Ajoutez une ou plusieurs lignes : Article du catalogue d'Achats (ou désignation libre "
            "si hors catalogue), Quantité, Unité.\n"
            "3. Cliquez sur « Créer », puis « Soumettre » depuis la fiche pour le faire valider.\n\n"
            "Exemple : Titre « Réapprovisionnement médicaments novembre 2026 », Article « Ibuprofen », "
            "Quantité « 200 », Unité « boîte ».\n\n"
            "Un besoin validé se transforme ensuite en Proforma (devis fournisseur, à valider ou "
            "rejeter), puis en Commande d'achat une fois le proforma validé, puis en Réception à "
            "l'arrivée de la livraison — chaque étape a son propre numéro (BAC..., PRF..., CAC..., "
            "REC...) et son propre statut. Le catalogue d'Articles et le carnet de Fournisseurs sont "
            "propres à Achats, distincts de ceux du module Stock."
        ),
    },
    'pharmacie': {
        "Bon à savoir": (
            "Un produit suivi par lots dont tous les lots de CETTE pharmacie sont périmés ou épuisés "
            "est bloqué à la vente et à la dispensation, même si sa fiche indique encore une quantité "
            "théorique : le blocage se base sur les lots réellement reçus par cette pharmacie, pas sur "
            "le stock du dépôt central.\n\n"
            "Le journal des mouvements retrace chaque entrée, dispensation, ajustement ou transfert, "
            "avec la quantité avant et après chaque opération — un bon point de départ en cas d'écart "
            "constaté.\n\n"
            "Les rapports de recette (jour, mois, tableau de bord) comptent à la fois les ventes au "
            "comptoir et les ordonnances facturées et payées en caisse — les deux sources sont "
            "toujours affichées séparément en plus du total."
        ),
    },
}


def mettre_a_jour(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideArticle = apps.get_model('guide', 'GuideArticle')
    for code, articles in MISES_A_JOUR.items():
        try:
            categorie = GuideCategorie.objects.get(code=code)
        except GuideCategorie.DoesNotExist:
            continue
        for titre, contenu in articles.items():
            GuideArticle.objects.filter(categorie=categorie, titre=titre).update(contenu=contenu)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('guide', '0007_articles_mode_emploi'),
    ]

    operations = [
        migrations.RunPython(mettre_a_jour, noop_reverse),
    ]
