"""
Automatic activity logging via post_save signal.

Every save triggered inside a request (i.e. when CurrentUserMiddleware has
stored a user) creates a LogActivite entry, UNLESS the caller already created
a specific entry and marked the instance with _skip_auto_log = True.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

# Apps whose models are tracked in the sidebar
AUDITED_APPS = {
    'patients', 'facturation', 'hospitalisation', 'laboratoire',
    'achats', 'conges', 'employer', 'medecins', 'pharmacie',
    'services', 'soins', 'stock', 'ressources_humaines', 'rapports',
}

# Model names (lowercase) never auto-logged to avoid loops or noise
SKIP_MODELS = {
    'logactivite', 'userprofile', 'session', 'logentry',
    'permission', 'group', 'contenttype',
}


@receiver(post_save)
def auto_log_save(sender, instance, created, **kwargs):
    try:
        app = sender._meta.app_label
        model = sender._meta.model_name

        if app not in AUDITED_APPS or model in SKIP_MODELS:
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
        msg = f'{label} créé(e)' if created else f'{label} modifié(e)'
        log_event(instance, user, msg, type='system' if created else 'modif')

    except Exception:
        pass
