from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Centre


@login_required
@require_POST
def changer_centre(request, centre_id):
    """Bascule le centre actif de l'utilisateur connecté vers `centre_id`,
    puis revient à la page précédente."""
    centre = get_object_or_404(Centre, pk=centre_id)
    profile = request.user.profile
    if not profile.peut_acceder(centre):
        raise PermissionDenied("Vous n'avez pas accès à ce centre.")

    profile.centre_actif = centre
    profile.save(update_fields=['centre_actif'])

    next_url = request.META.get('HTTP_REFERER')
    return redirect(next_url) if next_url else redirect('dashboard')
