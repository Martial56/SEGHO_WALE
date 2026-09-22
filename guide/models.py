from django.db import models


class GuideCategorie(models.Model):
    """Une entrée du guide correspondant à un module de l'application
    (Patients, Pharmacie, Stock…) ou à une rubrique transverse (prise en
    main, mon compte)."""
    nom = models.CharField(max_length=100, verbose_name="Nom")
    code = models.SlugField(max_length=50, unique=True, verbose_name="Code")
    icone = models.CharField(
        max_length=50, default='bi-book-half',
        help_text="Classe d'icône Bootstrap Icons (ex: bi-people-fill)",
        verbose_name="Icône",
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="Description courte")
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")
    groupe = models.CharField(
        max_length=100, blank=True,
        help_text="Section du sommaire regroupant plusieurs catégories proches (ex: Ressources humaines)",
        verbose_name="Groupe",
    )
    groupe_ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre du groupe")

    class Meta:
        verbose_name = "Catégorie de guide"
        verbose_name_plural = "Catégories de guide"
        ordering = ['groupe_ordre', 'ordre', 'nom']

    def __str__(self):
        return self.nom


class GuideArticle(models.Model):
    """Un article explicatif rattaché à une catégorie du guide."""
    categorie = models.ForeignKey(
        GuideCategorie, on_delete=models.CASCADE,
        related_name='articles', verbose_name="Catégorie",
    )
    titre = models.CharField(max_length=200, verbose_name="Titre")
    icone = models.CharField(
        max_length=50, default='bi-info-circle-fill',
        help_text="Classe d'icône Bootstrap Icons (ex: bi-list-check)",
        verbose_name="Icône",
    )
    contenu = models.TextField(
        verbose_name="Contenu",
        help_text="Texte explicatif. Une ligne vide sépare les paragraphes.",
    )
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    class Meta:
        verbose_name = "Article de guide"
        verbose_name_plural = "Articles de guide"
        ordering = ['ordre', 'titre']

    def __str__(self):
        return f"{self.categorie.nom} — {self.titre}"
