from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from .models import Patient, RendezVous, Pathologie, TypeVisite
from .forms import PatientForm, RendezVousForm, PathologieForm, TypeVisiteForm


@login_required
def patient_list(request):
    qs = Patient.objects.all()
    stats = {
        'total': qs.count(),
        'actifs': qs.filter(actif=True).count(),
        'nouveaux_30j': qs.filter(date_creation__gte=timezone.now() - timedelta(days=30)).count(),
    }

    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    sexe = request.GET.get('sexe', '')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)
    if sexe in ('M', 'F'):
        qs = qs.filter(sexe=sexe)

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'patients/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'statut': statut,
        'sexe': sexe,
        'total_filtre': qs.count(),
        'breadcrumb': [{'title': 'Patients'}],
    })


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    rdv_count = patient.rendez_vous.count()
    consultation_count = patient.consultations.count()
    facture_count = patient.factures.count()

    try:
        from consultations.models import Ordonnance
        ordonnance_count = Ordonnance.objects.filter(consultation__patient=patient).count()
    except Exception:
        ordonnance_count = 0

    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(patient=patient).count()
    except Exception:
        hospitalisation_count = 0

    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_examens_count = AnalyseLaboratoire.objects.filter(patient=patient).count()
        resultat_examens_count = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        demande_examens_count = 0
        resultat_examens_count = 0

    # Navigation précédent/suivant dans la liste ordonnée
    ids = list(Patient.objects.order_by('-date_creation').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'rdv_count': rdv_count,
        'consultation_count': consultation_count,
        'facture_count': facture_count,
        'ordonnance_count': ordonnance_count,
        'hospitalisation_count': hospitalisation_count,
        'demande_examens_count': demande_examens_count,
        'resultat_examens_count': resultat_examens_count,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            patient = form.save()
            messages.success(request, f'Patient {patient.nom} {patient.prenoms} enregistré avec le code {patient.code_patient}.')
            return redirect('patients:list')
    else:
        form = PatientForm()
    return render(request, 'patients/form.html', {'form': form, 'titre': 'Nouveau patient', 'edit': False})


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dossier patient mis à jour.')
            return redirect('patients:detail', pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, 'patients/form.html', {
        'form': form,
        'patient': patient,
        'titre': f'Modifier — {patient.nom} {patient.prenoms}',
        'edit': True,
    })


@login_required
def rdv_global_list(request):
    from datetime import date, datetime as dt

    today = date.today()
    q           = request.GET.get('q', '').strip()
    filter_val  = request.GET.get('filter', '')
    date_from_s = request.GET.get('date_from', '')
    date_to_s   = request.GET.get('date_to', '')

    qs = RendezVous.objects.select_related('patient', 'medecin', 'type_consultation').prefetch_related('registre_curatif').order_by('-date_heure')

    if q:
        qs = qs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(patient__code_patient__icontains=q)
        )

    if date_from_s or date_to_s:
        try:
            if date_from_s:
                qs = qs.filter(date_heure__date__gte=dt.strptime(date_from_s, '%Y-%m-%d').date())
            if date_to_s:
                qs = qs.filter(date_heure__date__lte=dt.strptime(date_to_s, '%Y-%m-%d').date())
        except ValueError:
            pass
    elif filter_val == 'mine':
        qs = qs.filter(date_heure__date=today)
        if hasattr(request.user, 'medecin'):
            qs = qs.filter(medecin=request.user.medecin)
    elif filter_val in ('planifie', 'confirme', 'termine', 'annule', 'absent'):
        qs = qs.filter(statut=filter_val)
    elif filter_val == 'not_done':
        qs = qs.filter(statut__in=['planifie', 'confirme'])
    else:
        # Par défaut (filter=today ou aucun paramètre) : rendez-vous du jour
        qs = qs.filter(date_heure__date=today)

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'patients/rendez_vous.html', {
        'page_obj': page_obj,
        'today':    today.isoformat(),
    })


@login_required
def patient_info_json(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return JsonResponse({'age': patient.age, 'telephone': patient.telephone})


@login_required
def patient_search_json(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'results': []})
    qs = Patient.objects.filter(
        Q(nom__icontains=q) | Q(prenoms__icontains=q) |
        Q(code_patient__icontains=q) | Q(telephone__icontains=q)
    ).order_by('nom', 'prenoms')[:20]
    results = [
        {
            'id': p.pk,
            'nom_complet': f"{p.nom} {p.prenoms}",
            'code': p.code_patient,
            'telephone': p.telephone or '',
            'actif': p.actif,
        }
        for p in qs
    ]
    return JsonResponse({'results': results})


@login_required
def rdv_create(request):
    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        patient_obj = None
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            rdv.save()
            messages.success(
                request,
                f'Rendez-vous créé pour {rdv.patient.nom} {rdv.patient.prenoms} '
                f'le {rdv.date_heure.strftime("%d/%m/%Y à %H:%M")}.'
            )
            action = request.POST.get('_action', '')
            if action == 'annuler':
                return redirect('patients:rdv_global')
            from django.urls import reverse
            return redirect(reverse('facture_create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
    else:
        initial = {'date_heure': timezone.now().strftime('%Y-%m-%dT%H:%M')}
        patient_pk = request.GET.get('patient')
        patient_obj = None
        if patient_pk:
            patient_obj = get_object_or_404(Patient, pk=patient_pk)
            initial['patient'] = patient_obj.pk
        form = RendezVousForm(initial=initial)
    return render(request, 'patients/rendez_vous_form.html', {
        'form':            form,
        'titre':           'Nouveau rendez-vous',
        'patient_prefill': patient_obj,
        'is_new':          True,
        'consultation':    None,
        'constante':       None,
        'pathologies':     Pathologie.objects.filter(actif=True).order_by('nom'),
    })


@login_required
def rdv_edit(request, pk):
    rdv = get_object_or_404(RendezVous, pk=pk)

    try:
        from facturation.models import Facture
        facture_payee = Facture.objects.filter(patient=rdv.patient, statut='payee').exists()
    except Exception:
        facture_payee = False

    # Consultation + constante liées à ce RDV
    consultation = None
    constante = None
    try:
        consultation = rdv.consultation
        try:
            constante = consultation.constantes
        except Exception:
            pass
    except Exception:
        pass

    if request.method == 'POST':
        action = request.POST.get('_action', '')

        if action == 'save_eval':
            _eval_map = {
                'eval_poids': 'poids',
                'eval_taille': 'taille',
                'eval_temperature': 'temperature',
                'eval_tension_systolique': 'tension_systolique',
                'eval_tension_diastolique': 'tension_diastolique',
                'eval_tension_systolique_droite': 'tension_systolique_droite',
                'eval_tension_diastolique_droite': 'tension_diastolique_droite',
                'eval_pouls': 'pouls',
                'eval_frequence_respiratoire': 'frequence_respiratoire',
                'eval_saturation_oxygene': 'saturation_oxygene',
                'eval_glycemie': 'glycemie',
                'eval_albumine': 'albumine',
                'eval_perimetre_brachial': 'perimetre_brachial',
                'eval_niveau_douleur': 'niveau_douleur',
            }
            from consultations.models import Consultation as Consult, Constante as Const
            try:
                consult_obj = rdv.consultation
            except Exception:
                consult_obj = None
            if consult_obj is None:
                consult_obj = Consult.objects.create(
                    patient=rdv.patient,
                    medecin=rdv.medecin,
                    rendez_vous=rdv,
                    motif=rdv.motif or 'Évaluation clinique',
                    cree_par=request.user,
                )
            const_obj, _ = Const.objects.get_or_create(consultation=consult_obj)
            for post_key, model_field in _eval_map.items():
                val = request.POST.get(post_key, '').strip()
                if val != '':
                    # Valeur soumise : mettre à jour
                    setattr(const_obj, model_field, val)
                # Valeur vide : conserver la valeur existante (ne pas écraser)
            const_obj.save()
            messages.success(request, 'Évaluation enregistrée.')
            from django.urls import reverse
            return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}))

        if action == 'confirmer':
            if facture_payee:
                from django.utils import timezone as tz
                rdv.statut = 'confirme'
                rdv.date_confirme = tz.now()
                rdv.save(update_fields=['statut', 'date_confirme'])
                messages.success(request, 'Rendez-vous confirmé.')
                from django.urls import reverse
                return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}))
            else:
                messages.error(request, 'Une facture payée est requise pour confirmer ce rendez-vous.')
            return redirect('patients:rdv_global')

        if action == 'en_attente':
            from django.utils import timezone as tz
            now = tz.now()
            rdv.statut = 'en_attente'
            rdv.date_en_attente = now
            if rdv.date_confirme:
                rdv.temps_constante_minutes = int((now - rdv.date_confirme).total_seconds() / 60)
            rdv.save(update_fields=['statut', 'date_en_attente', 'temps_constante_minutes'])
            messages.success(request, 'Rendez-vous mis en attente de consultation.')
            from django.urls import reverse
            return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}))

        if action == 'en_consultation':
            from django.utils import timezone as tz
            now = tz.now()
            rdv.statut = 'en_consultation'
            rdv.date_en_consultation = now
            if rdv.date_en_attente:
                rdv.temps_attente_minutes = int((now - rdv.date_en_attente).total_seconds() / 60)
            rdv.save(update_fields=['statut', 'date_en_consultation', 'temps_attente_minutes'])
            messages.success(request, 'Consultation démarrée.')
            from django.urls import reverse
            return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}))

        if action == 'terminer':
            from django.utils import timezone as tz
            now = tz.now()
            rdv.statut = 'termine'
            rdv.date_termine = now
            if rdv.date_en_consultation:
                rdv.temps_consultation_minutes = int((now - rdv.date_en_consultation).total_seconds() / 60)
            rdv.save(update_fields=['statut', 'date_termine', 'temps_consultation_minutes'])
            messages.success(request, 'Consultation terminée.')
            return redirect('patients:rdv_global')

        if action == 'annuler':
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])
            messages.success(request, 'Rendez-vous annulé.')
            return redirect('patients:rdv_global')

        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            rdv.save()

            from patients.utils import save_registres
            save_registres(request, rdv)

            # Sauvegarder l'évaluation clinique si des champs sont remplis
            _eval_map = {
                'eval_poids': 'poids',
                'eval_taille': 'taille',
                'eval_temperature': 'temperature',
                'eval_tension_systolique': 'tension_systolique',
                'eval_tension_diastolique': 'tension_diastolique',
                'eval_tension_systolique_droite': 'tension_systolique_droite',
                'eval_tension_diastolique_droite': 'tension_diastolique_droite',
                'eval_pouls': 'pouls',
                'eval_frequence_respiratoire': 'frequence_respiratoire',
                'eval_saturation_oxygene': 'saturation_oxygene',
                'eval_glycemie': 'glycemie',
                'eval_albumine': 'albumine',
                'eval_perimetre_brachial': 'perimetre_brachial',
            }
            if any(request.POST.get(k, '').strip() for k in _eval_map):
                from consultations.models import Consultation as Consult, Constante as Const
                try:
                    consult_obj = rdv.consultation
                except Exception:
                    consult_obj = None
                if consult_obj is None:
                    consult_obj = Consult.objects.create(
                        patient=rdv.patient,
                        medecin=rdv.medecin,
                        rendez_vous=rdv,
                        motif=rdv.motif or 'Évaluation clinique',
                        cree_par=request.user,
                    )
                const_obj, _ = Const.objects.get_or_create(consultation=consult_obj)
                for post_key, model_field in _eval_map.items():
                    val = request.POST.get(post_key, '').strip()
                    if val != '':
                        setattr(const_obj, model_field, val)
                const_obj.save()

            messages.success(request, 'Rendez-vous modifié.')
            if action == 'créer une facture':
                from django.urls import reverse
                return redirect(reverse('facture_create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
            return redirect('patients:rdv_global')
    else:
        form = RendezVousForm(instance=rdv)

    from patients.models import RegistreCPN, RegistreAccouchement, RegistrePostnatale, RegistreCuratif
    def _get_reg(Model):
        try:
            return Model.objects.get(rdv=rdv)
        except Model.DoesNotExist:
            return None

    return render(request, 'patients/rendez_vous_form.html', {
        'form':          form,
        'rdv':           rdv,
        'titre':         f'Rendez-vous — {rdv.patient.nom} {rdv.patient.prenoms}',
        'patient_prefill': rdv.patient,
        'facture_payee': facture_payee,
        'is_new':        False,
        'consultation':  consultation,
        'constante':     constante,
        'pathologies':   Pathologie.objects.filter(actif=True).order_by('nom'),
        'registre_cpn':          _get_reg(RegistreCPN),
        'registre_accouchement': _get_reg(RegistreAccouchement),
        'registre_postnatale':   _get_reg(RegistrePostnatale),
        'registre_curatif':      _get_reg(RegistreCuratif),
    })


@login_required
def rdv_edit(request, pk):
    from patients.models import RendezVous as RV
    rdv = get_object_or_404(RV, pk=pk)
    if request.method == 'POST':
        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rendez-vous mis à jour.')
            return redirect('patients:rdv_global')
    else:
        form = RendezVousForm(instance=rdv)
    return render(request, 'patients/rendez_vous_form.html', {
        'form':  form,
        'titre': 'Modifier le rendez-vous',
        'rdv':   rdv,
    })


@login_required
def gynecologie_rdv_list(request):
    from datetime import date as _date

    q          = request.GET.get('q', '').strip()
    filter_val = request.GET.get('filter', '')
    group_val  = request.GET.get('group', '')
    date_from  = request.GET.get('date_from', '')
    date_to    = request.GET.get('date_to', '')

    qs = RendezVous.objects.select_related('patient', 'medecin', 'type_consultation').prefetch_related('registre_curatif').filter(
        departement='gynecologie_cpn'
    ).order_by('-date_heure')

    if q:
        qs = qs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(patient__code_patient__icontains=q)
        )

    if filter_val == 'today':
        qs = qs.filter(date_heure__date=_date.today())
    elif filter_val == 'mine':
        qs = qs.filter(medecin__user=request.user)
    elif filter_val == 'not_done':
        qs = qs.exclude(statut__in=['termine', 'annule', 'absent'])

    if date_from:
        try:
            qs = qs.filter(date_heure__date__gte=date_from)
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            qs = qs.filter(date_heure__date__lte=date_to)
        except (ValueError, TypeError):
            pass

    if group_val in ('date_jour', 'date_semaine', 'date_mois', 'date_annee'):
        qs = qs.order_by('date_heure')
    elif group_val == 'statut':
        qs = qs.order_by('statut', '-date_heure')
    elif group_val in ('medecin', 'referent'):
        qs = qs.order_by('medecin', '-date_heure')
    elif group_val == 'patient':
        qs = qs.order_by('patient__nom', 'patient__prenoms')

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'gynecologie/rdv.html', {'page_obj': page_obj})


@login_required
def gynecologie_patient_list(request):
    gyne_ids = RendezVous.objects.filter(
        departement='gynecologie_cpn'
    ).values_list('patient_id', flat=True).distinct()

    qs = Patient.objects.filter(pk__in=gyne_ids).order_by('nom', 'prenoms')

    q          = request.GET.get('q', '').strip()
    filter_val = request.GET.get('filter', '')
    group_val  = request.GET.get('group', '')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )
    if filter_val == 'femme':
        qs = qs.filter(sexe='F')
    elif filter_val == 'homme':
        qs = qs.filter(sexe='M')

    if group_val == 'sexe':
        qs = qs.order_by('sexe', 'nom', 'prenoms')
    elif group_val == 'age':
        qs = qs.order_by('date_naissance')

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'gynecologie/list.html', {'page_obj': page_obj})


@login_required
def patient_rdv_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    items = patient.rendez_vous.select_related('medecin').order_by('-date_heure')
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'rdv',
        'titre': 'Rendez-vous',
        'items': items,
    })


@login_required
def patient_consultation_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from consultations.models import Consultation
        items = Consultation.objects.filter(patient=patient).select_related('medecin').order_by('-date_heure')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'consultation',
        'titre': 'Consultations',
        'items': items,
    })


@login_required
def patient_ordonnance_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from consultations.models import Ordonnance
        items = Ordonnance.objects.filter(
            consultation__patient=patient
        ).select_related('consultation').order_by('-date_emission')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'ordonnance',
        'titre': 'Ordonnances',
        'items': items,
    })


@login_required
def patient_hospitalisation_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from hospitalisation.models import Hospitalisation
        items = Hospitalisation.objects.filter(patient=patient).select_related(
            'medecin_traitant', 'chambre'
        ).order_by('-date_admission')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'hospitalisation',
        'titre': 'Hospitalisations',
        'items': items,
    })


@login_required
def patient_demande_examens_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from laboratoire.models import AnalyseLaboratoire
        items = AnalyseLaboratoire.objects.filter(patient=patient).order_by('-date_prelevement')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'demande_examens',
        'titre': "Demandes d'examens de laboratoire",
        'items': items,
    })


@login_required
def patient_resultat_examens_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from laboratoire.models import AnalyseLaboratoire
        items = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['résultat', 'validé', 'envoyé']
        ).order_by('-date_resultat')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'resultat_examens',
        'titre': "Résultats d'examens de laboratoire",
        'items': items,
    })


@login_required
def ordonnance_create(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    from consultations.models import Consultation as Consult, Ordonnance, LigneOrdonnance

    consultation = None
    consultation_pk = request.GET.get('consultation') or request.POST.get('consultation_id')
    rdv_pk = request.GET.get('rdv') or request.POST.get('rdv_id')

    if consultation_pk:
        consultation = get_object_or_404(Consult, pk=consultation_pk)
    elif rdv_pk:
        rdv_obj = get_object_or_404(RendezVous, pk=rdv_pk)
        try:
            consultation = rdv_obj.consultation
        except Exception:
            consultation = Consult.objects.create(
                patient=patient,
                medecin=rdv_obj.medecin,
                rendez_vous=rdv_obj,
                motif=rdv_obj.motif or 'Consultation',
                cree_par=request.user,
            )

    if request.method == 'POST':
        if consultation is None:
            messages.error(request, "Impossible de créer une ordonnance sans consultation associée.")
            return redirect('patients:ordonnance_list', pk=pk)

        notes = request.POST.get('notes', '')
        date_expiration = request.POST.get('date_expiration') or None
        statut = request.POST.get('statut', 'emise')
        type_ordonnance = request.POST.get('type_ordonnance', 'interne')

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            notes=notes,
            date_expiration=date_expiration,
            statut=statut,
            type_ordonnance=type_ordonnance,
        )

        medicaments = request.POST.getlist('medicament[]')
        medicaments_libres = request.POST.getlist('medicament_libre[]')
        posologies = request.POST.getlist('posologie[]')
        durees = request.POST.getlist('duree[]')
        quantites = request.POST.getlist('quantite[]')

        for i, posologie in enumerate(posologies):
            if not posologie.strip():
                continue
            med_id = medicaments[i] if i < len(medicaments) else ''
            med_libre = medicaments_libres[i] if i < len(medicaments_libres) else ''
            duree = durees[i] if i < len(durees) else ''
            quantite_val = quantites[i] if i < len(quantites) else '1'
            try:
                quantite = int(quantite_val)
            except (ValueError, TypeError):
                quantite = 1

            ligne = LigneOrdonnance(
                ordonnance=ordonnance,
                posologie=posologie,
                medicament_libre=med_libre,
                duree=duree,
                quantite=quantite,
            )
            if med_id:
                try:
                    ligne.medicament_id = int(med_id)
                except (ValueError, TypeError):
                    pass
            ligne.save()

        messages.success(request, f"Ordonnance {ordonnance.numero} créée avec succès.")
        return redirect('patients:ordonnance_list', pk=pk)

    try:
        from pharmacie.models import Medicament
        medicaments_dispo = list(Medicament.objects.filter(actif=True).values('pk', 'designation', 'dosage', 'forme'))
    except Exception:
        medicaments_dispo = []

    return render(request, 'pharmacie/ordonnance_create.html', {
        'patient': patient,
        'consultation': consultation,
        'medicaments_dispo': medicaments_dispo,
        'titre': 'Créer une ordonnance',
        'statuts': [('emise', 'Émise'), ('delivree', 'Délivrée'), ('partielle', 'Partielle'), ('expiree', 'Expirée')],
        'types': [('interne', 'Interne'), ('externe', 'Externe')],
    })


@login_required
def pathologie_list(request):
    qs = Pathologie.objects.all()
    q  = request.GET.get('q', '').strip()

    if q:
        qs = qs.filter(nom__icontains=q)

    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'patients/pathologie_list.html', {
        'page_obj': page_obj,
        'q':        q,
        'total':    qs.count(),
    })


@login_required
def pathologie_create(request):
    if request.method == 'POST':
        form = PathologieForm(request.POST)
        if form.is_valid():
            p = form.save()
            messages.success(request, f'Pathologie "{p.nom}" enregistrée.')
            return redirect('patients:pathologie_list')
    else:
        form = PathologieForm()
    return render(request, 'patients/pathologie_form.html', {
        'form': form, 'titre': 'Nouvelle pathologie', 'edit': False,
    })


@login_required
def pathologie_edit(request, pk):
    pathologie = get_object_or_404(Pathologie, pk=pk)
    if request.method == 'POST':
        form = PathologieForm(request.POST, instance=pathologie)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pathologie mise à jour.')
            return redirect('patients:pathologie_list')
    else:
        form = PathologieForm(instance=pathologie)
    return render(request, 'patients/pathologie_form.html', {
        'form': form, 'titre': 'Modifier la pathologie', 'edit': True, 'object': pathologie,
    })


@login_required
def pathologie_delete(request, pk):
    pathologie = get_object_or_404(Pathologie, pk=pk)
    if request.method == 'POST':
        nom = pathologie.nom
        pathologie.delete()
        messages.success(request, f'Pathologie "{nom}" supprimée.')
    return redirect('patients:pathologie_list')


@login_required
def typevisite_list(request):
    qs = TypeVisite.objects.all()
    q  = request.GET.get('q', '').strip()

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))

    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'patients/typevisite_list.html', {
        'page_obj': page_obj,
        'q':        q,
        'total':    qs.count(),
    })


@login_required
def typevisite_create(request):
    if request.method == 'POST':
        form = TypeVisiteForm(request.POST)
        if form.is_valid():
            tv = form.save()
            messages.success(request, f'Type de visite "{tv.nom}" enregistré.')
            return redirect('patients:typevisite_list')
    else:
        form = TypeVisiteForm()
    return render(request, 'patients/typevisite_form.html', {
        'form': form, 'titre': 'Nouveau type de visite', 'edit': False,
    })


@login_required
def typevisite_edit(request, pk):
    tv = get_object_or_404(TypeVisite, pk=pk)
    if request.method == 'POST':
        form = TypeVisiteForm(request.POST, instance=tv)
        if form.is_valid():
            form.save()
            messages.success(request, 'Type de visite mis à jour.')
            return redirect('patients:typevisite_list')
    else:
        form = TypeVisiteForm(instance=tv)
    return render(request, 'patients/typevisite_form.html', {
        'form': form, 'titre': 'Modifier le type de visite', 'edit': True, 'object': tv,
    })


@login_required
def typevisite_delete(request, pk):
    tv = get_object_or_404(TypeVisite, pk=pk)
    if request.method == 'POST':
        nom = tv.nom
        tv.delete()
        messages.success(request, f'Type de visite "{nom}" supprimé.')
    return redirect('patients:typevisite_list')
