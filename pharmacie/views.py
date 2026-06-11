from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q


@login_required
def ordonnance_create(request):
    from consultations.models import Ordonnance, LigneOrdonnance, Consultation as Consult
    from patients.models import Patient

    try:
        from pharmacie.models import Medicament
        medicaments_dispo = list(
            Medicament.objects.filter(actif=True).values(
                'pk', 'designation', 'dosage', 'forme',
                'stock_actuel', 'stock_alerte', 'stock_minimum'
            )
        )
    except Exception:
        medicaments_dispo = []

    ctx = {
        'patient': None,
        'consultation': None,
        'medicaments_dispo': medicaments_dispo,
        'titre': 'Créer une ordonnance',
        'statuts': [('emise', 'Émise'), ('delivree', 'Délivrée'), ('partielle', 'Partielle'), ('expiree', 'Expirée')],
        'types': [('interne', 'Interne'), ('externe', 'Externe')],
    }

    if request.method == 'POST':
        patient_pk = request.POST.get('patient_id') or request.POST.get('consultation_id')
        consultation_pk = request.POST.get('consultation_id')

        consultation = None
        patient = None

        if consultation_pk:
            try:
                consultation = Consult.objects.get(pk=consultation_pk)
                patient = consultation.patient
            except Consult.DoesNotExist:
                pass

        if patient is None and patient_pk:
            try:
                patient = Patient.objects.get(pk=patient_pk)
            except Patient.DoesNotExist:
                messages.error(request, "Patient introuvable.")
                return render(request, 'pharmacie/ordonnance_create.html', ctx)

        if patient is None:
            messages.error(request, "Veuillez sélectionner un patient.")
            return render(request, 'pharmacie/ordonnance_create.html', ctx)

        if consultation is None:
            consultation = Consult.objects.create(
                patient=patient,
                medecin=None,
                motif='Ordonnance pharmacie',
                cree_par=request.user,
            )

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            notes=request.POST.get('notes', ''),
            date_expiration=request.POST.get('date_expiration') or None,
            statut=request.POST.get('statut', 'emise'),
            type_ordonnance=request.POST.get('type_ordonnance', 'interne'),
        )

        posologies = request.POST.getlist('posologie[]')
        medicaments = request.POST.getlist('medicament[]')
        medicaments_libres = request.POST.getlist('medicament_libre[]')
        durees = request.POST.getlist('duree[]')
        quantites = request.POST.getlist('quantite[]')

        for i in range(len(posologies)):
            posologie = posologies[i].strip() if i < len(posologies) else ''
            med_id = medicaments[i] if i < len(medicaments) else ''
            med_libre = medicaments_libres[i] if i < len(medicaments_libres) else ''
            if not posologie and not med_id and not med_libre:
                continue
            ligne = LigneOrdonnance(
                ordonnance=ordonnance,
                posologie=posologie,
                medicament_libre=med_libre,
                duree=durees[i] if i < len(durees) else '',
                quantite=int(quantites[i]) if i < len(quantites) and quantites[i].isdigit() else 1,
            )
            if med_id:
                try:
                    ligne.medicament_id = int(med_id)
                except (ValueError, TypeError):
                    pass
            ligne.save()

        messages.success(request, f"Ordonnance {ordonnance.numero} créée avec succès.")
        return redirect('pharmacie:ordonnance_detail', pk=ordonnance.pk)

    return render(request, 'pharmacie/ordonnance_create.html', ctx)


@login_required
def ordonnance_detail(request, pk):
    from consultations.models import Ordonnance
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__patient', 'consultation__medecin'
        ).prefetch_related('lignes__medicament'),
        pk=pk
    )
    return render(request, 'pharmacie/ordonnance_detail.html', {'ordonnance': ordonnance})


@login_required
def ordonnance_list(request):
    from consultations.models import Ordonnance

    qs = Ordonnance.objects.select_related(
        'consultation__patient', 'consultation__medecin'
    ).order_by('-date_emission')

    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    type_ord = request.GET.get('type', '').strip()

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

    stats = {
        'total': Ordonnance.objects.count(),
        'emises': Ordonnance.objects.filter(statut='emise').count(),
        'delivrees': Ordonnance.objects.filter(statut='delivree').count(),
        'expirees': Ordonnance.objects.filter(statut='expiree').count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'pharmacie/ordonnance_list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'statut_filtre': statut,
        'type_filtre': type_ord,
        'titre': 'Ordonnances',
    })
