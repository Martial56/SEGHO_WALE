"""Imports longs menés en tâche de fond, avec avancement consultable.

Un import de quelques dizaines de milliers de lignes ne tient pas dans une
requête : le navigateur attend sans rien montrer, et l'utilisateur n'a aucun
moyen de distinguer « ça travaille » de « c'est bloqué ». On rend donc la main
tout de suite, et le travail continue dans un fil d'exécution qui pose son
avancement en base (core.models.TacheImport) ; la page le relit toutes les
deux secondes.

Le fil n'hérite pas du contexte de la requête : les variables thread-local
posées par CurrentUserMiddleware (utilisateur, centre actif) sont vides de
l'autre côté. Tout ce dont le travail a besoin doit donc lui être passé
explicitement — c'est pour cela que `lancer` prend le centre en argument et le
réinstalle, plutôt que de laisser le code appelé s'en remettre aux managers
cloisonnés.
"""

import threading
import time
import traceback

from django.db import connection
from django.utils import timezone

from core.middleware import centre_actif
from core.models import TacheImport


class Avancement:
    """Compteurs d'une tâche, écrits en base par paliers.

    Écrire à chaque enregistrement coûterait plus cher que l'import lui-même.
    On n'enregistre donc qu'au-delà d'un demi-seconde depuis la dernière fois :
    la jauge est relue toutes les deux secondes, elle n'a pas besoin de mieux.
    """

    INTERVALLE_SECONDES = 0.5

    def __init__(self, tache):
        self.tache = tache
        self._dernier_ecrit = 0.0

    def etape(self, libelle, total=None):
        self.tache.etape = libelle
        if total is not None:
            self.tache.total = total
        self._ecrire()

    def ajouter(self, traites=0, crees=0, mis_a_jour=0, ignores=0, erreurs=0):
        self.tache.traites += traites
        self.tache.crees += crees
        self.tache.mis_a_jour += mis_a_jour
        self.tache.ignores += ignores
        self.tache.erreurs += erreurs
        if time.monotonic() - self._dernier_ecrit >= self.INTERVALLE_SECONDES:
            self._ecrire()

    def enregistrer(self):
        """Force l'écriture des compteurs, sans attendre le palier suivant.

        À appeler quand le travail se termine : sinon les derniers
        enregistrements d'un lot — ou la totalité d'un petit import, plus rapide
        que le palier — resteraient en mémoire et la jauge s'arrêterait avant
        d'atteindre son terme.
        """
        self._ecrire()

    def _ecrire(self):
        self.tache.save(update_fields=[
            'etape', 'total', 'traites', 'crees', 'mis_a_jour', 'ignores', 'erreurs',
        ])
        self._dernier_ecrit = time.monotonic()


def lancer(libelle, utilisateur, centre, travail):
    """Démarre `travail(avancement)` en tâche de fond et rend la tâche créée.

    `travail` reçoit un Avancement à nourrir, et rend le message final à
    afficher. Toute exception est rattrapée : la tâche passe en échec avec sa
    trace, plutôt que de laisser la jauge tourner indéfiniment.
    """
    tache = TacheImport.objects.create(libelle=libelle, utilisateur=utilisateur,
                                       etape='Préparation…')
    fil = threading.Thread(target=_executer, args=(tache.pk, centre, travail),
                           name=f'import-{tache.pk}', daemon=True)
    fil.start()
    return tache


def _executer(tache_id, centre, travail):
    tache = TacheImport.objects.get(pk=tache_id)
    avancement = Avancement(tache)
    try:
        with centre_actif(centre):
            tache.message = travail(avancement) or ''
        avancement.enregistrer()
        tache.etat = 'termine'
        tache.etape = 'Terminé'
    except Exception:
        tache.etat = 'echec'
        tache.etape = 'Interrompu'
        tache.message = traceback.format_exc(limit=3)
    finally:
        tache.date_fin = timezone.now()
        try:
            tache.save()
        except Exception:
            pass
        # Un fil qui se termine laisserait sinon sa connexion ouverte : sur
        # SQLite elle garde le fichier verrouillé, sur PostgreSQL elle occupe
        # une place dans le pool.
        connection.close()
