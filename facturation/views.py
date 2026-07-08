from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.urls import reverse
from django.http import JsonResponse

from .models import Facture, LigneFacture, Acte, Paiement
from .forms import FactureForm
from core.views import log_event, get_logs

# Rôles autorisés à enregistrer un encaissement (voir aussi hospitalisation
# management/commands/init_groupes_hospitalisation.py qui définit "Caisse").
CAISSE_MANAGE_GROUPS = {'Caisse', 'Administrateur', 'Directeur'}


def can_manage_paiement(user):
    return user.is_superuser or user.groups.filter(name__in=CAISSE_MANAGE_GROUPS).exists()


@login_required(login_url='login')
def facturation_list(request):
    q      = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    type_f = request.GET.get('type_f', '').strip()

    qs = Facture.objects.select_related('patient').order_by('-date_emission')

    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)
    if type_f:
        qs = qs.filter(type_facture=type_f)

    total = qs.count()

    all_qs = Facture.objects.all()
    montant_total     = all_qs.aggregate(s=Sum('montant_total'))['s'] or 0
    montant_recu      = all_qs.aggregate(s=Sum('montant_paye'))['s']  or 0
    montant_attente   = montant_total - montant_recu
    taux_recouvrement = round(montant_recu * 100 / montant_total) if montant_total else 0
    nb_factures       = all_qs.count()
    nb_payees         = all_qs.filter(statut='payee').count()
    nb_emises         = all_qs.filter(statut='emise').count()

    stats = {
        'montant_total':     int(montant_total),
        'montant_recu':      int(montant_recu),
        'montant_attente':   int(montant_attente),
        'taux_recouvrement': taux_recouvrement,
        'nb_factures':       nb_factures,
        'nb_payees':         nb_payees,
        'nb_emises':         nb_emises,
    }

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rows = []
        for f in page_obj.object_list:
            rows.append({
                'pk':           f.pk,
                'numero':       f.numero,
                'patient':      f'{f.patient.nom} {f.patient.prenoms}',
                'type_display': f.get_type_facture_display(),
                'date':         f.date_emission.strftime('%d/%m/%Y'),
                'montant_total': float(f.montant_total),
                'montant_paye':  float(f.montant_paye),
                'solde_restant': float(f.solde_restant),
                'statut':        f.statut,
                'statut_display': f.get_statut_display(),
                'url':           reverse('facturation:detail', args=[f.pk]),
            })
        return JsonResponse({
            'rows':         rows,
            'total':        total,
            'has_previous': page_obj.has_previous(),
            'has_next':     page_obj.has_next(),
            'start_index':  page_obj.start_index() if page_obj.object_list else 0,
            'end_index':    page_obj.end_index(),
            'count':        page_obj.paginator.count,
            'page':         page_obj.number,
        })

    return render(request, 'facturation/list.html', {
        'page_obj':       page_obj,
        'stats':          stats,
        'q':              q,
        'statut':         statut,
        'type_f':         type_f,
        'total':          total,
        'statut_choices': Facture.STATUT,
        'type_choices':   Facture.TYPE,
    })


@login_required(login_url='login')
def facture_create(request):
    from patients.models import Patient, RendezVous
    from caisse.models import Caisse
    from services.models import Articleservice

    patient_pk = request.GET.get('patient') or request.POST.get('patient_id')
    patient    = get_object_or_404(Patient, pk=patient_pk) if patient_pk else None
    actes      = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses    = Caisse.objects.filter(actif=True).order_by('nom')
    services   = Articleservice.objects.select_related('categorie').filter(actif=True).order_by('nom')

    hosp_obj = None
    hosp_pk  = request.GET.get('hospitalisation') or request.POST.get('hospitalisation_id')
    if hosp_pk:
        try:
            from hospitalisation.models import Hospitalisation as HospModel
            hosp_obj = HospModel.objects.get(pk=hosp_pk)
        except Exception:
            pass

    rdv_obj = None
    rdv_pk  = request.GET.get('rdv') or request.POST.get('rdv_id')
    if rdv_pk:
        try:
            rdv_obj = RendezVous.objects.get(pk=rdv_pk)
        except RendezVous.DoesNotExist:
            pass

    demande_obj = None
    demande_pk  = request.GET.get('demande') or request.POST.get('demande_id')
    if demande_pk:
        try:
            from laboratoire.models import DemandeExamen
            demande_obj = DemandeExamen.objects.prefetch_related('lignes__type_examen').get(pk=demande_pk)
        except Exception:
            pass

    ordonnance_obj = None
    ordonnance_pk  = request.GET.get('ordonnance') or request.POST.get('ordonnance_id')
    if ordonnance_pk:
        try:
            from consultations.models import Ordonnance
            ordonnance_obj = Ordonnance.objects.prefetch_related(
                'lignes__produit', 'lignes__medicament'
            ).get(pk=ordonnance_pk)
        except Exception:
            pass

    initial_lignes = []
    if demande_obj:
        for ligne in demande_obj.lignes.select_related('type_examen').all():
            libelle = ligne.libelle or (str(ligne.type_examen) if ligne.type_examen else '')
            initial_lignes.append({
                'libelle': libelle,
                'prix': ligne.prix,
                'qte': 1,
                'remise': 0,
            })
    elif ordonnance_obj:
        for ligne in ordonnance_obj.lignes.all():
            if ligne.produit:
                libelle = ligne.produit.nom
                prix    = float(ligne.produit.prix_vente)
            elif ligne.medicament:
                libelle = ligne.medicament.designation
                prix    = float(ligne.medicament.prix_vente)
            elif ligne.medicament_libre:
                libelle = ligne.medicament_libre
                prix    = 0
            else:
                continue
            initial_lignes.append({
                'libelle': libelle,
                'prix':    prix,
                'qte':     ligne.quantite,
                'remise':  0,
            })

    initial_type_facture  = ('laboratoire' if demande_obj else
                             'pharmacie'   if ordonnance_obj else
                             'consultation' if rdv_obj else '')
    initial_ligne_libelle = (rdv_obj.type_consultation.nom
                             if (rdv_obj and rdv_obj.type_consultation) else '')

    back_url = request.GET.get('back') or (
        reverse('hospitalisation:detail', kwargs={'pk': hosp_obj.pk})       if hosp_obj else
        f'/laboratoire/{demande_obj.pk}/'                                    if demande_obj else
        reverse('ordonnance_detail', kwargs={'pk': ordonnance_obj.pk})       if ordonnance_obj else
        reverse('patients:rdv_edit', kwargs={'pk': rdv_obj.pk})              if rdv_obj else
        ''
    )

    if request.method == 'POST':
        form = FactureForm(request.POST)
        if not patient:
            messages.error(request, 'Patient introuvable.')
            return redirect('facturation:list')
        if form.is_valid():
            facture = form.save(commit=False)
            facture.patient  = patient
            facture.cree_par = request.user
            if hosp_obj:
                facture.hospitalisation = hosp_obj
                facture.type_facture    = 'hospitalisation'
            facture.save()

            total = _save_lignes(facture, request.POST)
            facture.montant_total = total
            facture.save()

            if demande_obj:
                demande_obj.facture = facture
                demande_obj.save(update_fields=['facture'])

            log_event(facture, request.user, 'Facture créée.', type='system')

            if request.POST.get('pay_montant', '').strip() and not can_manage_paiement(request.user):
                messages.warning(request, "Facture créée, mais le paiement n'a pas été enregistré : cette action est réservée à la Caisse.")
            else:
                facture = _handle_paiement(facture, request.POST, request.user, total)

            messages.success(request, f'Facture {facture.numero} créée avec succès.')
            if hosp_pk:
                return redirect(f'/hospitalisation/{hosp_pk}/modifier/')
            if rdv_pk:
                return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv_pk}))
            if demande_pk:
                return redirect(f'/laboratoire/{demande_pk}/')
            next_url = request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('facturation:list')
        # Form invalid: preserve submitted lignes so dynamically-added rows survive re-render
        _i, _post_lignes = 0, []
        while True:
            _lib = request.POST.get(f'ligne_libelle_{_i}')
            if _lib is None:
                break
            _post_lignes.append({
                'libelle': _lib,
                'prix':    request.POST.get(f'ligne_prix_{_i}', 0),
                'qte':     request.POST.get(f'ligne_qte_{_i}', 1),
                'remise':  request.POST.get(f'ligne_remise_{_i}', 0),
            })
            _i += 1
        if _post_lignes:
            initial_lignes = _post_lignes
    else:
        initial = {'type_facture': initial_type_facture} if initial_type_facture else {}
        form = FactureForm(initial=initial)

    return render(request, 'facturation/create_facture.html', {
        'form':                 form,
        'patient':              patient,
        'actes':                actes,
        'services':             services,
        'caisses':              caisses,
        'rdv':                  rdv_obj,
        'demande':              demande_obj,
        'ordonnance':           ordonnance_obj,
        'hospitalisation':      hosp_obj,
        'initial_ligne_libelle': initial_ligne_libelle,
        'initial_lignes':       initial_lignes,
        'back_url':             back_url,
        'edit':                 False,
    })


@login_required(login_url='login')
def facture_detail(request, pk):
    facture   = get_object_or_404(Facture, pk=pk)
    lignes    = facture.lignes.all()
    paiements = facture.paiements.order_by('date_paiement') if hasattr(facture, 'paiements') else []
    logs      = get_logs(facture)
    back_url  = request.GET.get('next', reverse('facturation:list'))
    return render(request, 'facturation/detail.html', {
        'facture':   facture,
        'lignes':    lignes,
        'paiements': paiements,
        'logs':      logs,
        'is_admin':  request.user.is_superuser or request.user.is_staff,
        'can_manage_paiement': can_manage_paiement(request.user),
        'back_url':  back_url,
    })


@login_required(login_url='login')
def facture_valider(request, pk):
    facture  = get_object_or_404(Facture, pk=pk)
    back_url = request.POST.get('next', reverse('facturation:list'))
    if request.method == 'POST' and facture.statut == 'brouillon':
        facture.statut = 'emise'
        facture.save()
        log_event(facture, request.user, 'Statut changé : émise', type='statut')
        messages.success(request, f"Facture {facture.numero} validée et émise.")
    return redirect(f"{reverse('facturation:detail', kwargs={'pk': pk})}?next={back_url}")


@login_required(login_url='login')
def facture_payer(request, pk):
    if not can_manage_paiement(request.user):
        raise PermissionDenied
    from soins.models import Soin
    facture  = get_object_or_404(Facture, pk=pk)
    if request.method != 'POST':
        return redirect('facturation:detail', pk=pk)
    back_url = request.POST.get('next', reverse('facturation:list'))

    try:
        montant = float(request.POST.get('pay_montant', 0))
    except (TypeError, ValueError):
        montant = 0

    if montant > 0 and facture.statut in ('brouillon', 'emise'):
        Paiement.objects.create(
            facture=facture,
            montant=montant,
            mode_paiement=request.POST.get('pay_mode', 'especes'),
            reference=request.POST.get('pay_reference', ''),
            recu_par=request.user,
        )
        total_paye = sum(p.montant for p in facture.paiements.all())
        facture.montant_paye = total_paye
        if total_paye >= facture.montant_total:
            facture.statut = 'payee'
            facture.save(update_fields=['montant_paye', 'statut'])
            log_event(facture, request.user, 'Statut changé : payée', type='statut')
            soin = Soin.objects.filter(facture=facture).first()
            if soin:
                soin.statut = 'en_cours'
                soin.save(update_fields=['statut'])
        else:
            facture.save(update_fields=['montant_paye'])

    return redirect(f"{reverse('facturation:detail', kwargs={'pk': pk})}?next={back_url}")


@login_required(login_url='login')
def facture_print(request, pk):
    facture = get_object_or_404(Facture.objects.select_related('patient', 'cree_par'), pk=pk)
    return render(request, 'facturation/print.html', {
        'facture':   facture,
        'lignes':    facture.lignes.select_related('acte').all(),
        'paiements': facture.paiements.all(),
        'back_url':  request.GET.get('next', reverse('facturation:list')),
    })


@login_required(login_url='login')
def facture_apercu(request, pk):
    facture = get_object_or_404(Facture.objects.select_related('patient', 'cree_par'), pk=pk)
    return render(request, 'facturation/apercu.html', {
        'facture':   facture,
        'lignes':    facture.lignes.select_related('acte').all(),
        'paiements': facture.paiements.all(),
        'back_url':  request.GET.get('next', reverse('facturation:list')),
    })


@login_required(login_url='login')
def facture_edit(request, pk):
    from caisse.models import Caisse
    from services.models import Articleservice

    facture  = get_object_or_404(Facture, pk=pk)
    actes    = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses  = Caisse.objects.filter(actif=True).order_by('nom')
    services = Articleservice.objects.select_related('categorie').filter(actif=True).order_by('nom')
    is_admin = request.user.is_superuser
    back_url = request.GET.get('next', reverse('facturation:detail', kwargs={'pk': pk}))

    if request.method == 'POST':
        back_url = request.POST.get('next', back_url)
        detail_url = reverse('facturation:detail', kwargs={'pk': pk})

        # ── Actions workflow ────────────────────────────────────────────────
        if 'action_emettre' in request.POST:
            if facture.statut == 'brouillon' or is_admin:
                facture.statut = 'emise'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Émise', type='statut')
                messages.success(request, 'Facture émise.')
            return redirect(f'{detail_url}?next={back_url}')

        if 'action_payer' in request.POST:
            if not can_manage_paiement(request.user):
                raise PermissionDenied
            if facture.statut in ('emise', 'brouillon') or is_admin:
                facture.statut = 'payee'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Payée', type='statut')
                messages.success(request, 'Facture marquée comme payée.')
            return redirect(f'{detail_url}?next={back_url}')

        if 'action_annuler' in request.POST:
            if facture.statut != 'annulee' or is_admin:
                facture.statut = 'annulee'
                facture.save()
                log_event(facture, request.user, 'Facture annulée', type='statut')
                messages.success(request, 'Facture annulée.')
            return redirect(f'{detail_url}?next={back_url}')

        if 'action_brouillon' in request.POST:
            if facture.statut == 'emise' or is_admin:
                facture.statut = 'brouillon'
                facture.save()
                log_event(facture, request.user, 'Remise en brouillon', type='statut')
                messages.success(request, 'Remise en brouillon.')
            return redirect(f'{detail_url}?next={back_url}')

        # ── Sauvegarde ──────────────────────────────────────────────────────
        form = FactureForm(request.POST, instance=facture, is_admin=is_admin)
        if form.is_valid():
            facture = form.save(commit=False)
            facture.lignes.all().delete()
            total = _save_lignes(facture, request.POST)
            facture.montant_total = total
            facture.save()
            log_event(facture, request.user, 'Facture mise à jour.', type='modif')
            messages.success(request, f'Facture {facture.numero} mise à jour.')
            return redirect(f'{detail_url}?next={back_url}')
    else:
        form = FactureForm(instance=facture, is_admin=is_admin)

    initial_lignes = [
        {
            'libelle': l.libelle,
            'qte':     float(l.quantite),
            'prix':    float(l.prix_unitaire),
            'remise':  float(l.remise),
        }
        for l in facture.lignes.all()
    ]

    return render(request, 'facturation/create_facture.html', {
        'form':          form,
        'facture':       facture,
        'patient':       facture.patient,
        'actes':         actes,
        'services':      services,
        'caisses':       caisses,
        'initial_lignes': initial_lignes,
        'is_admin':      is_admin,
        'edit':          True,
        'back_url':      back_url,
        'paiements':     list(facture.paiements.all()),
        'logs':          get_logs(facture),
    })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _save_lignes(facture, POST):
    total = 0
    i = 0
    while True:
        libelle = POST.get(f'ligne_libelle_{i}')
        if libelle is None:
            break
        if libelle.strip():
            qte    = _parse_float(POST.get(f'ligne_qte_{i}', 1), 1)
            prix   = _parse_float(POST.get(f'ligne_prix_{i}', 0), 0)
            remise = _parse_float(POST.get(f'ligne_remise_{i}', 0), 0)
            ligne  = LigneFacture(
                facture=facture,
                libelle=libelle.strip(),
                quantite=qte,
                prix_unitaire=prix,
                remise=remise,
            )
            acte_id = POST.get(f'ligne_acte_{i}')
            if acte_id:
                try:
                    ligne.acte_id = int(acte_id)
                except ValueError:
                    pass
            ligne.save()
            total += qte * prix * (1 - remise / 100)
        i += 1
    return total


def _handle_paiement(facture, POST, user, total):
    pay_montant_raw = POST.get('pay_montant', '').strip()
    if not pay_montant_raw:
        return facture
    if not can_manage_paiement(user):
        return facture
    pay_montant = _parse_float(pay_montant_raw, 0)
    if pay_montant <= 0:
        return facture

    mode      = POST.get('pay_mode', 'especes')
    memo      = POST.get('pay_memo', '')
    compte    = POST.get('pay_compte', '')
    reference = compte if compte else memo

    Paiement.objects.create(
        facture=facture,
        montant=pay_montant,
        mode_paiement=mode,
        reference=reference,
        notes=memo,
        recu_par=user,
    )

    total_paye = facture.paiements.aggregate(s=Sum('montant'))['s'] or 0
    facture.montant_paye = total_paye
    if total_paye >= facture.montant_total:
        facture.statut = 'payee'
    elif total_paye > 0:
        facture.statut = 'emise'
    facture.save()
    log_event(facture, user, f'Paiement de {int(pay_montant):,} FCFA enregistré.', type='modif')
    return facture
