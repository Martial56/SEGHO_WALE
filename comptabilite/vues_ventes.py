"""Écrans « Documents des ventes » du module Comptabilité, et sa page d'accueil."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import ventes
from .models import SessionCaissiere
from .vues_compta import _date, _exiger

PERM = 'comptabilite.view_ecriture'


@login_required(login_url='login')
def accueil(request):
    """Entrée du module Comptabilité (carte du tableau de bord) : le premier
    écran que l'utilisateur a le droit d'ouvrir."""
    for perm, route in ((PERM, 'comptabilite:documents_ventes'),
                        ('facturation.view_facture', 'comptabilite:gratuites'),
                        ('comptabilite.superviser_caisse', 'comptabilite:gratuites'),
                        ('comptabilite.view_comptetresorerie', 'comptabilite:tresorerie'),
                        ('comptabilite.view_compte', 'comptabilite:plan_comptable')):
        if request.user.has_perm(perm):
            return redirect(route)
    raise PermissionDenied


@login_required(login_url='login')
def documents_ventes(request):
    from facturation.models import Caisse

    _exiger(request.user, PERM)
    aujourdhui = timezone.localdate()
    debut = _date(request.GET.get('debut'), aujourdhui.replace(day=1))
    fin = _date(request.GET.get('fin'), aujourdhui)
    caisses = list(Caisse.objects.order_by('nom'))
    caisse = next((c for c in caisses if str(c.pk) == request.GET.get('caisse')), None)
    statut = request.GET.get('statut', '')
    docs = ventes.documents(debut, fin, caisse, statut if statut in ventes.STATUTS else None)
    return render(request, 'comptabilite/documents_ventes.html', {
        'documents': docs, 'debut': debut, 'fin': fin, 'caisses': caisses, 'caisse': caisse,
        'statut': statut, 'statuts': ventes.STATUTS,
    })


@login_required(login_url='login')
def document_vente(request, pk):
    _exiger(request.user, PERM)
    session = get_object_or_404(SessionCaissiere.objects.select_related('journee__caisse', 'caissiere'),
                                pk=pk, statut='validee')
    return render(request, 'comptabilite/document_vente.html', {'doc': ventes.document(session),
                                                                'retour': request.GET.get('retour', '')})
