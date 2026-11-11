from django.db import migrations

# La page d'accueil a été refaite : bandeau avec date, salutation et recherche,
# modules illustrés chacun par une image, vue « Icônes » ou « Liste », chiffres
# rafraîchis toutes les 30 secondes. La rubrique « Prise en main » décrivait
# encore l'ancienne grille ; elle plaçait aussi le changement de thème et le
# verrouillage dans le menu du profil, qui ne contient que « Centre actif »,
# « Mon compte » et « Déconnexion ».

MISES_A_JOUR = {
    'demarrage': {
        "Vue d'ensemble": (
            "SEGHO-WALE est le système de gestion du Centre Médico-Social WALÉ. Après connexion avec "
            "votre identifiant et votre mot de passe, vous arrivez sur la page d'accueil : un bandeau "
            "vert avec la date du jour, une salutation à votre nom et un champ de recherche, puis la "
            "grille des modules. Chaque module est représenté par une image et correspond à un domaine "
            "de l'activité du centre (patients, pharmacie, hospitalisation, caisse...).\n\n"
            "Seuls les modules auxquels votre compte a été autorisé apparaissent : deux comptes (un "
            "médecin et un caissier, par exemple) peuvent donc voir des pages d'accueil très "
            "différentes. Chaque module s'ouvre dans son propre espace, avec sa barre de navigation et "
            "ses propres écrans (listes, fiches, formulaires).\n\n"
            "Sous le nom de chaque module, une ligne donne un repère chiffré quand il y en a un "
            "(patients enregistrés, rendez-vous du jour, analyses en attente, factures impayées...). "
            "Ces chiffres se mettent à jour d'eux-mêmes toutes les 30 secondes, sans recharger la page."
        ),
        "Actions courantes": (
            "• Connectez-vous avec l'identifiant et le mot de passe fournis par un administrateur.\n"
            "• Sur la page d'accueil, cliquez sur un module pour l'ouvrir.\n"
            "• Pour trouver un module rapidement, tapez une partie de son nom dans le champ de "
            "recherche : la grille ne garde que les modules correspondants, et Entrée ouvre le premier.\n"
            "• Le sélecteur « Vue », au-dessus de la grille, bascule entre « Icônes » (grandes images) "
            "et « Liste » (lignes compactes, plus de modules visibles d'un coup).\n"
            "• Depuis n'importe quel module, l'icône en grille de points (à gauche de la barre du "
            "module) ou le logo SEGHO-WALE en haut à gauche ramène à la page d'accueil.\n"
            "• Le bouton soleil/lune de la barre du haut bascule entre thème clair et sombre ; le menu "
            "de votre profil (en haut à droite) donne accès à « Mon compte » et à la déconnexion."
        ),
        "Bon à savoir": (
            "Une pastille rouge (ou orange) sur un module signale du travail qui vous attend : "
            "hospitalisations à traiter sur Meo, soins à facturer ou à administrer sur Soins, factures "
            "à encaisser sur Caisse, produits sous le seuil d'alerte sur Pharmacie, plannings pas "
            "encore consultés sur Planning. Cliquer sur ce module ouvre directement la liste déjà "
            "filtrée sur ce que la pastille a compté. Sans rien en attente, la pastille disparaît.\n\n"
            "La recherche ne tient pas compte des accents ni des majuscules, et reconnaît quelques mots "
            "en plus du nom du module : « rdv » trouve Rendez-vous, « hospitalisation » trouve Meo, "
            "« médicaments » trouve Pharmacie. Raccourcis : Ctrl+K place le curseur dans la recherche, "
            "Échap la vide.\n\n"
            "Le choix « Icônes » ou « Liste » est retenu par le navigateur : il s'applique à chaque "
            "retour sur la page d'accueil depuis ce poste.\n\n"
            "Le module « Tableau de bord » n'est pas la page d'accueil : il regroupe les statistiques "
            "et indicateurs du centre.\n\n"
            "Après un délai d'inactivité configurable (réglable dans « Mon compte »), la session se "
            "verrouille automatiquement par sécurité : un simple mot de passe suffit à la déverrouiller, "
            "sans perdre la page en cours ni devoir se reconnecter entièrement.\n\n"
            "Si un module ou un lien vous semble manquant, ce n'est pas une erreur technique la plupart "
            "du temps : seul un administrateur peut accorder l'accès à un module ou à un élément de menu "
            "précis, groupe par groupe ou utilisateur par utilisateur."
        ),
        "Mode d'emploi": (
            "La barre du haut donne accès à :\n"
            "• La cloche de notifications — alertes stock, factures impayées, analyses en attente, "
            "congés à traiter...\n"
            "• Le bouton soleil/lune — thème clair ou sombre.\n"
            "• Votre profil (en haut à droite) : si vous avez accès à plusieurs centres, un menu "
            "« Centre actif » permet de basculer de l'un à l'autre (sinon le centre est choisi "
            "automatiquement). « Mon compte » et « Déconnexion » sont dans ce même menu.\n\n"
            "Sur la page d'accueil :\n"
            "1. Repérez le module voulu dans la grille, ou tapez son nom dans le champ de recherche du "
            "bandeau vert (Ctrl+K pour y aller directement).\n"
            "2. Cliquez sur le module (ou appuyez sur Entrée dans la recherche) pour l'ouvrir.\n"
            "3. Au besoin, passez en vue « Liste » avec le sélecteur « Vue » pour voir tous vos "
            "modules sur un seul écran.\n\n"
            "Chaque module a ensuite son propre sous-menu, affiché juste sous la barre du haut. Pour "
            "revenir à la page d'accueil, cliquez sur l'icône en grille de points de ce sous-menu ou "
            "sur le logo en haut à gauche."
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
        ('guide', '0008_independance_achats_stock'),
    ]

    operations = [
        migrations.RunPython(mettre_a_jour, noop_reverse),
    ]
