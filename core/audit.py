"""
Journal d'activité automatique : trace les créations, modifications,
suppressions et connexions de chaque utilisateur, via signaux Django.

Toute sauvegarde/suppression déclenchée dans une requête (c'est-à-dire quand
CurrentUserMiddleware a mémorisé un utilisateur) crée une entrée LogActivite,
SAUF si l'appelant a déjà créé une entrée plus précise et marqué l'instance
avec _skip_auto_log = True.
"""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

# Apps techniques jamais tracées (tout le reste de INSTALLED_APPS l'est) —
# la liste des modules métier n'a ainsi pas besoin d'être tenue à jour à
# chaque nouvelle app.
UNAUDITED_APPS = {
    'admin', 'auth', 'contenttypes', 'sessions', 'messages',
    'staticfiles', 'humanize', 'django_browser_reload',
}

# Noms de modèles (minuscules) jamais tracés automatiquement, pour éviter
# les boucles ou le bruit
SKIP_MODELS = {
    'logactivite', 'userprofile', 'session', 'logentry',
    'permission', 'group', 'contenttype',
}


def _est_audite(sender):
    app = sender._meta.app_label
    model = sender._meta.model_name
    return app not in UNAUDITED_APPS and model not in SKIP_MODELS


def _valeur_lisible(valeur):
    if valeur is None:
        return '—'
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    texte = str(valeur)
    return texte if len(texte) <= 60 else texte[:57] + '…'


def _champs_modifies(sender, avant, apres):
    """Liste "Libellé : ancienne valeur → nouvelle valeur" pour chaque champ
    qui a réellement changé entre les deux états (hors champs non éditables :
    id, horodatages auto_now, etc.)."""
    diffs = []
    for field in sender._meta.fields:
        if field.primary_key or not field.editable:
            continue
        try:
            v_avant = getattr(avant, field.name)
            v_apres = getattr(apres, field.name)
        except Exception:
            continue
        if v_avant == v_apres:
            continue
        label = field.verbose_name or field.name
        diffs.append(f"{label} : {_valeur_lisible(v_avant)} → {_valeur_lisible(v_apres)}")
    return diffs


@receiver(pre_save)
def auto_snapshot_avant_save(sender, instance, **kwargs):
    """Mémorise l'état en base AVANT modification, pour pouvoir détailler ce
    qui a changé une fois la sauvegarde effectuée (post_save ne voit que le
    nouvel état)."""
    try:
        if not _est_audite(sender) or not instance.pk:
            return
        instance._etat_avant_modif = sender.objects.filter(pk=instance.pk).first()
    except Exception:
        pass


@receiver(post_save)
def auto_log_save(sender, instance, created, **kwargs):
    try:
        if not _est_audite(sender):
            return

        # Caller opted out — they'll log a richer message themselves
        if getattr(instance, '_skip_auto_log', False):
            return

        from core.middleware import get_current_user
        user = get_current_user()
        if not user or not user.is_authenticated:
            return

        from core.views import log_event
        label = sender._meta.verbose_name.capitalize()

        if created:
            log_event(instance, user, f'{label} créé(e)', type='system')
            return

        avant = getattr(instance, '_etat_avant_modif', None)
        diffs = _champs_modifies(sender, avant, instance) if avant is not None else []
        msg = f"{label} modifié(e) — " + " ; ".join(diffs) if diffs else f'{label} modifié(e)'
        log_event(instance, user, msg, type='modif')

    except Exception:
        pass


@receiver(post_delete)
def auto_log_delete(sender, instance, **kwargs):
    try:
        if not _est_audite(sender):
            return

        if getattr(instance, '_skip_auto_log', False):
            return

        from core.middleware import get_current_user
        user = get_current_user()
        if not user or not user.is_authenticated:
            return

        from core.views import log_event
        label = sender._meta.verbose_name.capitalize()
        log_event(instance, user, f'{label} supprimé(e) : {instance}', type='suppression')

    except Exception:
        pass


@receiver(user_logged_in)
def auto_log_login(sender, request, user, **kwargs):
    try:
        request.session['login_time'] = timezone.now().isoformat()
        from core.views import log_event
        log_event(user, user, 'Connexion', type='connexion')
    except Exception:
        pass


@receiver(user_logged_out)
def auto_log_logout(sender, request, user, **kwargs):
    try:
        if not user:
            return

        duree = None
        login_time_iso = request.session.get('login_time')
        if login_time_iso:
            from datetime import datetime
            login_time = datetime.fromisoformat(login_time_iso)
            duree = int((timezone.now() - login_time).total_seconds())

        from core.views import log_event
        log_event(user, user, 'Déconnexion', type='connexion', duree_secondes=duree)
    except Exception:
        pass
