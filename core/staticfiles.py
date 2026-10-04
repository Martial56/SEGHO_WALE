"""Coller la date du fichier à l'adresse d'un fichier statique.

`{% static 'js/listing_groupes.js' %}` rendait toujours la même adresse, quel
que soit le contenu du fichier. Un navigateur qui en gardait une copie la
réutilisait donc indéfiniment, et une correction livrée restait invisible chez
celui qui avait déjà ouvert la page.

Ce n'est pas une hypothèse : le chargement différé des groupes a été livré avec
un script qui va chercher les lignes au serveur, alors que l'ancien se
contentait de démasquer des lignes déjà présentes. Les deux se ressemblent
assez pour qu'aucune erreur ne paraisse — le groupe s'ouvrait, et restait vide.
Il a fallu un aller-retour pour comprendre qu'il fallait vider le cache.

D'où ceci : l'adresse porte la date de dernière modification du fichier.

    /static/js/listing_groupes.js?v=1759419240

Le fichier change, l'adresse change, le navigateur va rechercher. Rien à
demander à personne, et aucun gabarit à toucher — c'est `{% static %}` lui-même
qui en profite, partout.

La date est retenue par chemin : rendre une page demande des dizaines
d'adresses, et interroger le disque à chaque fois pour un fichier qui ne bouge
pas serait payer cher un renseignement constant. Le serveur de développement
recharge le processus à chaque modification du code, et un fichier statique
modifié seul se voit au rechargement suivant du serveur ; en production, le
processus repart au déploiement, c'est-à-dire exactement quand les fichiers
changent.
"""
import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.exceptions import SuspiciousFileOperation


class StockageStatiqueDate(StaticFilesStorage):
    """Stockage statique dont les adresses portent la date du fichier."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dates = {}

    def _chemin_sur_disque(self, nom):
        """Où le fichier se trouve réellement, des deux côtés.

        Après `collectstatic` il est sous `STATIC_ROOT`, que le stockage
        connaît. En développement il n'y est pas : il vit dans
        `STATICFILES_DIRS`, et seuls les chercheurs savent l'y retrouver.
        Interroger le stockage seul rendait donc une date introuvable et une
        adresse sans version — exactement là où on en a le plus besoin.
        """
        try:
            chemin = self.path(nom)
            if os.path.exists(chemin):
                return chemin
        except (NotImplementedError, ValueError, SuspiciousFileOperation):
            pass
        return finders.find(nom)

    def _date(self, nom):
        if nom not in self._dates:
            chemin = self._chemin_sur_disque(nom)
            try:
                self._dates[nom] = int(os.path.getmtime(chemin))
            except (TypeError, OSError):
                # Fichier absent, stockage distant, horloge indisponible : on
                # rend l'adresse nue plutôt que de faire échouer le rendu de la
                # page pour une question de cache.
                self._dates[nom] = None
        return self._dates[nom]

    def url(self, nom):
        adresse = super().url(nom)
        date = self._date(nom)
        if date is None:
            return adresse
        return f"{adresse}{'&' if '?' in adresse else '?'}v={date}"
