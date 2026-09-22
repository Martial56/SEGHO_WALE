from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models.functions import ExtractYear
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.models import LogActivite
from core.views import log_event

_est_admin = user_passes_test(lambda u: u.is_superuser, login_url='login')

MOIS_CHOICES = [
    (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
    (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
    (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
]


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


@login_required(login_url='login')
@_est_admin
def journal_list(request):
    qs = LogActivite.objects.select_related('user', 'content_type').all()

    utilisateur_id = request.GET.get('utilisateur', '')
    if utilisateur_id:
        qs = qs.filter(user_id=utilisateur_id)

    module = request.GET.get('module', '')
    if module:
        qs = qs.filter(module=module)

    type_log = request.GET.get('type', '')
    if type_log:
        qs = qs.filter(type=type_log)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(message__icontains=q)

    date_debut = _parse_date(request.GET.get('date_debut', ''))
    if date_debut:
        qs = qs.filter(date__date__gte=date_debut)
    date_fin = _parse_date(request.GET.get('date_fin', ''))
    if date_fin:
        qs = qs.filter(date__date__lte=date_fin)

    mois = request.GET.get('mois', '')
    if mois:
        qs = qs.filter(date__month=mois)
    annee = request.GET.get('annee', '')
    if annee:
        qs = qs.filter(date__year=annee)

    utilisateurs = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')

    modules = (
        LogActivite.objects
        .exclude(module='')
        .values_list('module', flat=True)
        .distinct()
        .order_by('module')
    )

    annees = (
        LogActivite.objects
        .annotate(annee=ExtractYear('date'))
        .values_list('annee', flat=True)
        .distinct()
        .order_by('-annee')
    )

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'journal/list.html', {
        'page_obj': page_obj,
        'utilisateurs': utilisateurs,
        'modules': modules,
        'type_choices': LogActivite.TYPE_CHOICES,
        'utilisateur_id': utilisateur_id,
        'module': module,
        'type_log': type_log,
        'q': q,
        'date_debut': request.GET.get('date_debut', ''),
        'date_fin': request.GET.get('date_fin', ''),
        'mois_choices': MOIS_CHOICES,
        'mois': mois,
        'annees': annees,
        'annee': annee,
        'querystring': request.GET.urlencode(),
        'total_count': LogActivite.objects.count(),
    })


@login_required(login_url='login')
@_est_admin
@require_POST
def journal_supprimer_selection(request):
    ids = request.POST.getlist('selection')
    a_supprimer = list(LogActivite.objects.filter(pk__in=ids).values_list('pk', flat=True))
    nb, _ = LogActivite.objects.filter(pk__in=ids).delete()

    if nb:
        # Journalisée APRÈS la suppression : cette trace ne peut pas
        # s'auto-effacer, même si elle porte sur d'autres entrées du journal.
        ids_txt = ', '.join(str(i) for i in a_supprimer[:20])
        if len(a_supprimer) > 20:
            ids_txt += f", … (+{len(a_supprimer) - 20})"
        log_event(
            request.user, request.user,
            f"{nb} entrée{'s' if nb > 1 else ''} du journal supprimée{'s' if nb > 1 else ''} (IDs : {ids_txt})",
            type='suppression',
        )
        messages.success(request, f"{nb} entrée{'s' if nb > 1 else ''} du journal supprimée{'s' if nb > 1 else ''}.")
    else:
        messages.info(request, "Aucune entrée sélectionnée.")

    qs = request.POST.get('querystring', '')
    return redirect(f"/journal/?{qs}" if qs else '/journal/')


@login_required(login_url='login')
@_est_admin
@require_POST
def journal_vider(request):
    nb, _ = LogActivite.objects.all().delete()
    # Créée APRÈS le vidage : c'est la seule entrée qui subsiste, elle prouve
    # que le journal a été vidé, par qui, quand et depuis quelle adresse IP.
    log_event(
        request.user, request.user,
        f"Journal vidé — {nb} entrée{'s' if nb > 1 else ''} supprimée{'s' if nb > 1 else ''}.",
        type='suppression',
    )
    messages.success(request, f"Journal vidé — {nb} entrée{'s' if nb > 1 else ''} supprimée{'s' if nb > 1 else ''}.")
    return redirect('journal:list')
