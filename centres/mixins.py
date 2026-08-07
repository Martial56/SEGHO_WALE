from core.middleware import get_current_centre


class AffecterCentreMixin:
    """Affecte automatiquement le centre actif à l'objet créé par une
    CreateView, sans exposer de champ « centre » dans le formulaire.

    Filet de sécurité redondant avec ModeleCentre.save() (qui fait déjà cette
    affectation pour tout enregistrement) — utile si une vue construit
    l'instance sans passer par form.save()."""

    def form_valid(self, form):
        if getattr(form.instance, 'centre_id', None) is None:
            form.instance.centre = get_current_centre()
        return super().form_valid(form)
