"""Écran de fin d'exercice (lot 8) : inventaire des stocks, contrôles,
clôture et réouverture. Les règles vivent dans comptabilite/cloture.py."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from core.middleware import get_current_centre
from core.views import log_event

from . import cloture as regles
from . import ecritures as moteur
from .models import Ecriture, Exercice


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _montant(valeur):
    try:
        return Decimal(str(valeur or '').replace(' ', '').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        return None


@login_required(login_url='login')
def exercices(request):
    _exiger(request.user, 'comptabilite.view_exercice')
    return render(request, 'comptabilite/exercices.html', {
        'exercices': Exercice.objects.select_related('cloture_par'),
    })


@login_required(login_url='login')
def exercice(request, pk):
    _exiger(request.user, 'comptabilite.view_exercice')
    exercice_ = get_object_or_404(Exercice, pk=pk)
    centre = get_current_centre()
    verif = None
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'inventaire':
                _exiger(request.user, 'comptabilite.passer_ecritures')
                valeurs = {t: _montant(request.POST.get(f'valeur_{t}')) for t, _ in regles.TYPES_STOCK
                           if f'valeur_{t}' in request.POST}
                ecriture = regles.comptabiliser_inventaire(exercice_, centre, valeurs, request.user)
                if ecriture:
                    messages.success(request, "Écriture d'inventaire préparée en brouillon : validez-la au "
                                              "passage des écritures.")
                else:
                    messages.info(request, "Les comptes de stock sont déjà à la valeur inventoriée : aucune "
                                           "variation à passer.")
                return redirect('comptabilite:exercice', pk=pk)
            if action == 'verifier':
                verif = regles.controles(exercice_)
            elif action == 'cloturer':
                _exiger(request.user, 'comptabilite.cloturer_exercice')
                regles.cloturer(exercice_, request.user,
                                malgre_avertissements=request.POST.get('malgre') == '1')
                log_event(exercice_, request.user, f'Exercice {exercice_} clôturé.', type='statut',
                          module='comptabilite')
                messages.success(request, f"Exercice {exercice_} clôturé ; les à-nouveaux sont passés dans "
                                          "l'exercice suivant.")
                return redirect('comptabilite:exercice', pk=pk)
            elif action == 'rouvrir':
                _exiger(request.user, 'comptabilite.cloturer_exercice')
                regles.rouvrir(exercice_, request.user)
                log_event(exercice_, request.user, f'Exercice {exercice_} rouvert.', type='statut',
                          module='comptabilite')
                messages.warning(request, f"Exercice {exercice_} rouvert : ses à-nouveaux sont retirés, "
                                          "à refaire par une nouvelle clôture.")
                return redirect('comptabilite:exercice', pk=pk)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
            if action != 'verifier':
                return redirect('comptabilite:exercice', pk=pk)
    inventaire = None
    if exercice_.statut == 'ouvert':
        try:
            inventaire = regles.situation_inventaire(exercice_, centre)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
    return render(request, 'comptabilite/exercice.html', {
        'exercice': exercice_, 'centre': centre, 'inventaire': inventaire, 'verif': verif,
        'ecriture_inventaire': regles.ecriture_inventaire(exercice_, centre),
        'a_nouveaux': Ecriture.objects.filter(origine__startswith=f'an:{exercice_.pk}:').select_related('exercice'),
        'resultat': regles.resultat(exercice_) if exercice_.statut == 'ouvert' else exercice_.resultat,
        'peut_inventorier': request.user.has_perm('comptabilite.passer_ecritures'),
        'peut_cloturer': request.user.has_perm('comptabilite.cloturer_exercice'),
    })
