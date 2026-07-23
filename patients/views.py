from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from .models import Patient, RendezVous, Pathologie
from .forms import PatientForm, RendezVousForm, PathologieForm, TypeVisiteForm
from medecins.models import Medecin
from core.views import log_event
from gynecologie.models import TypeVisite


def _age_bracket_label(patient, today):
    if patient.date_naissance > today.replace(year=today.year - 18):
        return 'Mineurs (< 18 ans)'
    if patient.date_naissance > today.replace(year=today.year - 60):
        return 'Adultes (18–60 ans)'
    return 'Seniors (> 60 ans)'


@login_required
def patient_list(request):
    from datetime import date
    qs = Patient.objects.all()
    stats = {
        'total':        qs.count(),
        'nouveaux_30j': qs.filter(date_creation__gte=timezone.now() - timedelta(days=30)).count(),
        'femmes':       qs.filter(sexe='F').count(),
        'hommes':       qs.filter(sexe='M').count(),
    }

    q       = request.GET.get('q', '').strip()
    filters = request.GET.getlist('filter')
    groups  = request.GET.getlist('group')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )

    if 'nouveau' in filters:
        qs = qs.filter(date_creation__gte=timezone.now() - timedelta(days=30))

    sexe_map = {'femme': 'F', 'homme': 'M'}
    sexes_selectionnes = [sexe_map[f] for f in filters if f in sexe_map]
    if sexes_selectionnes:
        qs = qs.filter(sexe__in=sexes_selectionnes)

    today = date.today()
    tranches_selectionnees = [f for f in filters if f in ('mineur', 'adulte', 'senior')]
    if tranches_selectionnees:
        age_q = Q()
        if 'mineur' in tranches_selectionnees:
            age_q |= Q(date_naissance__gt=today.replace(year=today.year - 18))
        if 'adulte' in tranches_selectionnees:
            age_q |= Q(
                date_naissance__lte=today.replace(year=today.year - 18),
                date_naissance__gt=today.replace(year=today.year - 60),
            )
        if 'senior' in tranches_selectionnees:
            age_q |= Q(date_naissance__lte=today.replace(year=today.year - 60))
        qs = qs.filter(age_q)

    # ── Regroupement (cumulable : Genre + Âge) ──────────────────────────────
    # Pas de vraie structure imbriquée : on trie pour que les groupes soient
    # contigus, puis on marque le premier élément de chaque nouveau groupe
    # d'un en-tête de section combiné (ex. "Féminin — Adultes (18–60 ans)"),
    # avec le total réel du groupe (toutes pages confondues, pas juste la page
    # courante) — calculé côté base via une agrégation groupée.
    group_counts = {}
    if groups:
        from django.db.models import Case, When, Value, CharField, Count
        annotations = {}
        values_fields = []
        if 'sexe' in groups:
            values_fields.append('sexe')
        if 'age' in groups:
            annotations['age_bracket'] = Case(
                When(date_naissance__gt=today.replace(year=today.year - 18), then=Value('Mineurs (< 18 ans)')),
                When(date_naissance__gt=today.replace(year=today.year - 60), then=Value('Adultes (18–60 ans)')),
                default=Value('Seniors (> 60 ans)'),
                output_field=CharField(),
            )
            values_fields.append('age_bracket')
        rows = qs.annotate(**annotations).order_by().values(*values_fields).annotate(n=Count('id'))
        sexe_labels = dict(Patient.SEXE)
        for row in rows:
            parts = []
            if 'sexe' in groups:
                parts.append(sexe_labels.get(row['sexe'], row['sexe']))
            if 'age' in groups:
                parts.append(row['age_bracket'])
            group_counts[' — '.join(parts)] = row['n']

    ordering = []
    if 'sexe' in groups:
        ordering.append('sexe')
    if 'age' in groups:
        ordering.append('-date_naissance')
    if ordering:
        qs = qs.order_by(*ordering)

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    if groups:
        prev_key = None
        group_index = -1
        for p in page_obj:
            parts = []
            if 'sexe' in groups:
                parts.append(p.get_sexe_display())
            if 'age' in groups:
                parts.append(_age_bracket_label(p, today))
            key = ' — '.join(parts)
            if key != prev_key:
                group_index += 1
                p.group_header = key
                p.group_count = group_counts.get(key, 0)
            p.group_id = group_index
            prev_key = key

    return render(request, 'patients/list.html', {
        'page_obj':     page_obj,
        'stats':        stats,
        'q':            q,
        'filters':      filters,
        'groups':       groups,
        'total_filtre': qs.count(),
        'breadcrumb':   [{'title': 'Patients'}],
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
        from laboratoire.models import DemandeExamen, AnalyseLaboratoire
        demande_examens_count = DemandeExamen.objects.filter(patient=patient).count()
        resultat_examens_count = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['resultat', 'valide', 'envoye']
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
    filter_val  = request.GET.get('filter', 'today')
    date_from_s = request.GET.get('date_from', '')
    date_to_s   = request.GET.get('date_to', '')

    base_qs = RendezVous.objects.select_related('patient', 'medecin', 'type_consultation')

    # Stats du jour (toujours calculées sur aujourd'hui)
    today_qs = base_qs.filter(date_heure__date=today)
    stats = {
        'aujourd_hui': today_qs.count(),
        'planifie':    today_qs.filter(statut='planifie').count(),
        'confirme':    today_qs.filter(statut='confirme').count(),
        'termine':     today_qs.filter(statut='termine').count(),
        'annule':      today_qs.filter(statut__in=['annule', 'absent']).count(),
        'total':       base_qs.count(),
    }

    qs = base_qs.prefetch_related('registre_curatif').order_by('-date_heure')

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
    elif filter_val == 'all':
        pass  # pas de filtre date
    elif filter_val in ('planifie', 'confirme', 'termine', 'annule', 'absent'):
        qs = qs.filter(statut=filter_val)
    elif filter_val == 'not_done':
        qs = qs.filter(statut__in=['planifie', 'confirme'])
    else:
        qs = qs.filter(date_heure__date=today).exclude(statut='termine')

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'patients/rendez_vous.html', {
        'page_obj':    page_obj,
        'today':       today.isoformat(),
        'stats':       stats,
        'filter_val':  filter_val,
        'q':           q,
        'date_from':   date_from_s,
        'date_to':     date_to_s,
    })


@login_required
def patient_info_json(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return JsonResponse({'age': patient.age, 'telephone': patient.telephone})


@login_required
def patient_search_json(request):
    def _to_dict(p):
        return {
            'id': p.pk,
            'nom_complet': f"{p.nom} {p.prenoms}",
            'code': p.code_patient,
            'telephone': p.telephone or '',
            'age': p.age,
            'sexe_display': p.get_sexe_display(),
            'adresse': p.adresse or '',
            'assurance_nom': p.assurance.nom if p.assurance_id else '',
        }

    pk = request.GET.get('id', '').strip()
    if pk:
        try:
            p = Patient.objects.select_related('assurance').get(pk=int(pk))
            return JsonResponse({'results': [_to_dict(p)]})
        except (Patient.DoesNotExist, ValueError):
            return JsonResponse({'results': []})

    q = request.GET.get('q', '').strip()
    base_qs = Patient.objects.select_related('assurance').order_by('nom', 'prenoms')
    if not q:
        qs = base_qs[:20]
    elif len(q) < 2:
        return JsonResponse({'results': []})
    else:
        qs = base_qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )[:20]
    return JsonResponse({'results': [_to_dict(p) for p in qs]})


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
            rdv._skip_auto_log = True
            rdv.save()
            log_event(rdv, request.user, 'Rendez-vous créé.', type='system')
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
        'medecins':        Medecin.objects.filter(actif=True).select_related('employe').order_by('employe__nom', 'employe__prenoms'),
    })


@login_required
def rdv_edit(request, pk):
    rdv = get_object_or_404(RendezVous, pk=pk)

    try:
        from facturation.models import Facture
        facture_payee = Facture.objects.filter(
            Q(rendez_vous=rdv) | Q(patient=rdv.patient, statut='payee')
        ).exclude(statut='annulee').exists()
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
            # Sauvegarder le médecin sélectionné dans le modal
            medecin_pk = request.POST.get('eval_medecin', '').strip()
            if medecin_pk:
                try:
                    rdv.medecin = Medecin.objects.get(pk=medecin_pk)
                    rdv.save(update_fields=['medecin'])
                except Exception:
                    pass

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
                    setattr(const_obj, model_field, val)
            const_obj.save()
            messages.success(request, 'Évaluation enregistrée. Sélectionnez un médecin et cliquez sur « En Attente » pour continuer.')
            from django.urls import reverse
            return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}) + '?edit=1')

        if action == 'confirmer':
            if facture_payee:
                from django.utils import timezone as tz
                rdv.statut = 'confirme'
                rdv.date_confirme = tz.now()
                rdv._skip_auto_log = True
                rdv.save(update_fields=['statut', 'date_confirme'])
                log_event(rdv, request.user, 'État : Brouillon → Confirmer', type='statut')
                messages.success(request, 'Rendez-vous confirmé.')
                return redirect('patients:rdv_global')
            else:
                messages.error(request, 'Une facture est requise pour confirmer ce rendez-vous.')
                return redirect('patients:rdv_global')

        if action == 'en_attente':
            from django.utils import timezone as tz
            now = tz.now()
            rdv.statut = 'en_attente'
            rdv.date_en_attente = now
            if rdv.date_confirme:
                rdv.temps_constante_minutes = int((now - rdv.date_confirme).total_seconds() / 60)
            rdv.duree_minutes = rdv.temps_constante_minutes + rdv.temps_attente_minutes + rdv.temps_consultation_minutes
            update_fields = ['statut', 'date_en_attente', 'temps_constante_minutes', 'duree_minutes']
            medecin_pk = request.POST.get('medecin', '').strip()
            if medecin_pk:
                try:
                    rdv.medecin = Medecin.objects.get(pk=medecin_pk)
                    update_fields.append('medecin')
                except Exception:
                    pass
            rdv._skip_auto_log = True
            rdv.save(update_fields=update_fields)
            log_event(rdv, request.user, 'État : Confirmer → En Attente', type='statut')
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
            rdv.duree_minutes = rdv.temps_constante_minutes + rdv.temps_attente_minutes + rdv.temps_consultation_minutes
            rdv._skip_auto_log = True
            rdv.save(update_fields=['statut', 'date_en_consultation', 'temps_attente_minutes', 'duree_minutes'])
            log_event(rdv, request.user, 'État : En Attente → En Consultation', type='statut')
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
            rdv.duree_minutes = rdv.temps_constante_minutes + rdv.temps_attente_minutes + rdv.temps_consultation_minutes
            rdv._skip_auto_log = True
            rdv.save(update_fields=['statut', 'date_termine', 'temps_consultation_minutes', 'duree_minutes'])
            log_event(rdv, request.user, 'État : En Consultation → Terminé', type='statut')
            messages.success(request, 'Consultation terminée.')
            return redirect('patients:rdv_global')

        if action == 'annuler':
            rdv.statut = 'annule'
            rdv._skip_auto_log = True
            rdv.save(update_fields=['statut'])
            log_event(rdv, request.user, 'Rendez-vous annulé.', type='statut')
            messages.success(request, 'Rendez-vous annulé.')
            return redirect('patients:rdv_global')

        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            rdv._skip_auto_log = True
            rdv.save()
            log_event(rdv, request.user, 'Rendez-vous modifié.', type='modif')

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
            from django.urls import reverse
            return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv.pk}))
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
        'medecins':      Medecin.objects.filter(actif=True).select_related('employe').order_by('employe__nom', 'employe__prenoms'),
        'registre_cpn':          _get_reg(RegistreCPN),
        'registre_accouchement': _get_reg(RegistreAccouchement),
        'registre_postnatale':   _get_reg(RegistrePostnatale),
        'registre_curatif':      _get_reg(RegistreCuratif),
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
        departement__code='GYN'
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
        departement__code='GYN'
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
def patient_soin_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from soins.models import Soin, ProcedureSoin
        from django.db.models import Prefetch
        items = Soin.objects.filter(patient=patient).prefetch_related(
            Prefetch(
                'procedures',
                queryset=ProcedureSoin.objects.select_related('infirmier', 'soin_type').order_by('date'),
                to_attr='procedures_list'
            )
        ).order_by('-date_heure')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'soin',
        'titre': 'Soins infirmiers',
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
        from laboratoire.models import DemandeExamen
        items = DemandeExamen.objects.filter(patient=patient).prefetch_related('lignes').order_by('-date_creation')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'demande_examens',
        'titre': "Demandes d'examens",
        'items': items,
    })


@login_required
def patient_resultat_examens_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from laboratoire.models import AnalyseLaboratoire
        items = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['resultat', 'valide', 'envoye']
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

    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'patients/pathologie_list.html', {
        'page_obj': page_obj,
        'q':        q,
        'total':    qs.count(),
    })


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@login_required
def pathologie_create(request):
    is_ajax = _is_ajax(request)
    if request.method == 'POST':
        form = PathologieForm(request.POST)
        if form.is_valid():
            p = form.save()
            if is_ajax:
                return JsonResponse({'ok': True, 'message': f'Pathologie "{p.nom}" enregistrée.'})
            messages.success(request, f'Pathologie "{p.nom}" enregistrée.')
            return redirect('patients:pathologie_list')
    else:
        form = PathologieForm()
    template = 'patients/pathologie_form_modal.html' if is_ajax else 'patients/pathologie_form.html'
    return render(request, template, {
        'form': form, 'titre': 'Nouvelle pathologie', 'edit': False,
    })


@login_required
def pathologie_edit(request, pk):
    pathologie = get_object_or_404(Pathologie, pk=pk)
    is_ajax = _is_ajax(request)
    if request.method == 'POST':
        form = PathologieForm(request.POST, instance=pathologie)
        if form.is_valid():
            form.save()
            if is_ajax:
                return JsonResponse({'ok': True, 'message': 'Pathologie mise à jour.'})
            messages.success(request, 'Pathologie mise à jour.')
            return redirect('patients:pathologie_list')
    else:
        form = PathologieForm(instance=pathologie)
    template = 'patients/pathologie_form_modal.html' if is_ajax else 'patients/pathologie_form.html'
    return render(request, template, {
        'form': form, 'titre': 'Modifier la pathologie', 'edit': True, 'object': pathologie,
    })


@login_required
def pathologie_delete(request, pk):
    pathologie = get_object_or_404(Pathologie, pk=pk)
    if request.method == 'POST':
        nom = pathologie.nom
        pathologie.delete()
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'message': f'Pathologie "{nom}" supprimée.'})
        messages.success(request, f'Pathologie "{nom}" supprimée.')
    return redirect('patients:pathologie_list')


# ── Export / Import des pathologies ─────────────────────────────────────────

_PATHOLOGIE_HDR = ['nom', 'description', 'actif']


def _pathologie_row(p):
    return [p.nom, p.description, int(p.actif)]


@login_required
def export_pathologies(request):
    from core.utils import csv_response
    import json as _json
    from django.http import HttpResponse

    fmt = request.GET.get('format', 'json')
    qs = Pathologie.objects.all()
    rows = [_pathologie_row(p) for p in qs]

    if fmt == 'csv':
        return csv_response('pathologies', _PATHOLOGIE_HDR, rows, delimiter=',')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        import io as _io
        wb = Workbook()
        ws = wb.active
        ws.title = 'Pathologies'
        fill = PatternFill(start_color='1F6E8C', end_color='1F6E8C', fill_type='solid')
        fnt = Font(color='FFFFFF', bold=True)
        ws.append(_PATHOLOGIE_HDR)
        for cell in ws[1]:
            cell.fill, cell.font = fill, fnt
            cell.alignment = Alignment(horizontal='center')
        for row in rows:
            ws.append(['' if v is None else v for v in row])
        for col in ws.columns:
            w = max((len(str(c.value or '')) for c in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(w + 4, 55)
        buf = _io.BytesIO()
        wb.save(buf)
        resp = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = 'attachment; filename="pathologies.xlsx"'
        return resp

    data = [dict(zip(_PATHOLOGIE_HDR, r)) for r in rows]
    resp = HttpResponse(
        _json.dumps(data, ensure_ascii=False, indent=2, default=str),
        content_type='application/json',
    )
    resp['Content-Disposition'] = 'attachment; filename="pathologies.json"'
    return resp


def _parse_pathologie_upload(upload):
    import csv as _csv
    import io as _io
    import json as _json

    name = upload.name.lower()
    try:
        if name.endswith('.json'):
            return _json.loads(upload.read().decode('utf-8')), None
        if name.endswith('.csv'):
            text = upload.read().decode('utf-8-sig')
            reader = _csv.DictReader(_io.StringIO(text))
            return list(reader), None
        if name.endswith(('.xlsx', '.xls')):
            import openpyxl
            wb = openpyxl.load_workbook(_io.BytesIO(upload.read()), data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return None, 'Fichier Excel vide.'
            hdrs = [str(h) if h is not None else '' for h in rows[0]]
            data = [dict(zip(hdrs, r)) for r in rows[1:] if any(v is not None for v in r)]
            return data, None
        return None, 'Format non supporté (.json, .csv ou .xlsx uniquement)'
    except Exception as e:
        return None, f'Erreur lecture fichier : {e}'


def _s(v):
    if v is None:
        return ''
    return str(v).replace('﻿', '').strip()


def _b(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ('1', 'true', 'oui', 'yes')


@login_required
def import_pathologies(request):
    upload = request.FILES.get('fichier')
    if not upload:
        messages.error(request, 'Aucun fichier sélectionné.')
        return redirect('patients:pathologie_list')

    data, err = _parse_pathologie_upload(upload)
    if err:
        messages.error(request, err)
        return redirect('patients:pathologie_list')

    do_update = 'update' in request.POST
    created = updated = skipped = errors = 0

    for item in data:
        try:
            nom = _s(item.get('nom', ''))
            if not nom:
                errors += 1
                continue
            defaults = {
                'description': _s(item.get('description', '')),
                'actif': _b(item.get('actif', True)),
            }
            obj, was_created = Pathologie.objects.get_or_create(nom=nom, defaults=defaults)
            if was_created:
                created += 1
            elif do_update:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                updated += 1
            else:
                skipped += 1
        except Exception:
            errors += 1

    if errors:
        messages.warning(request, f'{created} créée(s), {updated} mise(s) à jour, {skipped} ignorée(s), {errors} erreur(s).')
    else:
        messages.success(request, f'{created} pathologie(s) importée(s), {updated} mise(s) à jour, {skipped} ignorée(s).')
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
            return redirect('gynecologie_typevisite_list')
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
            return redirect('gynecologie_typevisite_list')
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
    return redirect('gynecologie_typevisite_list')


# ── Export / Import des types de visite ─────────────────────────────────────

_TYPEVISITE_HDR = ['nom', 'code', 'description', 'actif']


def _typevisite_row(tv):
    return [tv.nom, tv.code, tv.description, int(tv.actif)]


@login_required
def export_typevisite(request):
    import json as _json
    from django.http import HttpResponse

    fmt = request.GET.get('format', 'json')
    qs = TypeVisite.objects.all()
    rows = [_typevisite_row(tv) for tv in qs]

    if fmt == 'csv':
        from core.utils import csv_response
        return csv_response('types_visite', _TYPEVISITE_HDR, rows, delimiter=',')
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        import io as _io
        wb = Workbook()
        ws = wb.active
        ws.title = 'Types de visite'
        fill = PatternFill(start_color='1F6E8C', end_color='1F6E8C', fill_type='solid')
        fnt = Font(color='FFFFFF', bold=True)
        ws.append(_TYPEVISITE_HDR)
        for cell in ws[1]:
            cell.fill, cell.font = fill, fnt
            cell.alignment = Alignment(horizontal='center')
        for row in rows:
            ws.append(['' if v is None else v for v in row])
        for col in ws.columns:
            w = max((len(str(c.value or '')) for c in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(w + 4, 55)
        buf = _io.BytesIO()
        wb.save(buf)
        resp = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = 'attachment; filename="types_visite.xlsx"'
        return resp

    data = [dict(zip(_TYPEVISITE_HDR, r)) for r in rows]
    resp = HttpResponse(
        _json.dumps(data, ensure_ascii=False, indent=2, default=str),
        content_type='application/json',
    )
    resp['Content-Disposition'] = 'attachment; filename="types_visite.json"'
    return resp


@login_required
def import_typevisite(request):
    upload = request.FILES.get('fichier')
    if not upload:
        messages.error(request, 'Aucun fichier sélectionné.')
        return redirect('gynecologie_typevisite_list')

    data, err = _parse_pathologie_upload(upload)
    if err:
        messages.error(request, err)
        return redirect('gynecologie_typevisite_list')

    do_update = 'update' in request.POST
    created = updated = skipped = errors = 0

    for item in data:
        try:
            nom = _s(item.get('nom', ''))
            code = _s(item.get('code', ''))
            if not nom or not code:
                errors += 1
                continue
            defaults = {
                'nom': nom,
                'description': _s(item.get('description', '')),
                'actif': _b(item.get('actif', True)),
            }
            obj, was_created = TypeVisite.objects.get_or_create(code__iexact=code, defaults={**defaults, 'code': code})
            if was_created:
                created += 1
            elif do_update:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                updated += 1
            else:
                skipped += 1
        except Exception:
            errors += 1

    if errors:
        messages.warning(request, f'{created} créé(s), {updated} mis à jour, {skipped} ignoré(s), {errors} erreur(s).')
    else:
        messages.success(request, f'{created} type(s) de visite importé(s), {updated} mis à jour, {skipped} ignoré(s).')
    return redirect('gynecologie_typevisite_list')
