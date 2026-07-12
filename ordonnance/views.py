from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator

import json

from consultations.models import Ordonnance, LigneOrdonnance, Consultation
from pharmacie.models import Medicament
from stock.models import Produit
from patients.models import Patient
from medecins.models import Medecin


@login_required(login_url='login')
def ordonnance_list(request):
    qs = Ordonnance.objects.select_related(
        'consultation__patient', 'consultation__medecin', 'medecin', 'patient'
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

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'pharmacie/ordonnance/ordonnance_list.html', {
        'page_obj': page_obj,
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
            'consultation__patient', 'consultation__medecin', 'patient'
        ).prefetch_related('lignes__produit', 'lignes__medicament'),
        pk=pk
    )
    patient = ordonnance.patient or (
        ordonnance.consultation.patient if ordonnance.consultation else None
    )
    return render(request, 'pharmacie/ordonnance/ordonnance_detail.html', {
        'ordonnance': ordonnance,
        'patient':    patient,
        'today':      date.today(),
    })


@login_required(login_url='login')
def ordonnance_print(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__patient', 'consultation__medecin'
        ).prefetch_related('lignes__medicament'),
        pk=pk
    )
    return render(request, 'pharmacie/ordonnance/print.html', {
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
        if c.rendez_vous and c.rendez_vous.departement and c.rendez_vous.departement.modules_specialises.filter(code='gynecologie').exists():
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

    types = Ordonnance._meta.get_field('type_ordonnance').choices

    medecins = Medecin.objects.select_related('specialite', 'employe').order_by('employe__nom')

    if request.method == 'POST':
        type_ord   = request.POST.get('type_ordonnance', 'interne')
        date_exp   = request.POST.get('date_expiration') or None
        notes      = request.POST.get('notes', '').strip()
        medecin_id = request.POST.get('medecin_id', '').strip()

        medecin = None
        if medecin_id:
            try:
                medecin = Medecin.objects.get(pk=int(medecin_id))
            except (Medecin.DoesNotExist, ValueError):
                pass
        if medecin is None and consultation.medecin:
            medecin = consultation.medecin

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            medecin=medecin,
            type_ordonnance=type_ord,
            date_expiration=date_exp,
            notes=notes,
        )

        med_ids    = request.POST.getlist('medicament[]')
        med_libres = request.POST.getlist('medicament_libre[]')
        posologies = request.POST.getlist('posologie[]')
        durees     = request.POST.getlist('duree[]')
        quantites  = request.POST.getlist('quantite[]')

        for i, posologie in enumerate(posologies):
            if not posologie.strip():
                continue
            med_id    = med_ids[i]    if i < len(med_ids)    else ''
            med_libre = med_libres[i] if i < len(med_libres) else ''
            qte_raw   = quantites[i]  if i < len(quantites)  else '1'
            try:
                qte = max(1, int(qte_raw))
            except (ValueError, TypeError):
                qte = 1

            ligne = LigneOrdonnance(
                ordonnance=ordonnance,
                posologie=posologie.strip(),
                duree=durees[i].strip() if i < len(durees) else '',
                quantite=qte,
                medicament_libre=med_libre.strip(),
            )
            if med_id:
                try:
                    ligne.produit = Produit.objects.get(pk=int(med_id), type='medicament')
                    ligne.medicament_libre = ''
                except (Produit.DoesNotExist, ValueError):
                    pass
            ligne.save()

        messages.success(request, f'Ordonnance {ordonnance.numero} créée avec succès.')
        return redirect('ordonnance_detail', pk=ordonnance.pk)

    return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
        'consultation':      consultation,
        'patient':           consultation.patient,
        'medecin_preselect': consultation.medecin,
        'medecins':          medecins,
        'types':             types,
        'medicaments_dispo': _medicaments_dispo_json(),
    })


def _medicaments_dispo_json():
    produits = Produit.objects.filter(type='medicament', actif=True).order_by('nom')
    return json.dumps([
        {
            'pk': p.pk,
            'designation': p.nom,
            'forme': p.get_forme_display() if p.forme else '',
            'dosage': p.dosage or '',
            'dci': p.dci or '',
            'stock_actuel': float(p.stock_actuel),
            'stock_alerte': float(p.stock_alerte),
            'stock_minimum': float(p.stock_minimum),
        }
        for p in produits
    ])


@login_required(login_url='login')
def ordonnance_create_libre(request):
    """Create an ordonnance directly from the pharmacy list, without a pre-existing consultation."""
    types = Ordonnance._meta.get_field('type_ordonnance').choices
    medecins = Medecin.objects.select_related('specialite', 'employe').order_by('employe__nom')

    patient = None
    consultation = None
    medecin_preselect = None
    patient_id_get = request.GET.get('patient_id')
    consultation_id_get = request.GET.get('consultation_id')
    medecin_id_get = request.GET.get('medecin_id')
    if consultation_id_get:
        consultation = get_object_or_404(Consultation.objects.select_related('patient', 'medecin'), pk=consultation_id_get)
        patient = consultation.patient
        medecin_preselect = consultation.medecin
    elif patient_id_get:
        patient = get_object_or_404(Patient, pk=patient_id_get)
    if medecin_id_get and medecin_preselect is None:
        try:
            medecin_preselect = Medecin.objects.get(pk=int(medecin_id_get))
        except (Medecin.DoesNotExist, ValueError):
            pass

    initial_lignes = []
    from_ordonnance_pk = request.GET.get('from_ordonnance')
    if from_ordonnance_pk:
        try:
            src = Ordonnance.objects.prefetch_related('lignes__produit', 'lignes__medicament').get(pk=from_ordonnance_pk)
            if patient is None:
                patient = src.patient or (src.consultation.patient if src.consultation else None)
            for lg in src.lignes.select_related('produit', 'medicament').all():
                initial_lignes.append({
                    'med_id':    lg.produit_id or lg.medicament_id or '',
                    'med_nom':   lg.produit.nom if lg.produit else (lg.medicament.designation if lg.medicament else (lg.medicament_libre or '')),
                    'posologie': lg.posologie or '',
                    'duree':     lg.duree or '',
                    'quantite':  lg.quantite,
                })
        except Ordonnance.DoesNotExist:
            pass

    if request.method == 'POST':
        type_ord   = request.POST.get('type_ordonnance', 'interne')
        date_exp   = request.POST.get('date_expiration') or None
        notes      = request.POST.get('notes', '').strip()
        consultation_id = request.POST.get('consultation_id', '').strip()
        patient_id      = request.POST.get('patient_id', '').strip()
        medecin_id_post = request.POST.get('medecin_id', '').strip()

        if consultation_id:
            consultation = get_object_or_404(Consultation.objects.select_related('patient', 'medecin'), pk=consultation_id)
            patient = consultation.patient
        elif patient_id:
            patient = get_object_or_404(Patient, pk=patient_id)
            consultation = None
        else:
            messages.error(request, 'Veuillez sélectionner un patient.')
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'types': types,
                'medecins': medecins,
                'medicaments_dispo': _medicaments_dispo_json(),
            })

        if not medecin_id_post:
            messages.error(request, 'Veuillez sélectionner le médecin prescripteur.')
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'types': types,
                'medecins': medecins,
                'patient': patient,
                'consultation': consultation,
                'medecin_preselect': medecin_preselect,
                'medicaments_dispo': _medicaments_dispo_json(),
            })

        medecin = None
        try:
            medecin = Medecin.objects.get(pk=int(medecin_id_post))
        except (Medecin.DoesNotExist, ValueError):
            pass

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            patient=patient if not consultation else None,
            medecin=medecin,
            type_ordonnance=type_ord,
            date_expiration=date_exp,
            notes=notes,
        )

        med_ids     = request.POST.getlist('medicament[]')
        med_libres  = request.POST.getlist('medicament_libre[]')
        posologies  = request.POST.getlist('posologie[]')
        durees      = request.POST.getlist('duree[]')
        quantites   = request.POST.getlist('quantite[]')

        for i, posologie in enumerate(posologies):
            med_id    = med_ids[i] if i < len(med_ids) else ''
            med_libre = med_libres[i].strip() if i < len(med_libres) else ''
            if not posologie.strip() and not med_id and not med_libre:
                continue
            qte_raw   = quantites[i] if i < len(quantites) else '1'
            try:
                qte = max(1, int(qte_raw))
            except (ValueError, TypeError):
                qte = 1

            ligne = LigneOrdonnance(
                ordonnance=ordonnance,
                posologie=posologie.strip(),
                duree=durees[i].strip() if i < len(durees) else '',
                quantite=qte,
            )
            if med_id:
                try:
                    ligne.produit = Produit.objects.get(pk=int(med_id), type='medicament')
                except (Produit.DoesNotExist, ValueError):
                    ligne.medicament_libre = med_libre
            elif med_libre:
                ligne.medicament_libre = med_libre
            ligne.save()

        messages.success(request, f'Ordonnance {ordonnance.numero} créée avec succès.')
        return redirect('ordonnance_detail', pk=ordonnance.pk)

    return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
        'consultation':      consultation,
        'patient':           patient,
        'medecin_preselect': medecin_preselect,
        'medecins':          medecins,
        'types':             types,
        'medicaments_dispo': _medicaments_dispo_json(),
        'initial_lignes':    initial_lignes,
    })


@login_required(login_url='login')
def ordonnance_changer_statut(request, pk):
    if request.method != 'POST':
        return redirect('ordonnance_detail', pk=pk)
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    nouveau_statut = request.POST.get('statut', '')
    statuts_valides = [s[0] for s in Ordonnance.STATUT]
    if nouveau_statut in statuts_valides:
        ancien_statut = ordonnance.statut
        ordonnance.statut = nouveau_statut
        ordonnance.save()


        messages.success(request, f'Statut mis a jour : {ordonnance.get_statut_display()}.')
    return redirect('ordonnance_detail', pk=pk)
