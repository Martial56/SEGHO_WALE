from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count

from consultations.models import Ordonnance, LigneOrdonnance, Consultation
from pharmacie.models import Medicament


@login_required(login_url='login')
def ordonnance_list(request):
    qs = Ordonnance.objects.select_related(
        'consultation__patient', 'consultation__medecin'
    ).annotate(nb_lignes=Count('lignes')).order_by('-date_emission')

    q        = request.GET.get('q', '').strip()
    statut   = request.GET.get('statut', '')
    type_ord = request.GET.get('type', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin   = request.GET.get('date_fin', '')

    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(consultation__patient__nom__icontains=q) |
            Q(consultation__patient__prenoms__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)
    if type_ord:
        qs = qs.filter(type_ordonnance=type_ord)
    if date_debut:
        qs = qs.filter(date_emission__date__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_emission__date__lte=date_fin)

    stats = {
        'total':     qs.count(),
        'emises':    qs.filter(statut='emise').count(),
        'delivrees': qs.filter(statut='delivree').count(),
        'expirees':  qs.filter(statut='expiree').count(),
    }

    return render(request, 'ordonnance/list.html', {
        'ordonnances': qs,
        'stats': stats,
        'q': q,
        'statut_filtre': statut,
        'type_filtre': type_ord,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'today': date.today(),
    })


@login_required(login_url='login')
def ordonnance_detail(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__patient', 'consultation__medecin'
        ).prefetch_related('lignes__medicament'),
        pk=pk
    )
    return render(request, 'ordonnance/detail.html', {
        'ordonnance': ordonnance,
        'today': date.today(),
    })


@login_required(login_url='login')
def ordonnance_print(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__patient', 'consultation__medecin'
        ).prefetch_related('lignes__medicament'),
        pk=pk
    )
    return render(request, 'ordonnance/print.html', {
        'ordonnance': ordonnance,
        'today': date.today(),
    })


@login_required(login_url='login')
def consultation_search(request):
    q = request.GET.get('q', '').strip()
    qs = (
        Consultation.objects
        .select_related('patient', 'medecin', 'rendez_vous')
        .order_by('-date_heure')
    )
    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(motif__icontains=q)
        )
    data = []
    for c in qs[:20]:
        dept = ''
        if c.rendez_vous and c.rendez_vous.departement == 'gynecologie_cpn':
            dept = 'gynecologie'
        data.append({
            'id':       c.pk,
            'numero':   c.numero,
            'patient':  f"{c.patient.nom} {c.patient.prenoms}",
            'date':     c.date_heure.strftime('%d/%m/%Y %H:%M'),
            'medecin':  str(c.medecin) if c.medecin else '',
            'motif':    c.motif[:60] if c.motif else '',
            'dept':     dept,
        })
    return JsonResponse({'results': data})


@login_required(login_url='login')
def medicament_search(request):
    q = request.GET.get('q', '').strip()
    qs = Medicament.objects.filter(actif=True).select_related('categorie')
    if q:
        qs = qs.filter(
            Q(designation__icontains=q) | Q(dci__icontains=q) | Q(code__icontains=q)
        )
    data = [
        {
            'id': m.pk,
            'designation': m.designation,
            'forme': m.get_forme_display(),
            'dosage': m.dosage or '',
            'stock': m.stock_actuel,
        }
        for m in qs[:25]
    ]
    return JsonResponse({'results': data})


@login_required(login_url='login')
def ordonnance_create(request, consultation_pk):
    consultation = get_object_or_404(
        Consultation.objects.select_related('patient', 'medecin'),
        pk=consultation_pk
    )

    if request.method == 'POST':
        type_ord  = request.POST.get('type_ordonnance', 'interne')
        date_exp  = request.POST.get('date_expiration') or None
        notes     = request.POST.get('notes', '').strip()

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            type_ordonnance=type_ord,
            date_expiration=date_exp,
            notes=notes,
        )

        med_ids      = request.POST.getlist('medicament_id[]')
        med_libres   = request.POST.getlist('medicament_libre[]')
        posologies   = request.POST.getlist('posologie[]')
        durees       = request.POST.getlist('duree[]')
        quantites    = request.POST.getlist('quantite[]')
        notes_lignes = request.POST.getlist('notes_ligne[]')

        for i, posologie in enumerate(posologies):
            if not posologie.strip():
                continue
            med_id    = med_ids[i]    if i < len(med_ids)      else ''
            med_libre = med_libres[i] if i < len(med_libres)   else ''
            qte_raw   = quantites[i]  if i < len(quantites)    else '1'
            try:
                qte = max(1, int(qte_raw))
            except (ValueError, TypeError):
                qte = 1

            ligne = LigneOrdonnance(
                ordonnance=ordonnance,
                posologie=posologie.strip(),
                duree=durees[i].strip() if i < len(durees) else '',
                quantite=qte,
                notes=notes_lignes[i].strip() if i < len(notes_lignes) else '',
                medicament_libre=med_libre.strip(),
            )
            if med_id:
                try:
                    ligne.medicament = Medicament.objects.get(pk=int(med_id))
                except (Medicament.DoesNotExist, ValueError):
                    pass
            ligne.save()

        messages.success(request, f'Ordonnance {ordonnance.numero} creee avec succes.')
        return redirect('ordonnance_detail', pk=ordonnance.pk)

    return render(request, 'ordonnance/form.html', {
        'consultation': consultation,
    })


@login_required(login_url='login')
def ordonnance_changer_statut(request, pk):
    if request.method != 'POST':
        return redirect('ordonnance_detail', pk=pk)
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    nouveau_statut = request.POST.get('statut', '')
    statuts_valides = [s[0] for s in Ordonnance.STATUT]
    if nouveau_statut in statuts_valides:
        ordonnance.statut = nouveau_statut
        ordonnance.save()
        messages.success(request, f'Statut mis a jour : {ordonnance.get_statut_display()}.')
    return redirect('ordonnance_detail', pk=pk)
