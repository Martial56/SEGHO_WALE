from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.urls import reverse

from .models import Facture, LigneFacture, Acte, Paiement
from .forms import FactureForm
from core.views import log_event, get_logs


@login_required(login_url='login')
def facturation_list(request):
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()

    qs = Facture.objects.select_related('patient').order_by('-date_emission')

    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    total = qs.count()

    all_qs = Facture.objects.all()
    montant_total   = all_qs.aggregate(s=Sum('montant_total'))['s'] or 0
    montant_recu    = all_qs.aggregate(s=Sum('montant_paye'))['s']  or 0
    montant_attente = montant_total - montant_recu
    taux_recouvrement = round(montant_recu * 100 / montant_total) if montant_total else 0

    stats = {
        'montant_total':      int(montant_total),
        'montant_recu':       int(montant_recu),
        'montant_attente':    int(montant_attente),
        'taux_recouvrement':  taux_recouvrement,
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'facturation/list.html', {
        'page_obj':       page_obj,
        'stats':          stats,
        'q':              q,
        'statut':         statut,
        'total':          total,
        'statut_choices': Facture.STATUT,
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
    services   = Articleservice.objects.all().order_by('nom')

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

    initial_type_facture  = 'consultation' if rdv_obj else ''
    initial_ligne_libelle = (rdv_obj.type_consultation.nom
                             if (rdv_obj and rdv_obj.type_consultation) else '')

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

            log_event(facture, request.user, 'Facture créée.', type='system')

            facture = _handle_paiement(facture, request.POST, request.user, total)

            messages.success(request, f'Facture {facture.numero} créée avec succès.')
            if hosp_pk:
                return redirect(f'/hospitalisation/{hosp_pk}/modifier/')
            if rdv_pk:
                return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv_pk}))
            return redirect('facturation:list')
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
        'initial_ligne_libelle': initial_ligne_libelle,
        'edit':                 False,
    })


@login_required(login_url='login')
def facture_edit(request, pk):
    from caisse.models import Caisse
    from services.models import Articleservice

    facture  = get_object_or_404(Facture, pk=pk)
    actes    = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses  = Caisse.objects.filter(actif=True).order_by('nom')
    services = Articleservice.objects.all().order_by('nom')
    lignes   = list(facture.lignes.all())
    is_admin = request.user.is_superuser

    if request.method == 'POST':
        # ── Actions workflow ────────────────────────────────────────────────
        if 'action_emettre' in request.POST:
            if facture.statut == 'brouillon' or is_admin:
                facture.statut = 'emise'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Émise', type='statut')
                messages.success(request, 'Facture émise.')
            return redirect('facturation:edit', pk=facture.pk)

        if 'action_payer' in request.POST:
            if facture.statut in ('emise', 'brouillon') or is_admin:
                facture.statut = 'payee'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Payée', type='statut')
                messages.success(request, 'Facture marquée comme payée.')
            return redirect('facturation:edit', pk=facture.pk)

        if 'action_annuler' in request.POST:
            if facture.statut != 'annulee' or is_admin:
                facture.statut = 'annulee'
                facture.save()
                log_event(facture, request.user, 'Facture annulée', type='statut')
                messages.success(request, 'Facture annulée.')
            return redirect('facturation:edit', pk=facture.pk)

        if 'action_brouillon' in request.POST:
            if facture.statut == 'emise' or is_admin:
                facture.statut = 'brouillon'
                facture.save()
                log_event(facture, request.user, 'Remise en brouillon', type='statut')
                messages.success(request, 'Remise en brouillon.')
            return redirect('facturation:edit', pk=facture.pk)

        # ── Sauvegarde ──────────────────────────────────────────────────────
        form = FactureForm(request.POST, instance=facture)
        if form.is_valid():
            facture = form.save(commit=False)
            facture.lignes.all().delete()
            total = _save_lignes(facture, request.POST)
            facture.montant_total = total
            facture.save()

            facture = _handle_paiement(facture, request.POST, request.user, total)

            log_event(facture, request.user, 'Facture mise à jour.', type='modif')
            messages.success(request, f'Facture {facture.numero} mise à jour.')
            return redirect('facturation:edit', pk=facture.pk)
    else:
        form = FactureForm(instance=facture)

    return render(request, 'facturation/create_facture.html', {
        'form':      form,
        'facture':   facture,
        'patient':   facture.patient,
        'actes':     actes,
        'services':  services,
        'caisses':   caisses,
        'lignes':    lignes,
        'is_admin':  is_admin,
        'edit':      True,
        'paiements': list(facture.paiements.all()),
        'logs':      get_logs(facture),
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
