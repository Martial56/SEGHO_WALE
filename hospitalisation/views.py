from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import (Hospitalisation, Chambre, RegistreDeces,
                      ServiceAFacturer, ListeControleAdmission, ListeVerificationService,
                      ChecklistAdmission, ChecklistVerification, EvaluationClinique,
                      VisiteInfirmiere, VisiteDocteur, ResumeDecharge)
from core.views import log_event, get_logs
from .forms import ChambreForm, RegistreDecesForm, ListeControleAdmissionForm, ListeVerificationServiceForm



def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@login_required(login_url='login')
def hospitalisation_list(request):
    from django.utils import timezone as tz
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()

    qs = Hospitalisation.objects.select_related(
        'patient', 'medecin_traitant', 'chambre'
    ).order_by('-date_admission')

    if q:
        qs = qs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(numero__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    aujourd_hui = tz.now()

    total_chambres    = Chambre.objects.count()
    chambres_occupees = Chambre.objects.filter(statut=False).count()
    chambres_dispos   = Chambre.objects.filter(statut=True).count()
    taux_occupation   = round(chambres_occupees * 100 / total_chambres) if total_chambres else 0

    # Durée moyenne en jours des hospitalisations en cours
    from django.db.models import Avg, ExpressionWrapper, DurationField, F
    duree_moy_result = Hospitalisation.objects.filter(
        statut='hospitalise', heure_entree__isnull=False
    ).annotate(
        duree=ExpressionWrapper(aujourd_hui - F('heure_entree'), output_field=DurationField())
    ).aggregate(moy=Avg('duree'))
    duree_moy = duree_moy_result['moy']
    duree_moyenne = round(duree_moy.total_seconds() / 86400, 1) if duree_moy else 0

    stats = {
        'patients_hospitalises': Hospitalisation.objects.filter(statut='hospitalise').count(),
        'chambres_disponibles':  chambres_dispos,
        'taux_occupation':       taux_occupation,
        'duree_moyenne':         duree_moyenne,
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    vue = request.GET.get('vue', 'liste')
    if vue not in ('liste', 'kanban'):
        vue = 'liste'

    context = {
        'page_obj':      page_obj,
        'total':         qs.count(),
        'stats':         stats,
        'q':             q,
        'statut':        statut,
        'statut_choices': Hospitalisation.STATUT,
        'vue':           vue,
    }

    if _is_ajax(request):
        from django.template.loader import render_to_string
        return JsonResponse({
            'controls_html': render_to_string('hospitalisation/includes/_list_controls.html', context, request=request),
            'results_html':  render_to_string('hospitalisation/includes/_list_results.html', context, request=request),
            'total':         context['total'],
        })

    return render(request, 'hospitalisation/list.html', context)


def _constante_to_eval_prefill(constante):
    """Adapte un objet Constante (consultation) aux noms de champs d'EvaluationClinique."""
    from types import SimpleNamespace
    poids  = constante.poids
    taille = constante.taille
    imc    = round(float(poids) / (float(taille) ** 2), 2) if poids and taille and float(taille) > 0 else None
    if imc is None:
        imc_statut = ''
    elif imc < 18.5:
        imc_statut = 'Insuffisance pondérale'
    elif imc < 25:
        imc_statut = 'Normal'
    elif imc < 30:
        imc_statut = 'Surpoids'
    else:
        imc_statut = 'Obèse'
    return SimpleNamespace(
        poids=poids,
        taille=taille,
        temperature=constante.temperature,
        frequence_respiratoire=constante.frequence_respiratoire,
        tension_systolique=constante.tension_systolique,
        tension_diastolique=constante.tension_diastolique,
        saturation_o2=constante.saturation_oxygene,
        glycemie=constante.glycemie,
        niveau_douleur=constante.niveau_douleur,
        imc=imc,
        imc_statut=imc_statut,
    )


@login_required(login_url='login')
def hospitalisation_create(request):
    from django.utils import timezone
    from .forms import HospitalisationForm
    if request.method == 'POST':
        form = HospitalisationForm(request.POST, request.FILES)
        if form.is_valid():
            hosp = form.save(commit=False)
            hosp.cree_par = request.user
            hosp.save()
            form.save_m2m()
            for i, item in enumerate(ListeControleAdmission.objects.all()):
                ChecklistAdmission.objects.create(
                    hospitalisation=hosp, item=item.item, ordre=i
                )
            for i, item in enumerate(ListeVerificationService.objects.all()):
                ChecklistVerification.objects.create(
                    hospitalisation=hosp, item=item.item, ordre=i
                )
            # Évaluation clinique : priorité aux valeurs soumises dans le formulaire
            _save_evaluation_clinique(hosp, request.POST)
            # Soins et services saisis dans le formulaire de création
            _save_visites_infirmieres(hosp, request.POST, user=request.user)
            _save_visites_docteur(hosp, request.POST, user=request.user)
            _save_services_a_facturer(hosp, request.POST)
            log_event(hosp, request.user, 'Hospitalisation créée.', type='system')
            _sync_soins_services(hosp)
            if 'action_confirmer' in request.POST:
                ok, err = _transition_confirmer(hosp, request.user)
                if ok:
                    messages.success(request, f'Hospitalisation {hosp.numero} créée et confirmée.')
                else:
                    messages.error(request, err)
                    messages.warning(request, f'Hospitalisation {hosp.numero} créée mais non confirmée.')
            else:
                messages.success(request, f'Hospitalisation {hosp.numero} créée.')
            return redirect('hospitalisation:detail', pk=hosp.pk)
    else:
        initial = {'date_admission': timezone.now()}
        eval_prefill = None
        is_mo = False
        mo_patient = mo_medecin = mo_maladie = None
        # Pré-remplissage depuis les paramètres URL (ex. depuis rendez-vous)
        try:
            if request.GET.get('medecin'):
                initial['medecin_traitant'] = int(request.GET['medecin'])
        except (ValueError, TypeError):
            pass
        try:
            if request.GET.get('patient'):
                initial['patient'] = int(request.GET['patient'])
        except (ValueError, TypeError):
            pass
        # Pré-remplissage depuis un rendez-vous (mode M.O)
        try:
            rdv_pk = request.GET.get('rdv')
            if rdv_pk:
                from patients.models import RendezVous, RegistreCuratif, Pathologie
                rdv = RendezVous.objects.select_related(
                    'patient', 'medecin', 'consultation'
                ).get(pk=int(rdv_pk))
                is_mo = True
                mo_patient = rdv.patient
                mo_medecin = rdv.medecin
                # Maladie : premier diagnostic retenu du registre curatif
                try:
                    reg = rdv.registre_curatif
                    diag_pks = reg.donnees.get('cur_diagnostic', [])
                    if isinstance(diag_pks, str):
                        diag_pks = [diag_pks] if diag_pks else []
                    first_pk = next((int(v) for v in diag_pks if str(v).strip().isdigit()), None)
                    if first_pk:
                        initial['maladie'] = first_pk
                        mo_maladie = Pathologie.objects.filter(pk=first_pk).first()
                except (RegistreCuratif.DoesNotExist, AttributeError):
                    pass
                # Évaluation clinique : constantes de la consultation liée au RDV
                try:
                    constante = rdv.consultation.constantes
                    eval_prefill = _constante_to_eval_prefill(constante)
                except AttributeError:
                    pass
        except (ValueError, TypeError, Exception):
            pass
        # Fallback : dernière constante du patient si pas de RDV
        if eval_prefill is None:
            try:
                patient_pk = initial.get('patient')
                if patient_pk:
                    from consultations.models import Constante
                    last = Constante.objects.filter(
                        consultation__patient_id=patient_pk
                    ).order_by('-date_saisie').first()
                    if last:
                        eval_prefill = _constante_to_eval_prefill(last)
            except Exception:
                pass
        form = HospitalisationForm(initial=initial)
    from medecins.models import Medecin
    from services.models import Articleservice
    from stock.models import UniteMesure
    ctx = {
        'form':          form,
        'titre':         'Nouveau',
        'edit':          False,
        'medecins_list': list(Medecin.objects.filter(actif=True).order_by('employe__nom')),
        'unites_list':   list(UniteMesure.objects.filter(actif=True).order_by('nom')),
        'services_list': list(Articleservice.objects.filter(actif=True, categorie__code='SN').order_by('nom')),
    }
    if request.method == 'GET':
        ctx['eval_clin'] = eval_prefill
        ctx['is_mo']     = is_mo
        ctx['mo_patient'] = mo_patient
        ctx['mo_medecin'] = mo_medecin
        ctx['mo_maladie'] = mo_maladie
    return render(request, 'hospitalisation/form.html', ctx)


def _sync_soins_services(hosp):
    """Synchronise soins_apportes → ServiceAFacturer (source='soin')."""
    from django.utils import timezone as tz
    current_ids = set(hosp.soins_apportes.values_list('pk', flat=True))
    existing = {saf.service_id: saf for saf in hosp.services_a_facturer.filter(source='soin')}
    # Ajouter les nouveaux soins
    for soin_pk in current_ids:
        if soin_pk not in existing:
            ServiceAFacturer.objects.create(
                hospitalisation=hosp,
                service_id=soin_pk,
                source='soin',
                quantite=1,
                date=tz.now().date(),
            )
    # Supprimer les soins retirés (seulement si non facturés)
    for soin_pk, saf in existing.items():
        if soin_pk not in current_ids and not saf.facture_id:
            saf.delete()


# ─── HELPERS DE TRANSITION DE STATUT ──────────────────────────────────────────
# Chaque helper retourne (ok: bool, erreur: str|None).
# La vue appelante affiche le message et redirige.

def _transition_confirmer(hosp, user):
    """brouillon → confirme : crée la ligne MEO et synchronise les SAF depuis soins_apportes."""
    from .services import check_action
    ok, err = check_action(hosp, user, 'confirmer')
    if not ok:
        return False, err
    _sync_soins_services(hosp)
    # Ligne MEO automatique (une seule fois)
    from services.models import Articleservice
    from django.utils import timezone as tz
    meo = Articleservice.objects.filter(categorie__code='MO', reference_interne='MO_MEO').first()
    if meo:
        date_adm = hosp.date_admission.date() if hosp.date_admission else tz.now().date()
        ServiceAFacturer.objects.get_or_create(
            hospitalisation=hosp,
            source='meo',
            defaults={'service': meo, 'quantite': 1, 'date': date_adm},
        )
    hosp.statut = 'confirme'
    hosp.modifie_par = user
    hosp.date_modification = tz.now()
    hosp.save(update_fields=['statut', 'modifie_par', 'date_modification'])
    log_event(hosp, user, 'Statut changé : Confirmé — Mise en observation générée.', type='statut')
    return True, None


def _sync_soins_only(hosp, user):
    """confirme/hospitalise : garde-fou + log pour synchro soins sans changement de statut.

    _sync_soins_services() est déjà appelé par le chemin principal (form.save_m2m),
    donc cette fonction ne fait que valider, loguer et retourner.
    """
    if hosp.statut not in ('confirme', 'hospitalise'):
        return False, f"Impossible depuis le statut {hosp.get_statut_display()}."
    if not (user.is_superuser or user.has_perm('hospitalisation.can_confirmer_demande')):
        return False, "Vous n'avez pas l'autorisation de synchroniser les soins."
    log_event(hosp, user, 'Soins mis à jour — services à facturer synchronisés.', type='modif')
    return True, None


def _transition_installer(hosp, user):
    """confirme → hospitalise : exige une facture payée et une chambre attribuée, fige heure_entree."""
    from .services import check_action
    from django.db import transaction as db_transaction
    ok, err = check_action(hosp, user, 'installer')
    if not ok:
        return False, err
    if not hosp.chambre_id:
        return False, "Une chambre doit être attribuée avant d'hospitaliser."
    from django.utils import timezone as tz
    with db_transaction.atomic():
        chambre = Chambre.objects.select_for_update().get(pk=hosp.chambre_id)
        if chambre.nombre_lits == 1:
            if not chambre.statut:
                return False, "Cette chambre n'est plus disponible."
            chambre.statut = False
            chambre.save(update_fields=['statut'])
        else:
            lit_no = hosp.numero_lit
            if not lit_no:
                return False, "Aucun lit sélectionné pour cette chambre."
            deja_pris = Hospitalisation.objects.filter(
                chambre=chambre, numero_lit=lit_no, statut='hospitalise'
            ).exclude(pk=hosp.pk).exists()
            if deja_pris:
                return False, f"Le lit {lit_no} de cette chambre est déjà occupé."
        now = tz.now()
        hosp.statut = 'hospitalise'
        hosp.heure_entree = now
        hosp.modifie_par = user
        hosp.date_modification = now
        hosp.save(update_fields=['statut', 'heure_entree', 'modifie_par', 'date_modification'])
    log_event(hosp, user, "Statut changé : Hospitalisé — heure d'entrée figée à %s." % hosp.heure_entree.strftime('%H:%M'), type='statut')
    return True, None


def _transition_decharger(hosp, user):
    """hospitalise → decharge : exige résumé de décharge, fige heure_sortie."""
    from .services import check_action
    ok, err = check_action(hosp, user, 'decharger')
    if not ok:
        return False, err
    try:
        if hosp.resume_decharge.transfert:
            if not (hosp.etablissement_destination or '').strip():
                return False, "L'établissement de destination est obligatoire pour un transfert."
            if not (hosp.motif_reference or '').strip():
                return False, "Le motif du transfert est obligatoire."
    except ResumeDecharge.DoesNotExist:
        pass
    from django.utils import timezone as tz
    now = tz.now()
    hosp.statut = 'decharge'
    hosp.heure_sortie = now
    hosp.modifie_par = user
    hosp.date_modification = now
    if hosp.chambre_id and hosp.chambre.nombre_lits == 1:
        hosp.chambre.statut = True
        hosp.chambre.save(update_fields=['statut'])
    hosp.save(update_fields=['statut', 'heure_sortie', 'modifie_par', 'date_modification'])
    log_event(hosp, user, 'Statut changé : Déchargé — sortie médicale à %s.' % now.strftime('%H:%M'), type='statut')
    _sync_statut_soin_dossier(hosp, user)
    return True, None


def _transition_terminer(hosp, user):
    """decharge → termine : bloqué si SAF non facturés ou factures impayées."""
    from .services import check_action
    ok, err = check_action(hosp, user, 'terminer')
    if not ok:
        return False, err
    from django.utils import timezone as tz
    now = tz.now()
    hosp.statut = 'termine'
    hosp.termine_par = user
    hosp.date_termine = now
    hosp.modifie_par = user
    hosp.date_modification = now
    hosp.save(update_fields=['statut', 'termine_par', 'date_termine', 'modifie_par', 'date_modification'])
    log_event(hosp, user, 'Statut changé : Terminé — dossier clos administrativement.', type='statut')
    _sync_statut_soin_dossier(hosp, user)
    return True, None


def _transition_annuler(hosp, user, motif=''):
    """brouillon/confirme/hospitalise → annule."""
    from .services import check_action
    ok, err = check_action(hosp, user, 'annuler')
    if not ok:
        return False, err
    # Garde explicite : impossible depuis decharge, termine ou annule
    if hosp.statut in ('decharge', 'termine', 'annule'):
        return False, f"Impossible d'annuler une hospitalisation au statut {hosp.get_statut_display()}."
    from django.utils import timezone as tz
    from facturation.models import Facture
    now = tz.now()
    statut_avant = hosp.statut
    if statut_avant == 'hospitalise' and hosp.chambre_id:
        if hosp.chambre.nombre_lits == 1:
            hosp.chambre.statut = True
            hosp.chambre.save(update_fields=['statut'])
        hosp.heure_sortie = now
    # Annuler les factures impayées (les factures payées sont conservées)
    Facture.objects.filter(hospitalisation=hosp).exclude(
        statut__in=['payee', 'annulee']
    ).update(statut='annulee')
    hosp.statut = 'annule'
    hosp.modifie_par = user
    hosp.date_modification = now
    fields = ['statut', 'modifie_par', 'date_modification']
    if statut_avant == 'hospitalise':
        fields.append('heure_sortie')
    hosp.save(update_fields=fields)
    msg = 'Hospitalisation annulée.'
    if motif:
        msg += f' Motif : {motif}'
    log_event(hosp, user, msg, type='statut')
    _sync_statut_soin_dossier(hosp, user)
    return True, None


def _get_facture_blocage(hosp):
    """
    Retourne la première facture non payée et non annulée liée à cette hospitalisation,
    ou None si toutes les factures sont réglées/annulées.
    Utilisé pour verrouiller le formulaire d'édition.
    """
    from facturation.models import Facture
    return Facture.objects.filter(
        hospitalisation=hosp
    ).exclude(
        statut__in=['payee', 'annulee']
    ).order_by('date_emission').first()


def _apply_lock_protection(hosp, post_data, is_admin=False, facture_bloquante=False, chambre_libre=False):
    """
    Neutralise les POST forgés sur les champs d'en-tête verrouillés.
    chambre_libre=True : ne réinjecte pas chambre_lit (mode attribution chambre).
    """
    if is_admin:
        return post_data
    verrou_actif = (hosp.statut != 'brouillon') or facture_bloquante
    if not verrou_actif:
        return post_data
    data = post_data.copy()
    if hosp.patient_id:
        data['patient'] = str(hosp.patient_id)
    if hosp.medecin_traitant_id:
        data['medecin_traitant'] = str(hosp.medecin_traitant_id)
    if hosp.chambre_id and not chambre_libre:
        lit = hosp.numero_lit or 0
        data['chambre_lit'] = f"{hosp.chambre_id}_{lit}"
    if hosp.date_admission:
        data['date_admission'] = hosp.date_admission.strftime('%Y-%m-%dT%H:%M')
    if (hosp.mise_en_observation or '').strip():
        data['mise_en_observation'] = hosp.mise_en_observation
    if hosp.infirmiere_primaire_id:
        data['infirmiere_primaire'] = str(hosp.infirmiere_primaire_id)
    return data


def _parse_decimal(val, default=None):
    try:
        v = val.replace(',', '.').strip()
        return Decimal(v) if v else default
    except Exception:
        return default


def _parse_int(val, default=None):
    try:
        v = val.strip()
        return int(v) if v else default
    except Exception:
        return default


def _save_evaluation_clinique(hosp, POST):
    eval_clin, _ = EvaluationClinique.objects.get_or_create(hospitalisation=hosp)
    eval_clin.poids                = _parse_decimal(POST.get('eval_poids', ''))
    eval_clin.taille               = _parse_decimal(POST.get('eval_taille', ''))
    eval_clin.temperature          = _parse_decimal(POST.get('eval_temperature', ''))
    eval_clin.frequence_respiratoire = _parse_int(POST.get('eval_freq_resp', ''))
    eval_clin.tension_systolique   = _parse_int(POST.get('eval_tension_sys', ''))
    eval_clin.tension_diastolique  = _parse_int(POST.get('eval_tension_dia', ''))
    eval_clin.saturation_o2        = _parse_decimal(POST.get('eval_sat_o2', ''))
    eval_clin.glycemie             = _parse_decimal(POST.get('eval_glycemie', ''))
    eval_clin.niveau_douleur       = _parse_int(POST.get('eval_douleur', ''))
    eval_clin.save()


def _save_services_a_facturer(hosp, POST):
    from services.models import Articleservice
    from stock.models import UniteMesure
    ids      = POST.getlist('saf_id[]')
    services = POST.getlist('saf_service[]')
    unites   = POST.getlist('saf_unite[]')
    quantites= POST.getlist('saf_quantite[]')
    dates    = POST.getlist('saf_date[]')
    seen = set()
    for i, pk_str in enumerate(ids):
        svc_pk = services[i] if i < len(services) else ''
        un_pk  = unites[i] if i < len(unites) else ''
        qte    = _parse_decimal(quantites[i] if i < len(quantites) else '', 1)
        date_val = dates[i].strip() if i < len(dates) else ''
        from django.utils.dateparse import parse_date
        date_obj = parse_date(date_val) if date_val else None
        svc_obj = Articleservice.objects.filter(pk=svc_pk).first() if svc_pk else None
        un_obj  = UniteMesure.objects.filter(pk=un_pk).first() if un_pk else None
        if not svc_obj:
            continue
        if pk_str:
            try:
                obj = ServiceAFacturer.objects.get(pk=int(pk_str), hospitalisation=hosp)
                if obj.facture_id:
                    # Ligne déjà facturée : aucune modification ni suppression autorisée.
                    seen.add(obj.pk)
                else:
                    obj.service=svc_obj; obj.unite_mesure=un_obj; obj.quantite=qte; obj.date=date_obj; obj.ordre=i
                    obj.save(); seen.add(obj.pk)
            except ServiceAFacturer.DoesNotExist:
                pass
        else:
            obj = ServiceAFacturer.objects.create(
                hospitalisation=hosp, service=svc_obj, unite_mesure=un_obj,
                quantite=qte, date=date_obj, ordre=i)
            seen.add(obj.pk)
    # Seules les lignes manuelles non soumises et non facturées sont supprimées.
    # Les entrées source='soin', 'visite_infirmiere', 'visite_docteur', 'chambre'
    # sont gérées par leurs propres fonctions de synchronisation.
    hosp.services_a_facturer.filter(source='manuel', facture__isnull=True).exclude(pk__in=seen).delete()


def _save_resume_decharge(hosp, POST):
    # Fonction idempotente : plusieurs appels avec les mêmes données POST produisent
    # exactement le même état. get_or_create garantit l'unicité du résumé ;
    # chaque champ est simplement écrasé avec la valeur du POST.
    # IMPORTANT : ne pas retirer le `return` de la branche `action_decharger` dans
    # hospitalisation_edit sans revoir ce point — le double appel est voulu.
    resume, _ = ResumeDecharge.objects.get_or_create(hospitalisation=hosp)
    resume.transfert             = 'rd_transfert' in POST
    resume.diagnostic_decharge   = POST.get('rd_diagnostic', '').strip()
    resume.note_preoperatoire    = POST.get('rd_note_preop', '').strip()
    resume.cours_post_operatoire = POST.get('rd_cours_post_op', '').strip()
    resume.plan_sortie           = POST.get('rd_plan_sortie', '').strip()
    resume.instructions          = POST.get('rd_instructions', '').strip()
    rd_deces_pk = POST.get('rd_registre_deces', '').strip()
    if rd_deces_pk:
        try:
            resume.registre_deces = RegistreDeces.objects.get(pk=int(rd_deces_pk))
        except (RegistreDeces.DoesNotExist, ValueError):
            resume.registre_deces = None
    else:
        resume.registre_deces = None
    resume.save()
    # Synchronise les champs de transfert sur l'hospitalisation elle-même
    if resume.transfert:
        hosp.etablissement_destination = POST.get('rd_etablissement_destination', '').strip()
        hosp.motif_reference = POST.get('rd_motif_reference', '').strip()
    else:
        hosp.etablissement_destination = ''
        hosp.motif_reference = ''
    hosp.save(update_fields=['etablissement_destination', 'motif_reference'])


def _sync_saf_from_visite(hosp, article, quantite, date_obj, source, visite_pk):
    """Crée ou met à jour une ligne ServiceAFacturer liée à une visite."""
    if not article:
        return
    from django.utils import timezone as tz
    saf, _ = ServiceAFacturer.objects.get_or_create(
        hospitalisation=hosp,
        source=source,
        ordre=visite_pk,
        defaults={
            'service': article,
            'quantite': quantite,
            'date': (date_obj.date() if hasattr(date_obj, 'date') else date_obj) or tz.now().date(),
        }
    )
    if not _:
        saf.service = article
        saf.quantite = quantite
        saf.date = (date_obj.date() if hasattr(date_obj, 'date') else date_obj) or tz.now().date()
        saf.save()


def get_or_create_soin_dossier(hosp, user):
    """Retourne ou crée le dossier Soin unique lié à cette hospitalisation."""
    from soins.models import Soin as SoinModule
    dossier = SoinModule.objects.filter(hospitalisation=hosp).first()
    if not dossier:
        dossier = SoinModule.objects.create(
            patient=hosp.patient,
            motif=f"Soins hospitalisation {hosp.numero}",
            statut='en_attente_de_paiement',
            hospitalisation=hosp,
            cree_par=user,
        )
    return dossier


def _sync_statut_soin_dossier(hosp, user=None):
    """Recalcule le statut du dossier Soin lié à l'hospitalisation et de ses ProcedureSoin."""
    from soins.models import Soin as SoinModule
    from django.utils import timezone as tz

    dossier = SoinModule.objects.filter(hospitalisation=hosp).first()
    if not dossier:
        return

    procedures = list(dossier.procedures.select_related('facture').all())

    # --- Statut de chaque ProcedureSoin ---
    for proc in procedures:
        if hosp.statut == 'annule':
            new_statut = 'annule'
        elif proc.facture and proc.facture.statut == 'payee':
            if hosp.statut in ('decharge', 'termine'):
                new_statut = 'termine'
            else:
                new_statut = 'en_cours'
        else:
            # Facture non payée (ou absente) : jamais forcer 'termine'
            new_statut = proc.statut if proc.statut != 'termine' else 'en_cours'

        if proc.statut != new_statut:
            proc.statut = new_statut
            proc.date_modification = tz.now()
            if user:
                proc.modifie_par = user
            proc.save(update_fields=['statut', 'date_modification', 'modifie_par'])

    # --- Statut du dossier Soin ---
    # Seules les factures non annulées sont prises en compte
    factures = [p.facture for p in procedures if p.facture and p.facture.statut != 'annulee']
    has_unpaid = any(f.statut != 'payee' for f in factures)
    has_paid = any(f.statut == 'payee' for f in factures)

    if hosp.statut == 'annule':
        new_dossier_statut = 'annule'
    elif has_unpaid:
        # Une facture impayée maintient en_attente_de_paiement MÊME après décharge
        new_dossier_statut = 'en_attente_de_paiement'
    elif has_paid and hosp.statut in ('decharge', 'termine'):
        new_dossier_statut = 'termine'
    elif has_paid:
        new_dossier_statut = 'en_cours'
    else:
        # Aucune facture encore : en attente de facturation
        new_dossier_statut = 'en_attente_de_paiement'

    if dossier.statut != new_dossier_statut:
        old = dossier.statut
        dossier.statut = new_dossier_statut
        dossier.date_modification = tz.now()
        if user:
            dossier.modifie_par = user
        dossier.save(update_fields=['statut', 'date_modification', 'modifie_par'])
        log_event(dossier, user, f'Statut synchronisé : {old} → {new_dossier_statut}.', type='statut')


def _sync_procedure_soin(hosp, article, quantite, date_obj, user):
    """Crée une ProcedureSoin dans le module soins pour traçabilité (visites infirmières/docteur)."""
    from soins.models import ProcedureSoin
    from django.utils import timezone as tz
    dossier = get_or_create_soin_dossier(hosp, user)
    ProcedureSoin.objects.create(
        soin=dossier,
        patient=hosp.patient,
        soin_type=article,
        prix=article.prix_vente if article else 0,
        date=date_obj or tz.now(),
        cree_par=user,
    )


def _save_visites_infirmieres(hosp, POST, user=None):
    from medecins.models import Medecin
    from stock.models import UniteMesure
    from services.models import Articleservice
    ids         = POST.getlist('vi_id[]')
    dates       = POST.getlist('vi_date[]')
    soins       = POST.getlist('vi_soin[]')
    quantites   = POST.getlist('vi_quantite[]')
    unites      = POST.getlist('vi_unite[]')
    infirmieres = POST.getlist('vi_infirmiere[]')
    remarques   = POST.getlist('vi_remarques[]')
    # VIs dont la facture est payée : intouchables (ni modification, ni suppression)
    payees_pks = set(hosp.services_a_facturer.filter(
        source='visite_infirmiere', facture__statut='payee'
    ).values_list('ordre', flat=True))

    seen = set()
    seen_saf_orders = set()
    for i, pk_str in enumerate(ids):
        date_val = dates[i].strip() if i < len(dates) else ''
        soin_pk  = soins[i] if i < len(soins) else ''
        qte      = _parse_decimal(quantites[i] if i < len(quantites) else '', 1)
        unite_pk = unites[i] if i < len(unites) else ''
        inf_pk   = infirmieres[i] if i < len(infirmieres) else ''
        rem      = remarques[i] if i < len(remarques) else ''
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as tz
        date_obj  = parse_datetime(date_val) if date_val else tz.now()
        soin_obj  = Articleservice.objects.filter(pk=soin_pk).first() if soin_pk else None
        unite_obj = UniteMesure.objects.filter(pk=unite_pk).first() if unite_pk else None
        inf_obj   = Medecin.objects.filter(pk=inf_pk).first() if inf_pk else None
        if pk_str:
            try:
                obj = VisiteInfirmiere.objects.get(pk=int(pk_str), hospitalisation=hosp)
                seen.add(obj.pk)
                if obj.pk in payees_pks:
                    # Ligne payée : on la conserve sans la modifier
                    seen_saf_orders.add(obj.pk)
                    continue
                obj.date=date_obj; obj.soin=soin_obj; obj.quantite=qte
                obj.unite_mesure=unite_obj; obj.infirmiere=inf_obj; obj.remarques=rem; obj.ordre=i
                obj.save()
                _sync_saf_from_visite(hosp, soin_obj, qte, date_obj, 'visite_infirmiere', obj.pk)
                seen_saf_orders.add(obj.pk)
            except VisiteInfirmiere.DoesNotExist:
                pass
        else:
            obj = VisiteInfirmiere.objects.create(
                hospitalisation=hosp, date=date_obj, soin=soin_obj,
                quantite=qte, unite_mesure=unite_obj, infirmiere=inf_obj,
                remarques=rem, ordre=i)
            seen.add(obj.pk)
            _sync_saf_from_visite(hosp, soin_obj, qte, date_obj, 'visite_infirmiere', obj.pk)
            seen_saf_orders.add(obj.pk)
    # Supprimer uniquement les visites non payées retirées
    removed = hosp.visites_infirmieres.exclude(pk__in=seen).exclude(pk__in=payees_pks)
    removed_pks = list(removed.values_list('pk', flat=True))
    hosp.services_a_facturer.filter(source='visite_infirmiere', ordre__in=removed_pks, facture__isnull=True).delete()
    removed.delete()


def _save_visites_docteur(hosp, POST, user=None):
    from medecins.models import Medecin
    from services.models import Articleservice
    ids          = POST.getlist('vd_id[]')
    dates        = POST.getlist('vd_date[]')
    soins        = POST.getlist('vd_soin[]')
    instructions = POST.getlist('vd_instruction[]')
    docteurs     = POST.getlist('vd_docteur[]')
    remarques    = POST.getlist('vd_remarques[]')
    seen = set()
    for i, pk_str in enumerate(ids):
        date_val = dates[i].strip() if i < len(dates) else ''
        soin_pk  = soins[i] if i < len(soins) else ''
        instr    = instructions[i].strip() if i < len(instructions) else ''
        doc_pk   = docteurs[i] if i < len(docteurs) else ''
        rem      = remarques[i] if i < len(remarques) else ''
        from django.utils.dateparse import parse_datetime
        date_obj = parse_datetime(date_val) if date_val else None
        soin_obj = Articleservice.objects.filter(pk=soin_pk).first() if soin_pk else None
        doc_obj  = Medecin.objects.filter(pk=doc_pk).first() if doc_pk else None
        if pk_str:
            try:
                obj = VisiteDocteur.objects.get(pk=int(pk_str), hospitalisation=hosp)
                obj.date=date_obj; obj.soin=soin_obj; obj.instruction=instr
                obj.docteur=doc_obj; obj.remarques=rem; obj.ordre=i
                obj.save(); seen.add(obj.pk)
                _sync_saf_from_visite(hosp, soin_obj, 1, date_obj, 'visite_docteur', obj.pk)
            except VisiteDocteur.DoesNotExist:
                pass
        else:
            obj = VisiteDocteur.objects.create(
                hospitalisation=hosp, date=date_obj, soin=soin_obj,
                instruction=instr, docteur=doc_obj, remarques=rem, ordre=i)
            seen.add(obj.pk)
            _sync_saf_from_visite(hosp, soin_obj, 1, date_obj, 'visite_docteur', obj.pk)
    removed = hosp.visites_docteur.exclude(pk__in=seen)
    removed_pks = list(removed.values_list('pk', flat=True))
    hosp.services_a_facturer.filter(source='visite_docteur', ordre__in=removed_pks, facture__isnull=True).delete()
    removed.delete()


def _save_checklist_admission(hosp, POST):
    ids       = POST.getlist('cadm_id[]')
    items     = POST.getlist('cadm_item[]')
    verifies  = POST.getlist('cadm_verifie[]')   # JS met '1' si coché, '' sinon
    remarques = POST.getlist('cadm_remarques[]')
    seen = set()
    for i, (pk_str, item_text) in enumerate(zip(ids, items)):
        item_text = item_text.strip()
        if not item_text:
            continue
        verifie  = (verifies[i] == '1') if i < len(verifies) else False
        remarque = remarques[i] if i < len(remarques) else ''
        if pk_str:
            try:
                obj = ChecklistAdmission.objects.get(pk=int(pk_str), hospitalisation=hosp)
                obj.item = item_text; obj.verifie = verifie
                obj.remarques = remarque; obj.ordre = i; obj.save()
                seen.add(obj.pk)
            except ChecklistAdmission.DoesNotExist:
                pass
        else:
            obj = ChecklistAdmission.objects.create(
                hospitalisation=hosp, item=item_text,
                verifie=verifie, remarques=remarque, ordre=i)
            seen.add(obj.pk)
    hosp.checklist_admission.exclude(pk__in=seen).delete()


def _save_checklist_verification(hosp, POST):
    ids       = POST.getlist('cver_id[]')
    items     = POST.getlist('cver_item[]')
    termines  = POST.getlist('cver_termine[]')
    remarques = POST.getlist('cver_remarques[]')
    seen = set()
    for i, (pk_str, item_text) in enumerate(zip(ids, items)):
        item_text = item_text.strip()
        if not item_text:
            continue
        termine  = (termines[i] == '1') if i < len(termines) else False
        remarque = remarques[i] if i < len(remarques) else ''
        if pk_str:
            try:
                obj = ChecklistVerification.objects.get(pk=int(pk_str), hospitalisation=hosp)
                obj.item = item_text; obj.termine = termine
                obj.remarques = remarque; obj.ordre = i; obj.save()
                seen.add(obj.pk)
            except ChecklistVerification.DoesNotExist:
                pass
        else:
            obj = ChecklistVerification.objects.create(
                hospitalisation=hosp, item=item_text,
                termine=termine, remarques=remarque, ordre=i)
            seen.add(obj.pk)
    hosp.checklist_verification.exclude(pk__in=seen).delete()




@login_required(login_url='login')
def hospitalisation_creer_facture(request, pk):
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    from .services import check_action
    ok, err = check_action(hosp, request.user, 'creer_facture')
    if not ok:
        messages.error(request, err)
        return redirect('hospitalisation:detail', pk=pk)

    from facturation.models import Facture, LigneFacture
    from soins.models import ProcedureSoin
    from django.utils import timezone as tz
    from django.urls import reverse

    back_url = reverse('hospitalisation:detail', kwargs={'pk': hosp.pk})

    # Prendre uniquement les SAF non encore facturés avec un service réel (pas chambre)
    services = list(hosp.services_a_facturer.filter(
        facture__isnull=True, service__isnull=False
    ).select_related('service').all())

    if not services:
        messages.warning(request, 'Aucun service à facturer non encore réglé.')
        return redirect(back_url)

    facture = Facture.objects.create(
        patient=hosp.patient,
        hospitalisation=hosp,
        type_facture='hospitalisation',
        statut='brouillon',
        montant_total=0,
        cree_par=request.user,
    )

    for s in services:
        LigneFacture.objects.create(
            facture=facture,
            libelle=s.service.nom,
            quantite=s.quantite,
            prix_unitaire=s.service.prix_vente,
            remise=Decimal('0'),
        )
        s.facture = facture
        s.save(update_fields=['facture'])

    # Recalcule le total après création de toutes les lignes (remises incluses).
    facture.recalculer_total()

    for s in services:
        # Synchroniser vers le module soins pour les soins apportés
        if s.source == 'soin' and s.service:
            dossier = get_or_create_soin_dossier(hosp, request.user)
            already_exists = dossier.procedures.filter(
                soin_type=s.service,
                facture=facture,
            ).exists()
            if not already_exists:
                ProcedureSoin.objects.create(
                    soin=dossier,
                    patient=hosp.patient,
                    soin_type=s.service,
                    prix=s.service.prix_vente,
                    facture=facture,
                    date=tz.now(),
                    cree_par=request.user,
                )

    _sync_statut_soin_dossier(hosp, request.user)
    log_event(hosp, request.user, f'Facture complémentaire {facture.numero} créée ({len(services)} ligne(s)).', type='system')
    log_event(facture, request.user, 'Facture complémentaire créée depuis hospitalisation.', type='system')
    messages.success(request, f'Facture {facture.numero} créée.')

    detail_url = reverse('facturation:detail', kwargs={'pk': facture.pk})
    return redirect(f'{detail_url}?next={back_url}')


@login_required(login_url='login')
def hospitalisation_edit(request, pk):
    from .forms import HospitalisationForm
    from medecins.models import Medecin
    from stock.models import UniteMesure
    from services.models import Articleservice
    from facturation.models import Facture
    from laboratoire.models import AnalyseLaboratoire

    from .services import get_actions_disponibles
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    is_admin = request.user.is_superuser

    # Permission de modification
    peut_changer   = is_admin or request.user.has_perm('hospitalisation.change_hospitalisation')
    peut_installer = request.user.has_perm('hospitalisation.can_installer_patient')
    peut_soins     = request.user.has_perm('hospitalisation.can_ajouter_soin')
    peut_decharger = request.user.has_perm('hospitalisation.can_decharger_patient')

    facture_blocage = _get_facture_blocage(hosp)
    facture_payee   = Facture.objects.filter(hospitalisation=hosp, statut='payee').exists()
    factures_impayees = Facture.objects.filter(hospitalisation=hosp).exclude(statut__in=['payee', 'annulee']).count()
    tab_param = request.GET.get('tab', '')

    # Mode attribution chambre : confirme + facture payée — seul chambre_lit est modifiable.
    mode_chambre_seule = hosp.statut == 'confirme' and facture_payee
    # Mode soins seuls : patient hospitalisé — seuls les soins/visites sont modifiables.
    # Non-admin : narrowé par permission (n'a que le droit d'ajouter un soin).
    # Admin : a toutes les permissions, donc narrowé seulement s'il arrive via le
    # lien "Ajouter un soin" (?tab=soins) plutôt que via "Modifier".
    mode_soins_seuls = hosp.statut == 'hospitalise' and peut_soins and (
        tab_param == 'soins' if is_admin else (not peut_changer and not peut_decharger)
    )
    # Mode décharge : toutes factures payées — seul l'onglet résumé de décharge est modifiable.
    # Même logique : admin narrowé seulement via le lien "Décharger" (?tab=resume).
    mode_decharge_seule = hosp.statut == 'hospitalise' and peut_decharger and factures_impayees == 0 and (
        tab_param == 'resume' if is_admin else not peut_changer
    )

    # Vérification d'accès
    if not peut_changer:
        if peut_installer and mode_chambre_seule:
            pass  # accès limité à l'attribution de chambre
        elif mode_soins_seuls:
            pass  # accès limité à l'ajout de soins
        elif mode_decharge_seule:
            pass  # accès limité au résumé de décharge
        else:
            messages.error(request, "Vous n'avez pas l'autorisation de modifier ce dossier.")
            return redirect('hospitalisation:detail', pk=pk)

    if hosp.statut in ('termine', 'annule') and not is_admin:
        messages.warning(request, "Ce dossier est clôturé et ne peut plus être modifié.")
        return redirect('hospitalisation:detail', pk=pk)

    if request.method == 'POST':

        # ── DÉCHARGER via modale (decharge-form : champs principaux absents) ───
        if 'action_decharger' in request.POST:
            _save_resume_decharge(hosp, request.POST)
            ok, err = _transition_decharger(hosp, request.user)
            if err:
                messages.error(request, err)
            else:
                messages.success(request, 'Patient déchargé — sortie médicale enregistrée.')
            return redirect('hospitalisation:detail', pk=hosp.pk)

        # ── Sauvegarde complète : helpers + HospitalisationForm ─────────────────
        if mode_decharge_seule:
            _save_visites_infirmieres(hosp, request.POST, user=request.user)
            _save_visites_docteur(hosp, request.POST, user=request.user)
            _save_services_a_facturer(hosp, request.POST)
            _sync_soins_services(hosp)
            _save_resume_decharge(hosp, request.POST)
            ok, err = _transition_decharger(hosp, request.user)
            if err:
                messages.error(request, err)
            else:
                messages.success(request, 'Patient déchargé — sortie médicale enregistrée.')
            return redirect('hospitalisation:detail', pk=hosp.pk)
        if mode_soins_seuls:
            # Seuls les soins/visites sont sauvegardés
            _save_visites_infirmieres(hosp, request.POST, user=request.user)
            _save_visites_docteur(hosp, request.POST, user=request.user)
            _save_services_a_facturer(hosp, request.POST)
            _sync_soins_services(hosp)
            log_event(hosp, request.user, 'Soins infirmiers enregistrés.', type='modif')
            messages.success(request, 'Soins enregistrés.')
            return redirect('hospitalisation:detail', pk=hosp.pk)
        if not mode_chambre_seule:
            _save_checklist_admission(hosp, request.POST)
            _save_checklist_verification(hosp, request.POST)
            _save_evaluation_clinique(hosp, request.POST)
            _save_visites_infirmieres(hosp, request.POST, user=request.user)
            _save_visites_docteur(hosp, request.POST, user=request.user)
            _save_services_a_facturer(hosp, request.POST)
            _save_resume_decharge(hosp, request.POST)
        _post = _apply_lock_protection(
            hosp, request.POST, is_admin=is_admin,
            facture_bloquante=bool(facture_blocage),
            chambre_libre=mode_chambre_seule,
        )
        form = HospitalisationForm(_post, request.FILES, instance=hosp)
        form_ok = form.is_valid()
        if form_ok:
            from django.utils import timezone as tz
            updated = form.save(commit=False)
            updated.modifie_par = request.user
            updated.date_modification = tz.now()
            updated.save()
            form.save_m2m()
            _sync_soins_services(hosp)

        # ── Transitions workflow (CONFIRMER, HOSPITALISER, TERMINER) ────────────
        wf_action = next(
            (k for k in ('action_confirmer', 'action_hospitaliser', 'action_terminer')
             if k in request.POST),
            None
        )
        if wf_action:
            if not form_ok:
                messages.error(request, 'Corrigez les erreurs du formulaire avant de continuer.')
            else:
                if wf_action == 'action_confirmer':
                    if hosp.statut == 'brouillon':
                        ok, err = _transition_confirmer(hosp, request.user)
                        msg_ok = 'Demande confirmée — services à facturer générés.'
                    elif hosp.statut in ('confirme', 'hospitalise'):
                        ok, err = _sync_soins_only(hosp, request.user)
                        msg_ok = 'Soins enregistrés — services à facturer mis à jour.'
                    else:
                        ok, err = False, f"Impossible depuis le statut {hosp.get_statut_display()}."
                        msg_ok = ''
                elif wf_action == 'action_hospitaliser':
                    ok, err = _transition_installer(hosp, request.user)
                    msg_ok = 'Patient installé en observation.'
                elif wf_action == 'action_terminer':
                    ok, err = _transition_terminer(hosp, request.user)
                    msg_ok = 'Dossier clôturé administrativement.'
                else:
                    ok, err = False, 'Action inconnue.'
                    msg_ok = ''
                if ok:
                    messages.success(request, msg_ok)
                else:
                    messages.error(request, err)
                return redirect('hospitalisation:detail', pk=hosp.pk)
        elif form_ok:
            log_event(hosp, request.user, 'Fiche mise à jour.', type='modif')
            messages.success(request, 'Hospitalisation mise à jour.')
            return redirect('hospitalisation:detail', pk=hosp.pk)
        # Fall through : ré-affichage avec erreurs de formulaire
    else:
        form = HospitalisationForm(instance=hosp)

    # ── Contexte ───────────────────────────────────────────────────────────
    from facturation.models import Facture
    from laboratoire.models import AnalyseLaboratoire
    from consultations.models import Ordonnance

    eval_clin, _  = EvaluationClinique.objects.get_or_create(hospitalisation=hosp)
    resume, _     = ResumeDecharge.objects.get_or_create(hospitalisation=hosp)
    checklist_adm = list(hosp.checklist_admission.all())
    checklist_ver = list(hosp.checklist_verification.all())
    nb_adm        = len(checklist_adm)
    nb_adm_ok     = sum(1 for c in checklist_adm if c.verifie)
    nb_ver        = len(checklist_ver)
    nb_ver_ok     = sum(1 for c in checklist_ver if c.termine)

    has_chambre = bool(hosp.chambre_id)
    has_soins   = hosp.soins_apportes.exists()

    nb_factures    = Facture.objects.filter(hospitalisation=hosp).count()
    a_facture      = nb_factures > 0
    # SAF non encore facturés = on peut créer une nouvelle facture (service réel obligatoire)
    saf_non_factures = hosp.services_a_facturer.filter(facture__isnull=True, service__isnull=False).count()
    # Actions disponibles (visibilité + activation) pour ce dossier et cet utilisateur
    actions = get_actions_disponibles(hosp, request.user)
    peut_creer_facture = actions['creer_facture']['enabled']

    # Verrous d'en-tête : statut != brouillon ET champ renseigné ET non superutilisateur.
    # Champ vide → reste modifiable même après brouillon (ex : chambre non encore attribuée).
    _post_brouillon           = not is_admin and hosp.statut != 'brouillon'
    # En mode soins/chambre/décharge, aucun verrou visuel — le JS bloque sans griser
    _no_lock = mode_soins_seuls or mode_chambre_seule or mode_decharge_seule
    lock_patient              = _post_brouillon and bool(hosp.patient_id) and not _no_lock
    lock_medecin_traitant     = _post_brouillon and bool(hosp.medecin_traitant_id) and not _no_lock
    lock_chambre              = _post_brouillon and bool(hosp.chambre_id) and not mode_chambre_seule and not mode_soins_seuls and not mode_decharge_seule
    lock_date_admission       = _post_brouillon and bool(hosp.date_admission) and not _no_lock
    lock_mise_en_observation  = _post_brouillon and bool((hosp.mise_en_observation or '').strip()) and not _no_lock
    lock_infirmiere_primaire  = _post_brouillon and bool(hosp.infirmiere_primaire_id) and not _no_lock
    lecture_seule_totale = (
        not is_admin and hosp.statut in ('termine', 'annule')
    )
    nb_ordonnances = Ordonnance.objects.filter(consultation__patient=hosp.patient).count()
    nb_labo        = AnalyseLaboratoire.objects.filter(patient=hosp.patient).count()
    nb_attribution = 1 if hosp.chambre else 0
    nb_evaluations = hosp.fiches_visite.count()

    medecins_list  = list(Medecin.objects.filter(actif=True).order_by('employe__nom'))
    unites_list    = list(UniteMesure.objects.filter(actif=True).order_by('nom'))
    services_list  = list(Articleservice.objects.filter(actif=True, categorie__code='SN').order_by('nom'))

    # Soins déjà sur une facture → verrouillés (non supprimables dans soins_apportes)
    soins_factures_ids = list(hosp.services_a_facturer.filter(
        source='soin', facture__isnull=False
    ).values_list('service_id', flat=True))

    # Visites infirmières dont la facture est payée → lignes non modifiables
    vi_payees_ids = set(hosp.services_a_facturer.filter(
        source='visite_infirmiere', facture__statut='payee'
    ).values_list('ordre', flat=True))

    soins_pour_visites = list(Articleservice.objects.filter(
        actif=True, categorie__code='SN'
    ).order_by('nom'))
    deces_list     = list(RegistreDeces.objects.filter(patient=hosp.patient))

    from django.urls import reverse
    url_facture = reverse('hospitalisation:creer_facture', kwargs={'pk': hosp.pk})
    factures_list = list(Facture.objects.filter(hospitalisation=hosp).order_by('-date_emission'))
    url_labo    = f"{reverse('laboratoire_create')}?patient={hosp.patient_id}&back=/hospitalisation/{hosp.pk}/modifier/"

    return render(request, 'hospitalisation/form.html', {
        'form':               form,
        'hosp':               hosp,
        'titre':              hosp.numero,
        'edit':               True,
        'is_admin':           is_admin,
        'a_facture':          a_facture,
        'peut_creer_facture': peut_creer_facture,
        'saf_non_factures':   saf_non_factures,
        'has_chambre':        has_chambre,
        'has_soins':          has_soins,
        'soins_factures_ids': soins_factures_ids,
        'vi_payees_ids':      vi_payees_ids,
        # Stats
        'nb_factures':        nb_factures,
        'nb_ordonnances':     nb_ordonnances,
        'nb_attribution':     nb_attribution,
        'nb_evaluations':     nb_evaluations,
        'nb_labo':            nb_labo,
        # Logs
        'logs':               get_logs(hosp),
        # Tab 2 - Checklists
        'checklist_adm':      checklist_adm,
        'checklist_ver':      checklist_ver,
        'pct_adm':            round(nb_adm_ok * 100 / nb_adm) if nb_adm else 0,
        'pct_ver':            round(nb_ver_ok * 100 / nb_ver) if nb_ver else 0,
        # Tab 3 - Évaluation clinique
        'eval_clin':          eval_clin,
        # Tab 4 - Soins
        'visites_inf':        list(hosp.visites_infirmieres.select_related('soin','unite_mesure','infirmiere').all()),
        'visites_doc':        list(hosp.visites_docteur.select_related('soin','docteur').all()),
        'medecins_list':      medecins_list,
        'unites_list':        unites_list,
        'soins_pour_visites': soins_pour_visites,
        # Tab 5 - Services à facturer
        'services_a_facturer': list(hosp.services_a_facturer.select_related('service','unite_mesure','facture').all()),
        'services_list':       services_list,
        # Tab 6 - Résumé de décharge
        'resume':              resume,
        'deces_list':          deces_list,
        # Factures liées
        'factures_list':       factures_list,
        # URLs externes
        'url_facture': url_facture,
        'url_labo':    url_labo,
        # Matrice actions × permissions × conditions métier
        'actions':              actions,
        'lock_patient':              lock_patient,
        'lock_medecin_traitant':     lock_medecin_traitant,
        'lock_chambre':              lock_chambre,
        'lock_date_admission':       lock_date_admission,
        'lock_mise_en_observation':  lock_mise_en_observation,
        'lock_infirmiere_primaire':  lock_infirmiere_primaire,
        'lecture_seule_totale': lecture_seule_totale,
        'facture_blocage':      facture_blocage,
        'mode_chambre_seule':    mode_chambre_seule,
        'mode_soins_seuls':      mode_soins_seuls,
        'mode_decharge_seule':   mode_decharge_seule,
    })


# ─── VUES DE TRANSITION DE STATUT ─────────────────────────────────────────────
# Chaque vue est POST-only. Répond en JSON si X-Requested-With: XMLHttpRequest,
# sinon redirect classique (dégradé gracieux).

def _boutons_extra(hosp, user):
    """
    Calcule les boutons liens (hors get_actions_disponibles) : Modifier,
    Attribuer une chambre, Ajouter un soin. Utilisé au rendu initial de la
    page ET dans _etat_payload, pour que le re-rendu JS après une transition
    reste cohérent avec le template.
    """
    from facturation.models import Facture

    is_admin = user.is_superuser
    facture_payee = Facture.objects.filter(hospitalisation=hosp, statut='payee').exists()

    # Bouton Modifier : visible pour les utilisateurs change_hospitalisation dès le statut
    # confirmé, mais grisé/incliquable tant que la facture n'est pas payée. L'admin reste
    # inchangé (toujours actif), comme partout ailleurs dans ce module.
    _peut_modifier_base = (
        user.has_perm('hospitalisation.change_hospitalisation')
        and hosp.statut == 'confirme'
    )
    peut_modifier = is_admin or _peut_modifier_base
    modifier_enabled = is_admin or (_peut_modifier_base and facture_payee)
    modifier_raison = '' if modifier_enabled else "La facture doit être payée avant de modifier le dossier"
    # Bouton Attribuer une chambre : utilisateurs can_installer_patient ou admin (confirme + facture payée)
    peut_attribuer_chambre = (
        user.has_perm('hospitalisation.can_installer_patient')
        and hosp.statut == 'confirme'
        and facture_payee
    )
    # Bouton Ajouter un soin : can_ajouter_soin ou admin, mais seulement statut hospitalise
    # (jamais après décharge/clôture/annulation, même pour l'admin)
    peut_ajouter_soin = (
        hosp.statut == 'hospitalise'
        and (is_admin or user.has_perm('hospitalisation.can_ajouter_soin'))
    )
    return {
        'peut_modifier':          peut_modifier,
        'modifier_enabled':       modifier_enabled,
        'modifier_raison':        modifier_raison,
        'peut_attribuer_chambre': peut_attribuer_chambre,
        'peut_ajouter_soin':      peut_ajouter_soin,
    }


def _etat_payload(hosp, user):
    """Construit le dict d'état courant renvoyé par /etat/ et les transitions."""
    from facturation.models import Facture
    from django.urls import reverse
    from .services import get_actions_disponibles

    actions = get_actions_disponibles(hosp, user)
    saf_nf = hosp.services_a_facturer.filter(facture__isnull=True, service__isnull=False).count()

    factures = list(
        Facture.objects.filter(hospitalisation=hosp)
        .values('pk', 'numero', 'statut', 'montant_total', 'montant_paye')
        .order_by('-date_emission')
    )

    return {
        'statut':             hosp.statut,
        'statut_display':     hosp.get_statut_display(),
        'actions':            actions,
        'peut_creer_facture': actions['creer_facture']['enabled'],
        'saf_non_factures':   saf_nf,
        'has_chambre':        bool(hosp.chambre_id),
        'has_soins':          hosp.soins_apportes.exists(),
        'url_facture':        reverse('hospitalisation:creer_facture', kwargs={'pk': hosp.pk}),
        'heure_entree':       hosp.heure_entree.isoformat() if hosp.heure_entree else None,
        'heure_sortie':       hosp.heure_sortie.isoformat() if hosp.heure_sortie else None,
        'date_termine':       hosp.date_termine.isoformat() if hosp.date_termine else None,
        'duree_observation':  hosp.duree_observation,
        'factures':           factures,
        'nb_factures':        len(factures),
        **_boutons_extra(hosp, user),
    }


@login_required(login_url='login')
def hospitalisation_etat(request, pk):
    """GET → JSON état courant (badge, pipeline, boutons, durée)."""
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    return JsonResponse(_etat_payload(hosp, request.user))


@login_required(login_url='login')
def hospitalisation_ajouter_soin(request, pk):
    """Endpoint POST : ajoute un seul soin à une hospitalisation confirmée ou en cours."""
    from services.models import Articleservice
    hosp = get_object_or_404(Hospitalisation, pk=pk)

    if request.method != 'POST':
        return redirect('hospitalisation:edit', pk=pk)

    if hosp.statut not in ('confirme', 'hospitalise'):
        return JsonResponse({'ok': False, 'error': "Statut incompatible."}, status=400)

    soin_pk = request.POST.get('soin_pk', '').strip()
    if not soin_pk:
        return JsonResponse({'ok': False, 'error': "Soin non spécifié."}, status=400)

    try:
        soin = Articleservice.objects.get(pk=soin_pk, actif=True)
    except Articleservice.DoesNotExist:
        return JsonResponse({'ok': False, 'error': "Soin introuvable."}, status=404)

    hosp.soins_apportes.add(soin)
    _sync_soins_services(hosp)
    from django.utils import timezone as tz
    hosp.modifie_par = request.user
    hosp.date_modification = tz.now()
    hosp.save(update_fields=['modifie_par', 'date_modification'])
    log_event(hosp, request.user, f'Soin ajouté : {soin.nom}', type='modif')

    from django.urls import reverse
    return JsonResponse({
        'ok': True,
        'soin_nom': soin.nom,
        'redirect': reverse('hospitalisation:detail', kwargs={'pk': pk}),
    })


@login_required(login_url='login')
def hospitalisation_confirmer(request, pk):
    """brouillon → confirme."""
    if request.method != 'POST':
        return redirect('hospitalisation:detail', pk=pk)
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    ok, err = _transition_confirmer(hosp, request.user)
    if _is_ajax(request):
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        hosp.refresh_from_db()
        return JsonResponse({'ok': True, 'reload': True, **_etat_payload(hosp, request.user)})
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Demande confirmée — services à facturer générés.')
    return redirect('hospitalisation:detail', pk=pk)


@login_required(login_url='login')
def hospitalisation_installer(request, pk):
    """confirme → hospitalise."""
    if request.method != 'POST':
        return redirect('hospitalisation:detail', pk=pk)
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    ok, err = _transition_installer(hosp, request.user)
    if _is_ajax(request):
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        hosp.refresh_from_db()
        return JsonResponse({'ok': True, **_etat_payload(hosp, request.user)})
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Patient installé en observation.')
    return redirect('hospitalisation:detail', pk=pk)


@login_required(login_url='login')
def hospitalisation_decharger(request, pk):
    """hospitalise → decharge."""
    if request.method != 'POST':
        return redirect('hospitalisation:detail', pk=pk)
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    ok, err = _transition_decharger(hosp, request.user)
    if _is_ajax(request):
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        hosp.refresh_from_db()
        return JsonResponse({'ok': True, **_etat_payload(hosp, request.user)})
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Patient déchargé — sortie médicale enregistrée.')
    return redirect('hospitalisation:detail', pk=pk)


@login_required(login_url='login')
def hospitalisation_terminer(request, pk):
    """decharge → termine."""
    if request.method != 'POST':
        return redirect('hospitalisation:detail', pk=pk)
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    ok, err = _transition_terminer(hosp, request.user)
    if _is_ajax(request):
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        hosp.refresh_from_db()
        return JsonResponse({'ok': True, **_etat_payload(hosp, request.user)})
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Dossier clôturé administrativement.')
    return redirect('hospitalisation:detail', pk=pk)


@login_required(login_url='login')
def hospitalisation_annuler(request, pk):
    """brouillon/confirme → annule."""
    if request.method != 'POST':
        return redirect('hospitalisation:detail', pk=pk)
    hosp = get_object_or_404(Hospitalisation, pk=pk)
    motif = request.POST.get('motif_annulation', '').strip()
    ok, err = _transition_annuler(hosp, request.user, motif=motif)
    if _is_ajax(request):
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
        hosp.refresh_from_db()
        return JsonResponse({'ok': True, 'reload': True, **_etat_payload(hosp, request.user)})
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Hospitalisation annulée.')
    return redirect('hospitalisation:detail', pk=pk)


# ─── VUE DÉTAIL (lecture + transitions fetch) ─────────────────────────────────

@login_required(login_url='login')
def hospitalisation_detail(request, pk):
    """Détail enrichi : pipeline, actions, onglets, SAF, visites, factures, décharge (lecture seule)."""
    from facturation.models import Facture
    from .services import get_actions_disponibles
    from django.utils import timezone as tz

    hosp     = get_object_or_404(Hospitalisation, pk=pk)
    is_admin = request.user.is_superuser

    eval_clin, _ = EvaluationClinique.objects.get_or_create(hospitalisation=hosp)
    resume, _    = ResumeDecharge.objects.get_or_create(hospitalisation=hosp)

    nb_factures      = Facture.objects.filter(hospitalisation=hosp).count()
    saf_non_factures = hosp.services_a_facturer.filter(
        facture__isnull=True, service__isnull=False
    ).count()
    actions = get_actions_disponibles(hosp, request.user)

    lecture_seule_totale = (not is_admin and hosp.statut in ('termine', 'annule'))
    facture_blocage = _get_facture_blocage(hosp)
    boutons_extra = _boutons_extra(hosp, request.user)
    peut_modifier = boutons_extra['peut_modifier']
    modifier_enabled = boutons_extra['modifier_enabled']
    modifier_raison = boutons_extra['modifier_raison']
    peut_attribuer_chambre = boutons_extra['peut_attribuer_chambre']
    peut_ajouter_soin = boutons_extra['peut_ajouter_soin']

    factures_list = list(Facture.objects.filter(hospitalisation=hosp).order_by('-date_emission'))

    from django.urls import reverse
    url_facture = reverse('hospitalisation:creer_facture', kwargs={'pk': hosp.pk})

    return render(request, 'hospitalisation/detail.html', {
        'hosp':                hosp,
        'titre':               hosp.numero,
        'is_admin':            is_admin,
        'saf_non_factures':    saf_non_factures,
        'has_chambre':         bool(hosp.chambre_id),
        'has_soins':           hosp.soins_apportes.exists(),
        'nb_factures':         nb_factures,
        'logs':                get_logs(hosp),
        'eval_clin':           eval_clin,
        'resume':              resume,
        'visites_inf':         list(hosp.visites_infirmieres.select_related(
                                   'soin', 'unite_mesure', 'infirmiere').all()),
        'visites_doc':         list(hosp.visites_docteur.select_related(
                                   'soin', 'docteur').all()),
        'services_a_facturer': list(hosp.services_a_facturer.select_related(
                                   'service', 'unite_mesure', 'facture').all()),
        'factures_list':       factures_list,
        'actions':             actions,
        'lecture_seule_totale': lecture_seule_totale,
        'facture_blocage':     facture_blocage,
        'peut_modifier':           peut_modifier,
        'modifier_enabled':        modifier_enabled,
        'modifier_raison':         modifier_raison,
        'peut_attribuer_chambre':  peut_attribuer_chambre,
        'peut_ajouter_soin':       peut_ajouter_soin,
        'url_facture':             url_facture,
        'today':                   tz.now().date(),
    })




@login_required(login_url='login')
def chambres_list(request):
    q = request.GET.get('q', '').strip()
    type_chambre = request.GET.get('type', '').strip()
    dispo = request.GET.get('dispo', '').strip()

    qs = Chambre.objects.order_by('salle_no')

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(salle_no__icontains=q))
    if type_chambre:
        qs = qs.filter(type_chambre=type_chambre)
    if dispo == '1':
        qs = qs.filter(statut=True)
    elif dispo == '0':
        qs = qs.filter(statut=False)

    stats = {
        'total':       Chambre.objects.count(),
        'disponibles': Chambre.objects.filter(statut=True).count(),
        'occupees':    Chambre.objects.filter(statut=False).count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'hospitalisation/chambres/list.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'stats': stats,
        'q': q,
        'type_chambre': type_chambre,
        'dispo': dispo,
        'types': Chambre.TYPE,
    })


@login_required(login_url='login')
def chambre_detail(request, pk):
    chambre = get_object_or_404(Chambre, pk=pk)
    return render(request, 'hospitalisation/chambres/detail.html', {'chambre': chambre})


@login_required(login_url='login')
def chambre_create(request):
    if request.method == 'POST':
        form = ChambreForm(request.POST)
        if form.is_valid():
            chambre = form.save()
            messages.success(request, f'Chambre « {chambre.nom} » créée (N° {chambre.salle_no}).')
            return redirect('hospitalisation:chambre_detail', pk=chambre.pk)
    else:
        form = ChambreForm()
    return render(request, 'hospitalisation/chambres/form.html', {
        'form': form,
        'titre': 'Nouvelle chambre',
        'edit': False,
    })


@login_required(login_url='login')
def chambre_edit(request, pk):
    chambre = get_object_or_404(Chambre, pk=pk)
    if request.method == 'POST':
        form = ChambreForm(request.POST, instance=chambre)
        if form.is_valid():
            form.save()
            messages.success(request, f'Chambre « {chambre.nom} » mise à jour.')
            return redirect('hospitalisation:chambre_detail', pk=chambre.pk)
    else:
        form = ChambreForm(instance=chambre)
    return render(request, 'hospitalisation/chambres/form.html', {
        'form': form,
        'chambre': chambre,
        'titre': f'Modifier — {chambre.nom or chambre.salle_no}',
        'edit': True,
    })



@login_required(login_url='login')
def registre_deces(request):
    q      = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()

    qs = RegistreDeces.objects.select_related(
        'patient', 'medecin', 'hospitalisation'
    ).order_by('-date_deces')

    if q:
        qs = qs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(code__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'hospitalisation/deces/list.html', {
        'page_obj': page_obj,
        'total':    qs.count(),
        'q':        q,
        'statut':   statut,
    })


@login_required(login_url='login')
def deces_detail(request, pk):
    deces = get_object_or_404(RegistreDeces, pk=pk)
    return render(request, 'hospitalisation/deces/detail.html', {
        'deces':        deces,
        'peut_modifier': request.user.is_superuser or deces.statut != 'termine',
    })


@login_required(login_url='login')
def deces_create(request):
    if request.method == 'POST':
        form = RegistreDecesForm(request.POST)
        if form.is_valid():
            deces = form.save()
            messages.success(request, f'Enregistrement {deces.code} créé.')
            return redirect('hospitalisation:deces_detail', pk=deces.pk)
    else:
        form = RegistreDecesForm()
    return render(request, 'hospitalisation/deces/form.html', {
        'form':  form,
        'titre': 'Nouveau',
        'edit':  False,
    })


@login_required(login_url='login')
def deces_edit(request, pk):
    deces = get_object_or_404(RegistreDeces, pk=pk)
    if deces.statut == 'termine' and not request.user.is_superuser:
        messages.warning(request, 'Cet enregistrement est clôturé et ne peut plus être modifié.')
        return redirect('hospitalisation:deces_detail', pk=pk)
    if request.method == 'POST':
        if 'terminer' in request.POST:
            deces.statut = 'termine'
            deces.save()
            messages.success(request, 'Enregistrement marqué comme terminé.')
            return redirect('hospitalisation:deces_detail', pk=pk)
        form = RegistreDecesForm(request.POST, instance=deces)
        if form.is_valid():
            form.save()
            messages.success(request, 'Enregistrement mis à jour.')
            return redirect('hospitalisation:deces_detail', pk=pk)
    else:
        form = RegistreDecesForm(instance=deces)
    return render(request, 'hospitalisation/deces/form.html', {
        'form':  form,
        'deces': deces,
        'titre': deces.code,
        'edit':  True,
    })


@login_required(login_url='login')


@login_required(login_url='login')
def configuration(request):
    return render(request, 'hospitalisation/configuration/index.html', {})


@login_required(login_url='login')
def config_batiments(request):
    return render(request, 'hospitalisation/configuration/batiments.html', {})


@login_required(login_url='login')
def config_liste_admission(request):
    q = request.GET.get('q', '').strip()
    qs = ListeControleAdmission.objects.all()
    if q:
        qs = qs.filter(Q(item__icontains=q) | Q(remarques__icontains=q))
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'hospitalisation/configuration/liste_admission/list.html', {
        'page_obj': page_obj,
        'q': q,
    })


@login_required(login_url='login')
def liste_admission_create(request):
    if request.method == 'POST':
        form = ListeControleAdmissionForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Élément « {obj.item} » créé.')
            return redirect('hospitalisation:config_liste_admission')
    else:
        form = ListeControleAdmissionForm()
    return render(request, 'hospitalisation/configuration/liste_admission/form.html', {
        'form':  form,
        'titre': 'Nouveau',
        'edit':  False,
    })


@login_required(login_url='login')
def liste_admission_edit(request, pk):
    obj = get_object_or_404(ListeControleAdmission, pk=pk)
    if request.method == 'POST':
        form = ListeControleAdmissionForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Élément « {obj.item} » modifié.')
            return redirect('hospitalisation:config_liste_admission')
    else:
        form = ListeControleAdmissionForm(instance=obj)
    return render(request, 'hospitalisation/configuration/liste_admission/form.html', {
        'form':  form,
        'obj':   obj,
        'titre': obj.item,
        'edit':  True,
    })


@login_required(login_url='login')
def liste_admission_delete(request, pk):
    obj = get_object_or_404(ListeControleAdmission, pk=pk)
    if request.method == 'POST':
        nom = obj.item
        obj.delete()
        messages.success(request, f'Élément « {nom} » supprimé.')
    return redirect('hospitalisation:config_liste_admission')


@login_required(login_url='login')
def config_liste_service(request):
    q = request.GET.get('q', '').strip()
    qs = ListeVerificationService.objects.all()
    if q:
        qs = qs.filter(item__icontains=q)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'hospitalisation/configuration/liste_service/list.html', {
        'page_obj': page_obj,
        'q': q,
    })


@login_required(login_url='login')
def liste_service_create(request):
    if request.method == 'POST':
        form = ListeVerificationServiceForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Élément « {obj.item} » créé.')
            return redirect('hospitalisation:config_liste_service')
    else:
        form = ListeVerificationServiceForm()
    return render(request, 'hospitalisation/configuration/liste_service/form.html', {
        'form':  form,
        'titre': 'Nouveau',
        'edit':  False,
    })


@login_required(login_url='login')
def liste_service_edit(request, pk):
    obj = get_object_or_404(ListeVerificationService, pk=pk)
    if request.method == 'POST':
        form = ListeVerificationServiceForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Élément « {obj.item} » modifié.')
            return redirect('hospitalisation:config_liste_service')
    else:
        form = ListeVerificationServiceForm(instance=obj)
    return render(request, 'hospitalisation/configuration/liste_service/form.html', {
        'form':  form,
        'obj':   obj,
        'titre': obj.item,
        'edit':  True,
    })


@login_required(login_url='login')
def liste_service_delete(request, pk):
    obj = get_object_or_404(ListeVerificationService, pk=pk)
    if request.method == 'POST':
        nom = obj.item
        obj.delete()
        messages.success(request, f'Élément « {nom} » supprimé.')
    return redirect('hospitalisation:config_liste_service')
