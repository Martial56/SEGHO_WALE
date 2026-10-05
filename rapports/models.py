from django.contrib.auth.models import User
from django.db import models


class HistoriqueRapport(models.Model):
    FORMAT = [('xlsx', 'Excel'), ('csv', 'CSV')]

    slug = models.CharField(max_length=50, verbose_name="Rapport")
    nom = models.CharField(max_length=150, verbose_name="Nom du rapport")
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='rapports_generes')
    periode_debut = models.DateField(null=True, blank=True, verbose_name="Période — début")
    periode_fin = models.DateField(verbose_name="Période — fin")
    format_fichier = models.CharField(max_length=10, choices=FORMAT)
    nb_lignes = models.PositiveIntegerField(default=0)
    fichier = models.FileField(upload_to='rapports/%Y/%m/', null=True, blank=True)
    date_generation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} — {self.utilisateur} ({self.date_generation:%d/%m/%Y %H:%M})"

    class Meta:
        verbose_name = "Rapport généré"
        verbose_name_plural = "Historique des rapports"
        ordering = ['-date_generation']


# ─────────────────────────────────────────────────────────────────────────────
# Fiche d'activité de soins : la composition des deux colonnes de soins vivait
# dans deux constantes de `rapports/soins.py`, qui désignaient les prestations
# **par leur nom**. Renommer un article dans le catalogue faisait tomber la
# ligne à zéro sans un mot ; ajouter une prestation la faisait disparaître de
# la fiche. Ces deux pannes se sont produites et n'ont été vues qu'en relisant
# la fiche ligne à ligne.
#
# La composition passe donc en base, et les prestations sont désignées par
# **clé étrangère** : un renommage ne casse plus rien, une suppression devient
# visible. L'écran de configuration n'est que la conséquence de ce choix — une
# fois la fiche en base, il faut bien un endroit pour la régler.
# ─────────────────────────────────────────────────────────────────────────────


class ConfigurationFicheSoins(models.Model):
    """Une composition complète de la fiche : ses blocs, leurs lignes.

    Trois rôles, distingués par deux drapeaux plutôt que par trois modèles :

    * `est_defaut` — **la** configuration officielle, livrée par migration de
      semis, sans propriétaire. Seuls les superutilisateurs la modifient, et
      « revenir au format par défaut » y ramène. C'est ce qui garantit que ce
      bouton veut encore dire quelque chose après trois ans de réglages.
    * `est_active` — celle que son propriétaire voit quand il ouvre la fiche.
      Une seule par compte.
    * ni l'un ni l'autre — une configuration mise de côté sous un nom, qu'on
      peut reprendre plus tard ou proposer à quelqu'un d'autre.

    Appliquer celle d'un collègue la **copie** : si elle restait partagée, le
    jour où il la modifie, la fiche de l'autre changerait sans que personne
    n'ait rien fait.
    """

    nom = models.CharField(max_length=120, verbose_name="Nom")
    utilisateur = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='configurations_fiche_soins', verbose_name="Propriétaire")
    est_defaut = models.BooleanField(
        default=False, verbose_name="Configuration par défaut")
    est_active = models.BooleanField(
        default=False, verbose_name="Active pour ce compte")
    partagee = models.BooleanField(
        default=False, verbose_name="Proposée aux autres utilisateurs")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    @classmethod
    def officielle(cls):
        """La configuration par défaut, ou None si le semis n'a pas tourné."""
        return cls.objects.filter(est_defaut=True).first()

    @classmethod
    def pour(cls, utilisateur):
        """Celle qu'il faut appliquer en ouvrant la fiche pour quelqu'un.

        La sienne si elle existe, sinon l'officielle. Tant que personne n'a
        rien réglé, tout le monde voit la même fiche — celle d'avant.
        """
        if utilisateur is not None and utilisateur.is_authenticated:
            sienne = cls.objects.filter(
                utilisateur=utilisateur, est_active=True).first()
            if sienne is not None:
                return sienne
        return cls.officielle()

    @classmethod
    def visibles_par(cls, utilisateur):
        """Les configurations qu'une personne a le droit d'ouvrir.

        Les siennes, le format par défaut, et celles que d'autres proposent.
        C'est le seul endroit qui en décide : une vue qui accepte un numéro de
        configuration venu de l'URL doit le passer par là, sinon il suffirait
        de changer un chiffre dans l'adresse pour lire la fiche de n'importe
        qui.
        """
        from django.db.models import Q
        if utilisateur is None or not utilisateur.is_authenticated:
            return cls.objects.filter(est_defaut=True)
        return cls.objects.filter(
            Q(utilisateur=utilisateur) | Q(est_defaut=True) | Q(partagee=True))

    @property
    def auteur(self):
        """Qui l'a faite, en une ligne lisible sur un écran ou une impression."""
        if self.est_defaut:
            return "format par défaut"
        if self.utilisateur is None:
            return "auteur inconnu"
        nom = self.utilisateur.get_full_name().strip()
        return nom or self.utilisateur.get_username()

    def dupliquer(self, utilisateur, nom=None, est_active=False):
        """Une copie complète, posée sur un autre compte.

        C'est l'opération centrale du dispositif, et elle **copie** au lieu de
        pointer. Si la configuration d'un utilisateur restait liée à celle dont
        elle vient, le jour où l'original change, sa fiche changerait sans
        qu'il ait rien fait — et le format officiel ne pourrait plus être
        retouché sans déranger tout le monde.
        """
        copie = ConfigurationFicheSoins.objects.create(
            nom=nom or self.nom, utilisateur=utilisateur,
            est_active=est_active)
        for bloc in self.blocs.prefetch_related('colonnes', 'lignes__articles'):
            copie_bloc = BlocFicheSoins.objects.create(
                configuration=copie, titre=bloc.titre, ordre=bloc.ordre)
            for colonne in bloc.colonnes.all():
                ColonneFicheSoins.objects.create(
                    bloc=copie_bloc, titre=colonne.titre,
                    type_valeur=colonne.type_valeur, ordre=colonne.ordre)
            for ligne in bloc.lignes.all():
                copie_ligne = LigneFicheSoins.objects.create(
                    bloc=copie_bloc, libelle=ligne.libelle, ordre=ligne.ordre,
                    source=ligne.source, origines=ligne.origines)
                copie_ligne.articles.set(ligne.articles.all())
        return copie

    def __str__(self):
        if self.est_defaut:
            return f"{self.nom} (par défaut)"
        return f"{self.nom} — {self.utilisateur or 'sans propriétaire'}"

    class Meta:
        verbose_name = "Configuration de la fiche de soins"
        verbose_name_plural = "Configurations de la fiche de soins"
        ordering = ['-est_defaut', 'nom']


class BlocFicheSoins(models.Model):
    """Un bloc de la fiche : un titre et des lignes.

    Les deux blocs livrés sont « Soins » et « Autres soins à préciser ». Ils
    s'impriment côte à côte, deux par rangée, comme sur la feuille d'origine.
    """

    configuration = models.ForeignKey(
        ConfigurationFicheSoins, on_delete=models.CASCADE,
        related_name='blocs', verbose_name="Configuration")
    titre = models.CharField(max_length=120, verbose_name="Titre")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")

    def __str__(self):
        return self.titre

    class Meta:
        verbose_name = "Bloc de la fiche de soins"
        verbose_name_plural = "Blocs de la fiche de soins"
        ordering = ['ordre', 'id']


class ColonneFicheSoins(models.Model):
    """Une colonne de valeurs d'un bloc.

    Il n'en existe qu'un type aujourd'hui, « Nombre » : un simple compte, et
    chaque bloc n'en porte qu'une — ce qui est exactement la fiche actuelle.

    Le modèle existe quand même, parce que c'est lui qui permettra plus tard de
    croiser une ligne par sexe ou par tranche d'âge sans rien réécrire : il
    suffira d'ajouter un type et de dire ce qu'il découpe. Une colonne n'est
    pas un libellé libre — c'est un découpage, et un découpage doit savoir se
    traduire en requête, donc être déclaré dans le code.
    """

    TYPE_VALEUR = [('nombre', 'Nombre')]

    bloc = models.ForeignKey(
        BlocFicheSoins, on_delete=models.CASCADE,
        related_name='colonnes', verbose_name="Bloc")
    titre = models.CharField(max_length=60, default='Nombre',
                             verbose_name="Titre")
    type_valeur = models.CharField(
        max_length=20, choices=TYPE_VALEUR, default='nombre',
        verbose_name="Type de valeur")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")

    def __str__(self):
        return self.titre

    class Meta:
        verbose_name = "Colonne de la fiche de soins"
        verbose_name_plural = "Colonnes de la fiche de soins"
        ordering = ['ordre', 'id']


class LigneFicheSoins(models.Model):
    """Une ligne de la fiche : un libellé, et de quoi calculer son nombre.

    Deux axes **séparés**, et c'est volontaire :

    * `source` dit **ce qu'on compte**. Des prestations cochées pour presque
      toutes les lignes ; des mises en observation pour PERFUSION et « Mise en
      Observation simple », qui ne comptent pas d'article du tout. Les forcer
      dans le même moule que les autres reperdrait ce qu'on vient de corriger.
    * `origines` dit **où on les cherche** : le module Soins, la mise en
      observation, ou les deux. C'est l'axe qui manquait : une nébulisation
      posée pendant une mise en observation était facturée, payée, et comptée
      nulle part.

    `manuelle` est la case laissée blanche à remplir à la main. Sans elle, une
    ligne sans prestation cochée afficherait zéro — un chiffre faux — au lieu
    d'un blanc qui demande qu'on le remplisse.
    """

    SOURCE = [
        ('articles', "Prestations cochées"),
        ('mo_avec_soin', "Mises en observation ayant reçu un soin payé"),
        ('mo_sans_soin', "Mises en observation payées sans aucun soin"),
        ('manuelle', "Case à remplir à la main"),
    ]
    ORIGINE = [
        ('procedure', "Module Soins"),
        ('mo', "Mise en observation"),
        ('les_deux', "Les deux"),
    ]

    bloc = models.ForeignKey(
        BlocFicheSoins, on_delete=models.CASCADE,
        related_name='lignes', verbose_name="Bloc")
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    source = models.CharField(
        max_length=20, choices=SOURCE, default='articles',
        verbose_name="Ce que compte la ligne")
    origines = models.CharField(
        max_length=20, choices=ORIGINE, default='procedure',
        verbose_name="Où chercher les prestations")
    articles = models.ManyToManyField(
        'services.Articleservice', blank=True,
        related_name='lignes_fiche_soins', verbose_name="Prestations")

    def __str__(self):
        return self.libelle

    class Meta:
        verbose_name = "Ligne de la fiche de soins"
        verbose_name_plural = "Lignes de la fiche de soins"
        ordering = ['ordre', 'id']
