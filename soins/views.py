import json
import re
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test

_staff_required = user_passes_test(lambda u: u.is_staff, login_url='login')
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone
from .models import Soin, ProcedureSoin, Maladie
from .forms import SoinForm, ProcedureSoinForm
from patients.models import RendezVous, Patient
from laboratoire.models import AnalyseLaboratoire, ExamenImagerie
from employer.models import Employe
from services.models import Articleservice


_STATUT_PROCEDURE_MAP = {
    'brouillon': 'brouillon',
    'en_cours':  'en_cours',
    'termine':   'termine',
    'annule':    'annule',
}


def _has_at_least_one_ligne(post_data):
    """Retourne True si au moins une ligne de soin valide (patient + service) existe."""
    for key, value in post_data.items():
        if re.match(r'^lignes\[(\d+)\]\[service\]$', key) and value:
            return True
    return False


def _sync_procedures(soin, statut):
    """Synchronise le statut de toutes les procédures du soin."""
    soin.procedures.all().update(statut=statut)


def _parse_prix(val):
    if not val:
        return 0
    import re as _re
    digits = _re.sub(r'\D', '', str(val))
    try:
        return int(digits) if digits else 0
    except (ValueError, TypeError):
        return 0


def _save_procedures_from_lignes(soin, post_data):
    """Supprime les anciennes procédures liées à ce soin puis recrée depuis les lignes du POST."""
    ProcedureSoin.objects.filter(soin=soin).delete()
    lignes = {}
    for key, value in post_data.items():
        m = re.match(r'^lignes\[(\d+)\]\[(\w+)\]$', key)
        if m:
            idx, field = m.group(1), m.group(2)
            if idx not in lignes:
                lignes[idx] = {}
            lignes[idx][field] = value
    for ligne in lignes.values():
        patient_id = ligne.get('patient') or None
        if not patient_id:
            continue
        service_id  = ligne.get('service')   or None
        if not service_id:
            continue
        infirmier_id = ligne.get('infirmier') or None
        date_str    = ligne.get('date')       or None
        prix_raw    = ligne.get('prix', '0')
        prix = _parse_prix(prix_raw)
        date = timezone.now()
        if date_str:
            try:
                date = timezone.make_aware(datetime.strptime(date_str, '%Y-%m-%d'))
            except ValueError:
                pass
        ProcedureSoin.objects.create(
            soin=soin,
            patient_id=patient_id,
            infirmier_id=infirmier_id,
            soin_type_id=service_id,
            departement=soin.departement,
            prix=prix,
            date=date,
            statut='brouillon',
        )


def _patient_counts(patient):
    return {
        'rdv': RendezVous.objects.filter(patient=patient).count(),
        'analyses': AnalyseLaboratoire.objects.filter(patient=patient).count(),
        'imageries': ExamenImagerie.objects.filter(patient=patient).count(),
    }


def _form_extras():
    services = list(Articleservice.objects.filter(
        type_article__in=['service', 'prestation']
    ).values('pk', 'nom', 'prix_vente'))
    employes = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    patients = list(Patient.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms', 'code_patient'))
    rdvs = list(RendezVous.objects.select_related('patient').values(
        'pk', 'patient_id', 'date_heure', 'type_rdv', 'statut', 'motif'
    ).order_by('-date_heure')[:500])
    return {
        'services_json': json.dumps(services, default=str),
        'employes_json': json.dumps(employes),
        'patients_json': json.dumps(patients),
        'rdvs_json': json.dumps(rdvs, default=str),
    }


@login_required(login_url='login')
def soins_patient_counts(request):
    from django.http import JsonResponse
    patient_id = request.GET.get('patient_id', '').strip()
    if not patient_id:
        return JsonResponse({'rdv': 0, 'examens': 0, 'analyses': 0})
    try:
        pat = Patient.objects.get(pk=patient_id)
        c = _patient_counts(pat)
        return JsonResponse({
            'rdv': c['rdv'],
            'examens': c['analyses'] + c['imageries'],
            'analyses': c['analyses'],
        })
    except Patient.DoesNotExist:
        return JsonResponse({'rdv': 0, 'examens': 0, 'analyses': 0})


@login_required(login_url='login')
def soins_list(request):
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    date_filtre = request.GET.get('date', '').strip()
    patient_id = request.GET.get('patient_id', '').strip()

    soins = Soin.objects.select_related(
        'patient', 'infirmier', 'departement', 'service_inscription'
    ).annotate(
        est_paye=Exists(
            ProcedureSoin.objects.filter(
                soin=OuterRef('pk'),
                facture__statut__in=['payee', 'partielle']
            )
        )
    ).order_by('-date_heure')

    if patient_id:
        soins = soins.filter(patient_id=patient_id)
    elif q:
        soins = soins.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(infirmier__nom__icontains=q) |
            Q(motif__icontains=q)
        )

    if statut:
        soins = soins.filter(statut=statut)

    if date_filtre:
        soins = soins.filter(date_heure__date=date_filtre)

    total = soins.count()
    paginator = Paginator(soins, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    today = timezone.now().date()
    stats = {
        'aujourdhui': Soin.objects.filter(date_heure__date=today).count(),
        'ce_mois': Soin.objects.filter(date_heure__month=today.month, date_heure__year=today.year).count(),
        'en_attente': Soin.objects.filter(statut='en_attente_de_paiement').count(),
        'en_cours': Soin.objects.filter(statut='en_cours').count(),
        'termines': Soin.objects.filter(statut='termine').count(),
    }

    patient_filtre = None
    if patient_id:
        try:
            patient_filtre = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            pass

    return render(request, 'soins/list.html', {
        'page_obj': page_obj,
        'total': total,
        'stats': stats,
        'q': q,
        'statut': statut,
        'date_filtre': date_filtre,
        'patient_id': patient_id,
        'patient_filtre': patient_filtre,
        'user_peut_creer_facture': request.user.has_perm('soins.can_creer_facture'),
    })


@login_required(login_url='login')
def soins_detail(request, pk):
    soin = get_object_or_404(
        Soin.objects.select_related('patient', 'infirmier', 'rendez_vous', 'departement', 'service_inscription', 'facture'),
        pk=pk
    )
    counts = _patient_counts(soin.patient)
    counts['examens'] = counts['analyses'] + counts['imageries']
    counts['soins'] = ProcedureSoin.objects.filter(patient=soin.patient).count()
    procedures = list(soin.procedures.select_related('soin_type', 'infirmier', 'facture').all())
    total_prix = sum(p.prix for p in procedures)
    facture_payee = (
        soin.facture is not None and
        soin.facture.statut in ('payee', 'partielle', 'comptabilisee')
    )
    # Auto-sync : si la facture est payée mais le soin encore en attente → passer en_cours
    if facture_payee and soin.statut == 'en_attente_de_paiement':
        soin.statut = 'en_cours'
        soin.save(update_fields=['statut'])
    peut_administrer = (
        soin.statut == 'en_cours' and
        facture_payee and
        (request.user.has_perm('soins.can_administrer_soin') or request.user.is_superuser)
    )
    peut_creer_facture = (
        soin.statut == 'en_attente_de_paiement' and
        not soin.facture_id and
        request.user.has_perm('soins.can_creer_facture')
    )
    est_caisse = request.user.has_perm('soins.can_creer_facture') or request.user.is_superuser
    peut_voir_facture = (
        soin.facture_id is not None and
        (facture_payee or est_caisse)
    )
    return render(request, 'soins/detail.html', {
        'soin': soin,
        'counts': counts,
        'procedures': procedures,
        'total_prix': total_prix,
        'facture_payee': facture_payee,
        'peut_administrer': peut_administrer,
        'peut_creer_facture': peut_creer_facture,
        'peut_voir_facture': peut_voir_facture,
    })


@login_required(login_url='login')
def soins_create(request):
    if request.method == 'POST':
        form = SoinForm(request.POST, request.FILES)
        if form.is_valid():
            soin = form.save(commit=False)
            action = request.POST.get('action', 'save')
            if action == 'enregistrer':
                if not _has_at_least_one_ligne(request.POST):
                    messages.error(request, "Ajoutez au moins une ligne de soin avant d'enregistrer.")
                    extras = _form_extras()
                    return render(request, 'soins/form.html', {
                        'form': form, 'is_new': True,
                        'counts': {'rdv': 0, 'examens': 0, 'analyses': 0},
                        'procedures_json': '[]', **extras,
                    })
                soin.statut = 'en_attente_de_paiement'
            else:
                soin.statut = 'brouillon'
            soin.save()
            _save_procedures_from_lignes(soin, request.POST)
            return redirect('soins:detail', pk=soin.pk)
    else:
        form = SoinForm()

    extras = _form_extras()
    patient_id = request.GET.get('patient_id', '')
    rdv_id = request.GET.get('rdv_id', '')
    initial = {}
    counts = {'rdv': 0, 'examens': 0, 'analyses': 0}
    if patient_id:
        try:
            pat = Patient.objects.get(pk=patient_id)
            initial['patient'] = pat
            c = _patient_counts(pat)
            counts = {'rdv': c['rdv'], 'examens': c['analyses'] + c['imageries'], 'analyses': c['analyses']}
        except Patient.DoesNotExist:
            pass
    if rdv_id:
        try:
            initial['rendez_vous'] = RendezVous.objects.get(pk=rdv_id)
        except RendezVous.DoesNotExist:
            pass
    if initial and request.method == 'GET':
        form = SoinForm(initial=initial)
    return render(request, 'soins/form.html', {
        'form': form,
        'is_new': True,
        'counts': counts,
        'procedures_json': '[]',
        **extras,
    })


@login_required(login_url='login')
def soins_edit(request, pk):
    soin = get_object_or_404(Soin, pk=pk)

    # Verrouillage : seul l'admin peut modifier un soin hors brouillon
    if soin.statut != 'brouillon' and not request.user.is_superuser:
        messages.warning(request, "Ce soin ne peut plus être modifié.")
        return redirect('soins:detail', pk=pk)

    if request.method == 'POST':
        form = SoinForm(request.POST, request.FILES, instance=soin)
        if form.is_valid():
            soin = form.save(commit=False)
            action = request.POST.get('action', 'save')
            if action == 'enregistrer':
                if not _has_at_least_one_ligne(request.POST):
                    messages.error(request, "Ajoutez au moins une ligne de soin avant d'enregistrer.")
                else:
                    soin.statut = 'en_attente_de_paiement'
                    soin.save()
                    _save_procedures_from_lignes(soin, request.POST)
                    return redirect('soins:detail', pk=soin.pk)
            else:
                soin.statut = 'brouillon'
            soin.save()
            _save_procedures_from_lignes(soin, request.POST)
            return redirect('soins:detail', pk=soin.pk)
    else:
        form = SoinForm(instance=soin)
        rdv_id = request.GET.get('rdv_id', '')
        if rdv_id and not soin.rendez_vous_id:
            try:
                soin.rendez_vous = RendezVous.objects.get(pk=rdv_id)
                soin.save(update_fields=['rendez_vous'])
                form = SoinForm(instance=soin)
            except RendezVous.DoesNotExist:
                pass

    counts = _patient_counts(soin.patient)
    counts['examens'] = counts['analyses'] + counts['imageries']
    extras = _form_extras()

    procedures_json = json.dumps([
        {
            'patient':      p.patient_id,
            'patient_code': p.patient.code_patient if p.patient else '',
            'service':      p.soin_type_id,
            'prix':         float(p.prix),
            'infirmier':    p.infirmier_id,
            'date':         p.date.strftime('%Y-%m-%d') if p.date else '',
            'statut':       p.statut,
        }
        for p in soin.procedures.select_related('patient', 'infirmier', 'soin_type').all()
    ], default=str)

    return render(request, 'soins/form.html', {
        'form': form,
        'soin': soin,
        'is_new': False,
        'counts': counts,
        'procedures_json': procedures_json,
        **extras,
    })


@login_required(login_url='login')
def soins_administrer(request, pk):
    """Marque le soin comme terminé (dispensé). Réservé au groupe Soins."""
    if not (request.user.has_perm('soins.can_administrer_soin') or request.user.is_superuser):
        messages.error(request, "Vous n'avez pas la permission d'administrer un soin.")
        return redirect('soins:detail', pk=pk)
    if request.method != 'POST':
        return redirect('soins:detail', pk=pk)
    soin = get_object_or_404(Soin.objects.select_related('facture'), pk=pk)
    if soin.statut != 'en_cours':
        messages.error(request, "Ce soin n'est pas en cours.")
        return redirect('soins:detail', pk=pk)
    if not soin.facture or soin.facture.statut not in ('payee', 'partielle', 'comptabilisee'):
        messages.error(request, "La facture doit être payée avant d'administrer le soin.")
        return redirect('soins:detail', pk=pk)
    soin.statut = 'termine'
    soin.save(update_fields=['statut'])
    _sync_procedures(soin, 'termine')
    messages.success(request, f"Soin {soin.numero} marqué comme terminé.")
    return redirect('soins:detail', pk=pk)


@login_required(login_url='login')
def soins_creer_facture(request, pk):
    """Crée la facture d'un soin (Caisse uniquement)."""
    if not request.user.has_perm('soins.can_creer_facture'):
        messages.error(request, "Vous n'avez pas la permission de créer une facture.")
        return redirect('soins:detail', pk=pk)
    soin = get_object_or_404(Soin.objects.select_related('patient', 'facture'), pk=pk)
    if soin.statut != 'en_attente_de_paiement':
        messages.error(request, "Ce soin n'est pas en attente de paiement.")
        return redirect('soins:detail', pk=pk)
    if soin.facture_id:
        from django.urls import reverse
        detail_url = reverse('soins:facture_detail', kwargs={'pk': soin.facture.pk})
        back_url = f'/soins/{soin.pk}/'
        return redirect(f'{detail_url}?next={back_url}')

    from facturation.models import Facture, LigneFacture
    procedures = list(soin.procedures.select_related('soin_type').all())
    if not procedures:
        messages.error(request, "Ce soin n'a pas de lignes de soin à facturer.")
        return redirect('soins:detail', pk=pk)

    def _prix_effectif(proc):
        if proc.prix:
            return proc.prix
        return proc.soin_type.prix_vente if proc.soin_type else 0

    total = sum(_prix_effectif(p) for p in procedures)
    facture = Facture.objects.create(
        patient=soin.patient,
        cree_par=request.user,
        type_facture='autre',
        statut='emise',
        montant_total=total,
    )
    for proc in procedures:
        prix = _prix_effectif(proc)
        LigneFacture.objects.create(
            facture=facture,
            libelle=proc.soin_type.nom if proc.soin_type else f"Soin – {proc.numero}",
            quantite=1,
            prix_unitaire=prix,
            remise=0,
        )
        update_fields = ['facture']
        if not proc.prix and prix:
            proc.prix = prix
            update_fields.append('prix')
        proc.facture = facture
        proc.save(update_fields=update_fields)

    soin.facture = facture
    soin.save(update_fields=['facture'])
    from django.urls import reverse
    detail_url = reverse('soins:facture_detail', kwargs={'pk': facture.pk})
    back_url = f'/soins/{soin.pk}/'
    return redirect(f'{detail_url}?next={back_url}')


@login_required(login_url='login')
def soins_facture_paiement(request, pk):
    """Page de paiement de la facture d'un soin (Caisse uniquement)."""
    from facturation.models import Facture, Paiement

    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'cree_par'),
        pk=pk
    )
    # Retrouve le soin lié
    soin = Soin.objects.filter(facture=facture).select_related('patient').first()

    if request.method == 'POST':
        if not request.user.has_perm('soins.can_creer_facture'):
            messages.error(request, "Vous n'avez pas la permission d'enregistrer un paiement.")
            return redirect('soins:facture_paiement', pk=pk)

        type_paiement = request.POST.get('type_paiement', '')
        mode = request.POST.get('mode_paiement', 'especes')
        reference = request.POST.get('reference', '')

        if type_paiement == 'paye':
            Paiement.objects.create(
                facture=facture, montant=facture.montant_total,
                mode_paiement=mode, reference=reference, recu_par=request.user,
            )
            facture.montant_paye = facture.montant_total
            facture.statut = 'comptabilisee'
            facture.save(update_fields=['montant_paye', 'statut'])
            if soin:
                soin.statut = 'en_cours'
                soin.save(update_fields=['statut'])
                _sync_procedures(soin, 'en_cours')
            messages.success(request, "Paiement enregistré. Le soin peut maintenant être administré.")
            return redirect('soins:detail', pk=soin.pk) if soin else redirect('soins:list')

        elif type_paiement == 'partiel':
            try:
                montant = float(request.POST.get('montant_partiel', 0) or 0)
            except ValueError:
                montant = 0
            peut_administrer = request.POST.get('peut_administrer', '') == 'oui'

            if montant <= 0:
                messages.error(request, "Veuillez saisir un montant valide.")
            elif peut_administrer:
                Paiement.objects.create(
                    facture=facture, montant=montant,
                    mode_paiement=mode, reference=reference, recu_par=request.user,
                )
                facture.montant_paye = montant
                facture.statut = 'partielle'
                facture.save(update_fields=['montant_paye', 'statut'])
                if soin:
                    soin.statut = 'en_cours'
                    soin.save(update_fields=['statut'])
                    _sync_procedures(soin, 'en_cours')
                messages.success(request, f"Paiement partiel de {int(montant):,} FCFA enregistré.".replace(',', ' '))
                return redirect('soins:detail', pk=soin.pk) if soin else redirect('soins:list')
            else:
                # Paiement partiel refusé → annulation
                facture.statut = 'annulee'
                facture.save(update_fields=['statut'])
                if soin:
                    soin.statut = 'annule'
                    soin.save(update_fields=['statut'])
                    _sync_procedures(soin, 'annule')
                messages.warning(request, "Soin et facture annulés suite au refus du paiement partiel.")
                return redirect('soins:detail', pk=soin.pk) if soin else redirect('soins:list')

        elif type_paiement == 'non_paye':
            raison_choisie = request.POST.getlist('raison_preset')
            raison_libre = request.POST.get('raison_libre', '').strip()
            raison_finale = ', '.join(raison_choisie)
            if raison_libre:
                raison_finale = (raison_finale + ' — ' + raison_libre) if raison_finale else raison_libre
            facture.statut = 'annulee'
            facture.notes = raison_finale
            facture.save(update_fields=['statut', 'notes'])
            if soin:
                soin.statut = 'annule'
                soin.save(update_fields=['statut'])
                _sync_procedures(soin, 'annule')
            messages.warning(request, "Soin et facture annulés — non paiement.")
            return redirect('soins:detail', pk=soin.pk) if soin else redirect('soins:list')

    return render(request, 'soins/facturation/paiement.html', {
        'facture': facture,
        'lignes': facture.lignes.all(),
        'soin': soin,
        'user_peut_payer': request.user.has_perm('soins.can_creer_facture'),
        'MODES_PAIEMENT': [
            ('especes', 'Espèces'),
            ('mobile_money', 'Mobile Money'),
            ('cheque', 'Chèque'),
            ('virement', 'Virement'),
            ('assurance', 'Assurance'),
        ],
        'RAISONS_NON_PAIEMENT': [
            'Manque de moyens',
            'Contestation du montant',
            'Patient parti sans payer',
            'Renvoi vers l\'assurance',
        ],
    })


@login_required(login_url='login')
def soins_terminer(request, pk):
    """Conservé pour compatibilité admin uniquement."""
    if request.method != 'POST':
        return redirect('soins:detail', pk=pk)
    soin = get_object_or_404(Soin, pk=pk)
    if request.user.is_superuser and soin.statut == 'en_cours':
        soin.statut = 'termine'
        soin.save(update_fields=['statut'])
        _sync_procedures(soin, 'termine')
    return redirect('soins:detail', pk=pk)


# ─── RENDEZ-VOUS DANS LE MODULE SOINS ──────────────────────────────────────

@login_required(login_url='login')
def soins_rdv_create(request):
    from patients.forms import RendezVousForm
    next_url = request.GET.get('next') or request.POST.get('next') or '/soins/'
    patient_id = request.GET.get('patient_id') or request.POST.get('patient_id') or ''

    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        if form.is_valid():
            rdv = form.save()
            action = request.POST.get('_action', '')
            if action == 'confirmer':
                rdv.statut = 'confirme'
                rdv.save()
            elif action == 'annuler':
                rdv.statut = 'annule'
                rdv.save()
            messages.success(
                request,
                f'Rendez-vous créé pour {rdv.patient.nom} {rdv.patient.prenoms} '
                f'le {rdv.date_heure.strftime("%d/%m/%Y à %H:%M")}.'
            )
            redirect_url = next_url
            if '?' in redirect_url:
                redirect_url += f'&rdv_id={rdv.pk}'
            else:
                redirect_url += f'?rdv_id={rdv.pk}'
            return redirect(redirect_url)
    else:
        initial = {'date_heure': timezone.now().strftime('%Y-%m-%dT%H:%M')}
        if patient_id:
            initial['patient'] = patient_id
        form = RendezVousForm(initial=initial)

    return render(request, 'soins/rdv/form.html', {
        'form': form,
        'is_new': True,
        'next_url': next_url,
    })


@login_required(login_url='login')
def soins_rdv_detail(request, pk):
    from patients.forms import RendezVousForm
    from patients.models import RendezVous
    rdv = get_object_or_404(
        RendezVous.objects.select_related('patient', 'medecin', 'docteur_jr'),
        pk=pk
    )
    next_url = request.GET.get('next') or request.POST.get('next') or '/soins/rendez-vous/'

    if request.method == 'POST':
        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save()
            action = request.POST.get('_action', '')
            if action == 'confirmer':
                rdv.statut = 'confirme'
                rdv.save(update_fields=['statut'])
            elif action == 'annuler':
                rdv.statut = 'annule'
                rdv.save(update_fields=['statut'])
            elif action == 'terminer':
                rdv.statut = 'termine'
                rdv.save(update_fields=['statut'])
            elif action == 'absent':
                rdv.statut = 'absent'
                rdv.save(update_fields=['statut'])
            messages.success(
                request,
                f'Rendez-vous de {rdv.patient.nom} {rdv.patient.prenoms} mis à jour.'
            )
            return redirect('soins:rdv_detail', pk=rdv.pk)
    else:
        form = RendezVousForm(instance=rdv)

    return render(request, 'soins/rdv/form.html', {
        'form': form,
        'rdv': rdv,
        'is_new': False,
        'next_url': next_url,
    })


@login_required(login_url='login')
def soins_rdv_list(request):
    from patients.models import RendezVous
    patient_id = request.GET.get('patient_id', '').strip()
    back = request.GET.get('next', '/soins/')
    back_label = request.GET.get('back_label', '')

    qs = RendezVous.objects.select_related('patient', 'medecin').order_by('-date_heure')
    patient = None
    if patient_id:
        qs = qs.filter(patient_id=patient_id)
        try:
            from patients.models import Patient
            patient = Patient.objects.get(pk=patient_id)
        except Exception:
            pass

    return render(request, 'soins/rdv/list.html', {
        'rdvs': qs[:100],
        'patient': patient,
        'patient_id': patient_id,
        'back': back,
        'back_label': back_label,
    })


# ─── LISTE DES SOINS (ProcedureSoin) ───────────────────────────────────────

def _procedure_extras():
    from facturation.models import Facture as FactureModel
    services = list(Articleservice.objects.filter(
        type_article__in=['service', 'prestation']
    ).values('pk', 'nom', 'prix_vente'))
    employes = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    patients = list(Patient.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms', 'code_patient'))
    rdvs = list(RendezVous.objects.select_related('patient').values(
        'pk', 'patient_id', 'date_heure', 'type_rdv', 'statut'
    ).order_by('-date_heure')[:500])
    factures = list(FactureModel.objects.values('pk', 'numero', 'patient_id', 'montant_total').order_by('-date_emission')[:300])
    maladies = list(Maladie.objects.values('pk', 'nom', 'code_cim'))
    return {
        'services_json': json.dumps(services, default=str),
        'employes_json': json.dumps(employes),
        'patients_json': json.dumps(patients),
        'rdvs_json': json.dumps(rdvs, default=str),
        'factures_json': json.dumps(factures, default=str),
        'maladies': Maladie.objects.all(),
    }


@login_required(login_url='login')
def procedure_list(request):
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '').strip()
    date_filtre = request.GET.get('date', '').strip()
    patient_id = request.GET.get('patient_id', '').strip()

    qs = ProcedureSoin.objects.select_related(
        'patient', 'infirmier', 'departement', 'soin_type'
    ).order_by('-date')

    if patient_id:
        qs = qs.filter(patient_id=patient_id)
    elif q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(infirmier__nom__icontains=q) |
            Q(soin_type__nom__icontains=q) |
            Q(maladie__nom__icontains=q)
        )

    if statut:
        qs = qs.filter(statut=statut)
    if date_filtre:
        qs = qs.filter(date__date=date_filtre)

    today = timezone.now().date()
    stats = {
        'aujourdhui': ProcedureSoin.objects.filter(date__date=today).count(),
        'ce_mois': ProcedureSoin.objects.filter(date__month=today.month, date__year=today.year).count(),
        'en_cours': ProcedureSoin.objects.filter(statut='en_cours').count(),
        'termines': ProcedureSoin.objects.filter(statut='termine').count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    patient_filtre = None
    if patient_id:
        try:
            patient_filtre = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            pass

    return render(request, 'soins/procedure/list.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'stats': stats,
        'q': q,
        'statut': statut,
        'date_filtre': date_filtre,
        'patient_id': patient_id,
        'patient_filtre': patient_filtre,
    })


def _auto_creer_facture(proc, user):
    """Crée automatiquement une facture liée à la procédure si elle n'en a pas déjà une."""
    from facturation.models import Facture, LigneFacture
    if proc.facture_id:
        return
    soin_label = proc.soin_type.nom if proc.soin_type else "Soin infirmier"
    libelle = f"{soin_label} – {proc.numero}"
    facture = Facture.objects.create(
        patient=proc.patient,
        cree_par=user,
        type_facture='autre',
        statut='brouillon',
        montant_total=proc.prix or 0,
    )
    LigneFacture.objects.create(
        facture=facture,
        libelle=libelle,
        quantite=1,
        prix_unitaire=proc.prix or 0,
        remise=0,
    )
    ProcedureSoin.objects.filter(pk=proc.pk).update(facture=facture)
    proc.facture = facture


@login_required(login_url='login')
def procedure_create(request):
    if request.method == 'POST':
        form = ProcedureSoinForm(request.POST)
        if form.is_valid():
            proc = form.save(commit=False)
            champs_ok = all([
                proc.patient_id,
                proc.infirmier_id,
                proc.soin_type_id,
                proc.departement_id,
            ])
            if champs_ok:
                proc.statut = 'en_cours'
                proc.save()
                _auto_creer_facture(proc, request.user)
            else:
                proc.statut = 'brouillon'
                proc.save()
            return redirect('soins:procedure_detail', pk=proc.pk)
    else:
        form = ProcedureSoinForm()

    return render(request, 'soins/procedure/form.html', {
        'form': form,
        'is_new': True,
        **_procedure_extras(),
    })


@login_required(login_url='login')
def procedure_detail(request, pk):
    proc = get_object_or_404(
        ProcedureSoin.objects.select_related(
            'patient', 'infirmier', 'departement', 'soin_type', 'maladie', 'rendez_vous', 'facture'
        ),
        pk=pk
    )
    facture_payee = (
        proc.facture is not None and
        proc.facture.statut in ('payee', 'partielle')
    )
    return render(request, 'soins/procedure/detail.html', {
        'proc': proc,
        'facture_payee': facture_payee,
    })


@login_required(login_url='login')
def procedure_edit(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    if request.method == 'POST':
        form = ProcedureSoinForm(request.POST, instance=proc)
        if form.is_valid():
            proc = form.save(commit=False)
            action = request.POST.get('action', 'save')
            if action == 'annuler':
                proc.statut = 'annule'
                proc.save()
            elif action in ('en_cours', 'termine'):
                proc.statut = action
                proc.save()
            else:
                # action == 'save' : auto-passage en_cours si champs obligatoires remplis
                champs_ok = all([
                    proc.patient_id,
                    proc.infirmier_id,
                    proc.soin_type_id,
                    proc.departement_id,
                ])
                if champs_ok and proc.statut == 'brouillon':
                    proc.statut = 'en_cours'
                    proc.save()
                    _auto_creer_facture(proc, request.user)
                else:
                    proc.save()
            return redirect('soins:procedure_detail', pk=proc.pk)
    else:
        form = ProcedureSoinForm(instance=proc)

    return render(request, 'soins/procedure/form.html', {
        'form': form,
        'proc': proc,
        'is_new': False,
        **_procedure_extras(),
    })


@login_required(login_url='login')
def procedure_terminer(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    if request.method == 'POST' and proc.statut == 'en_cours':
        proc.statut = 'termine'
        proc.save()
    return redirect('soins:procedure_detail', pk=pk)


@login_required(login_url='login')
def procedure_annuler(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    if request.method == 'POST' and proc.statut not in ('termine', 'annule'):
        proc.statut = 'annule'
        proc.save()
    return redirect('soins:procedure_detail', pk=pk)


@login_required(login_url='login')
def maladie_create(request):
    from .forms import MaladieForm
    next_url = request.GET.get('next') or request.POST.get('next') or '/soins/procedures/nouveau/'
    if request.method == 'POST':
        form = MaladieForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(next_url)
    else:
        nom_initial = request.GET.get('nom', '')
        form = MaladieForm(initial={'nom': nom_initial})
    return render(request, 'soins/maladie/form.html', {
        'form': form,
        'next_url': next_url,
        'title': 'Nouvelle maladie',
    })


@login_required(login_url='login')
def maladie_list(request):
    q = request.GET.get('q', '').strip()
    maladies = Maladie.objects.all()
    if q:
        maladies = maladies.filter(
            Q(nom__icontains=q) | Q(code_cim__icontains=q)
        )
    return render(request, 'soins/maladie/list.html', {
        'maladies': maladies,
        'q': q,
    })


@login_required(login_url='login')
def maladie_edit(request, pk):
    from .forms import MaladieForm
    maladie = get_object_or_404(Maladie, pk=pk)
    next_url = request.GET.get('next') or request.POST.get('next') or '/soins/maladies/'
    if request.method == 'POST':
        form = MaladieForm(request.POST, instance=maladie)
        if form.is_valid():
            form.save()
            return redirect(next_url)
    else:
        form = MaladieForm(instance=maladie)
    return render(request, 'soins/maladie/form.html', {
        'form': form,
        'next_url': next_url,
        'title': 'Modifier la maladie',
        'maladie': maladie,
    })


@login_required(login_url='login')
def maladie_delete(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    next_url = request.GET.get('next') or '/soins/maladies/'
    if request.method == 'POST':
        maladie.delete()
        return redirect(next_url)
    return render(request, 'soins/maladie/confirm_delete.html', {
        'maladie': maladie,
        'next_url': next_url,
    })


@_staff_required
def soin_facturer(request, pk):
    from facturation.models import Facture, LigneFacture
    from django.urls import reverse

    soin = get_object_or_404(
        Soin.objects.select_related('patient', 'service_inscription'), pk=pk
    )
    procedures = list(soin.procedures.select_related('soin_type').all())

    if procedures:
        total = sum(p.prix for p in procedures)
        facture = Facture.objects.create(
            patient=soin.patient,
            cree_par=request.user,
            type_facture='autre',
            statut='brouillon',
            montant_total=total,
        )
        for proc in procedures:
            libelle = proc.soin_type.nom if proc.soin_type else f"Soin - {proc.numero}"
            LigneFacture.objects.create(
                facture=facture,
                libelle=libelle,
                quantite=1,
                prix_unitaire=proc.prix,
                remise=0,
            )
            proc.facture = facture
            proc.save(update_fields=['facture'])
    else:
        libelle = f"Soins infirmiers - {soin.numero}"
        prix_unitaire = 0
        if soin.service_inscription:
            libelle = f"{soin.service_inscription.nom} - {soin.numero}"
            prix_unitaire = soin.service_inscription.prix_vente or 0
        facture = Facture.objects.create(
            patient=soin.patient,
            cree_par=request.user,
            type_facture='autre',
            statut='brouillon',
            montant_total=prix_unitaire,
        )
        LigneFacture.objects.create(
            facture=facture,
            libelle=libelle,
            quantite=1,
            prix_unitaire=prix_unitaire,
            remise=0,
        )

    detail_url = reverse('soins:facture_detail', kwargs={'pk': facture.pk})
    return redirect(f'{detail_url}?next=/soins/{pk}/')


@_staff_required
def procedure_facturer(request, pk):
    from facturation.models import Facture, LigneFacture
    from django.urls import reverse

    proc = get_object_or_404(
        ProcedureSoin.objects.select_related('patient', 'soin_type'), pk=pk
    )

    soin_label = proc.soin_type.nom if proc.soin_type else "Soin"
    libelle = f"{soin_label} - {proc.numero}"

    facture = Facture.objects.create(
        patient=proc.patient,
        cree_par=request.user,
        type_facture='autre',
        statut='brouillon',
        montant_total=proc.prix,
    )

    LigneFacture.objects.create(
        facture=facture,
        libelle=libelle,
        quantite=1,
        prix_unitaire=proc.prix,
        remise=0,
    )

    proc.facture = facture
    proc.save()

    detail_url = reverse('soins:facture_detail', kwargs={'pk': facture.pk})
    return redirect(f'{detail_url}?next=/soins/procedures/{pk}/')


# ─── FACTURE DANS LE MODULE SOINS ──────────────────────────────────────────

@login_required(login_url='login')
def soins_facture_detail(request, pk):
    from facturation.models import Facture
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'cree_par'),
        pk=pk
    )
    # Auto-correction : si le montant_total est 0 mais les procédures liées ont des prix,
    # recalculer silencieusement les lignes et le total depuis soin_type.prix_vente.
    if facture.montant_total == 0 and facture.statut in ('brouillon', 'emise'):
        lignes = list(facture.lignes.select_related('acte').all())
        procedures = list(facture.procedures_soins.select_related('soin_type').all())
        proc_by_libelle = {
            (p.soin_type.nom if p.soin_type else None): p for p in procedures
        }
        recalcule = False
        for ligne in lignes:
            if ligne.prix_unitaire == 0:
                proc = proc_by_libelle.get(ligne.libelle)
                prix = 0
                if proc:
                    prix = proc.prix or (proc.soin_type.prix_vente if proc.soin_type else 0)
                if prix:
                    ligne.prix_unitaire = prix
                    ligne.save(update_fields=['prix_unitaire'])
                    recalcule = True
        if recalcule:
            nouveau_total = sum(
                l.prix_unitaire for l in facture.lignes.all()
            )
            facture.montant_total = nouveau_total
            facture.save(update_fields=['montant_total'])
    back_url = request.GET.get('next', '/soins/')
    return render(request, 'soins/facturation/detail.html', {
        'facture': facture,
        'lignes': facture.lignes.all(),
        'paiements': facture.paiements.all(),
        'back_url': back_url,
        'is_admin': request.user.is_superuser,
    })


@login_required(login_url='login')
def soins_facture_edit(request, pk):
    from facturation.models import Facture, LigneFacture, Acte
    from facturation.forms import FactureForm
    from caisse.models import Caisse

    facture = get_object_or_404(Facture.objects.select_related('patient'), pk=pk)

    def _parse(val, default=0):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if request.method == 'POST':
        form = FactureForm(request.POST, instance=facture)
        back_url = request.POST.get('next', '/soins/')
        if form.is_valid():
            f = form.save(commit=False)
            LigneFacture.objects.filter(facture_id=facture.pk).delete()

            total = 0
            i = 0
            while f'ligne_libelle_{i}' in request.POST:
                libelle = request.POST.get(f'ligne_libelle_{i}', '').strip()
                acte_id = request.POST.get(f'ligne_acte_{i}') or None
                qte = _parse(request.POST.get(f'ligne_qte_{i}'), 1)
                prix = _parse(request.POST.get(f'ligne_prix_{i}'), 0)
                remise = _parse(request.POST.get(f'ligne_remise_{i}'), 0)
                if libelle or acte_id:
                    total += qte * prix * (1 - remise / 100)
                    LigneFacture.objects.create(
                        facture_id=facture.pk,
                        acte_id=acte_id,
                        libelle=libelle or (
                            Acte.objects.get(pk=acte_id).libelle if acte_id else '—'
                        ),
                        quantite=qte,
                        prix_unitaire=prix,
                        remise=remise,
                    )
                i += 1

            f.montant_total = round(total, 2)
            f.save()
            messages.success(request, f"Facture {f.numero} mise à jour.")
            from django.urls import reverse
            detail_url = reverse('soins:facture_detail', kwargs={'pk': facture.pk})
            return redirect(f'{detail_url}?next={back_url}')
    else:
        form = FactureForm(instance=facture)
        back_url = request.GET.get('next', '/soins/')

    return render(request, 'soins/facturation/edit.html', {
        'facture': facture,
        'form': form,
        'lignes': facture.lignes.all(),
        'actes': Acte.objects.filter(actif=True).order_by('categorie', 'libelle'),
        'caisses': Caisse.objects.filter(actif=True),
        'back_url': back_url,
    })


@login_required(login_url='login')
def soins_facture_valider(request, pk):
    from facturation.models import Facture
    from django.urls import reverse
    facture = get_object_or_404(Facture, pk=pk)
    if request.method == 'POST':
        back_url = request.POST.get('next', '/soins/')
        if facture.statut == 'brouillon':
            facture.statut = 'emise'
            facture.save()
            messages.success(request, f"Facture {facture.numero} validée et émise avec succès.")
        detail_url = reverse('soins:facture_detail', kwargs={'pk': pk})
        return redirect(f'{detail_url}?next={back_url}')
    return redirect('soins:facture_detail', pk=pk)


@login_required(login_url='login')
def soins_facture_payer(request, pk):
    from facturation.models import Facture, Paiement
    from django.urls import reverse

    facture = get_object_or_404(Facture, pk=pk)
    if request.method != 'POST':
        return redirect('soins:facture_detail', pk=pk)

    back_url = request.POST.get('next', '/soins/')

    try:
        montant = float(request.POST.get('pay_montant', 0))
    except (TypeError, ValueError):
        montant = 0

    journal = request.POST.get('pay_journal', 'caisse_accueil')
    compte_bancaire = request.POST.get('pay_compte_bancaire', '')
    memo = request.POST.get('pay_memo', '')

    journal_to_mode = {
        'caisse_accueil': 'especes',
        'caisse_soins':   'especes',
        'banque':         'virement',
        'mobile_money':   'mobile_money',
        'assurance':      'assurance',
    }
    mode = journal_to_mode.get(journal, 'especes')

    from django.utils.dateparse import parse_date
    date_str = request.POST.get('pay_date', '')
    from django.utils import timezone as tz
    if date_str:
        d = parse_date(date_str)
        date_paiement = tz.make_aware(
            __import__('datetime').datetime.combine(d, __import__('datetime').time.min)
        ) if d else tz.now()
    else:
        date_paiement = tz.now()

    if montant > 0 and facture.statut in ('brouillon', 'emise', 'partielle'):
        Paiement.objects.create(
            facture=facture,
            montant=montant,
            mode_paiement=mode,
            journal=journal,
            compte_bancaire=compte_bancaire,
            reference=memo,
            date_paiement=date_paiement,
            recu_par=request.user,
        )
        total_paye = sum(p.montant for p in facture.paiements.all())
        facture.montant_paye = total_paye
        if total_paye >= facture.montant_total:
            facture.statut = 'comptabilisee'
            facture.save(update_fields=['montant_paye', 'statut'])
            for soin in facture.soins.all():
                if soin.statut in ('en_attente_de_paiement', 'brouillon'):
                    soin.statut = 'en_cours'
                    soin.save(update_fields=['statut'])
            messages.success(request, f"Paiement complet — facture {facture.numero} comptabilisée.")
            detail_url = reverse('soins:facture_detail', kwargs={'pk': pk})
            return redirect(f'{detail_url}?next={back_url}')
        else:
            facture.statut = 'partielle'
            facture.save(update_fields=['montant_paye', 'statut'])
            messages.success(request, f"Paiement partiel de {int(montant):,} CFA enregistré.".replace(',', ' '))
            detail_url = reverse('soins:facture_detail', kwargs={'pk': pk})
            return redirect(f'{detail_url}?next={back_url}&partial_confirm=1')

    detail_url = reverse('soins:facture_detail', kwargs={'pk': pk})
    return redirect(f'{detail_url}?next={back_url}')


@login_required(login_url='login')
def soins_autoriser_soin_partiel(request, pk):
    from facturation.models import Facture
    facture = get_object_or_404(Facture, pk=pk)
    if request.method == 'POST':
        autoriser = request.POST.get('autoriser') == '1'
        back_url = request.POST.get('next', '/soins/')
        if autoriser:
            for soin in facture.soins.all():
                if soin.statut == 'en_attente_de_paiement':
                    soin.statut = 'en_cours'
                    soin.save(update_fields=['statut'])
            messages.success(request, "Le soin a été autorisé malgré le paiement partiel.")
        detail_url = reverse('soins:facture_detail', kwargs={'pk': pk})
        return redirect(f'{detail_url}?next={back_url}')
    return redirect('soins:facture_detail', pk=pk)


@login_required(login_url='login')
def soins_facture_print(request, pk):
    from facturation.models import Facture
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'cree_par'),
        pk=pk
    )
    back_url = request.GET.get('next', '/soins/')
    return render(request, 'soins/facturation/print.html', {
        'facture': facture,
        'lignes': facture.lignes.select_related('acte').all(),
        'paiements': facture.paiements.all(),
        'back_url': back_url,
    })


@login_required(login_url='login')
def soins_facture_apercu(request, pk):
    from facturation.models import Facture
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'cree_par'),
        pk=pk
    )
    back_url = request.GET.get('next', '/soins/')
    return render(request, 'soins/facturation/apercu.html', {
        'facture': facture,
        'lignes': facture.lignes.select_related('acte').all(),
        'paiements': facture.paiements.all(),
        'back_url': back_url,
    })


# ─── DEMANDES D'EXAMEN ──────────────────────────────────────────────────────

@login_required(login_url='login')
def demande_examen_list(request):
    from .models import DemandeExamen
    patient_id = request.GET.get('patient_id', '').strip()
    q          = request.GET.get('q', '').strip()
    back       = request.GET.get('next', '/soins/')

    qs = DemandeExamen.objects.select_related('patient', 'medecin_prescripteur').order_by('-date_creation')

    if patient_id:
        qs = qs.filter(patient_id=patient_id)
    elif q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q)
        )

    patient = None
    if patient_id:
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            pass

    return render(request, 'soins/demande_examen/list.html', {
        'demandes': qs[:200],
        'patient': patient,
        'patient_id': patient_id,
        'q': q,
        'back': back,
    })


@login_required(login_url='login')
def demande_examen_create(request):
    from .models import DemandeExamen, LigneDemandeExamen
    from laboratoire.models import TypeExamen

    soin_id = request.GET.get('soin_id', '') or request.POST.get('soin_id', '')
    initial_soin = None
    if soin_id:
        try:
            initial_soin = Soin.objects.select_related('patient').get(pk=soin_id)
        except Soin.DoesNotExist:
            pass

    if request.method == 'POST':
        patient_id  = request.POST.get('patient') or ''
        medecin_id  = request.POST.get('medecin_prescripteur') or None
        soin_fk_id  = request.POST.get('soin_id') or None

        if not patient_id:
            pass
        else:
            try:
                pat = Patient.objects.get(pk=patient_id)
            except Patient.DoesNotExist:
                pat = None

            if pat:
                demande = DemandeExamen.objects.create(
                    patient=pat,
                    soin_id=soin_fk_id if soin_fk_id else None,
                    medecin_prescripteur_id=medecin_id if medecin_id else None,
                    lab_groupe=request.POST.get('lab_groupe', ''),
                    est_demande_groupe=bool(request.POST.get('est_demande_groupe')),
                    type_test=request.POST.get('type_test', ''),
                    centre_collecte=request.POST.get('centre_collecte', ''),
                    envoyer_autre_lab=bool(request.POST.get('envoyer_autre_lab')),
                    sampler=request.POST.get('sampler', ''),
                    date_actes=request.POST.get('date_actes') or None,
                    echantillon_du_test=bool(request.POST.get('echantillon_du_test')),
                    statut=request.POST.get('statut', 'brouillon'),
                    raison_refus=request.POST.get('raison_refus', ''),
                    # HL7
                    type_segment=request.POST.get('type_segment', 'H'),
                    nom_fichier=request.POST.get('nom_fichier', 'WAL001.HPR'),
                    code_emetteur=request.POST.get('code_emetteur', '001'),
                    nom_emetteur=request.POST.get('nom_emetteur', ''),
                    code_recepteur=request.POST.get('code_recepteur', '002'),
                    nom_recepteur=request.POST.get('nom_recepteur', 'CMSWALE.0000'),
                    identifiant_recepteur=request.POST.get('identifiant_recepteur', 'WALE.SYSLAM'),
                    type_message=request.POST.get('type_message', 'DRA'),
                    mode_traitement=request.POST.get('mode_traitement', 'P'),
                    version_type=request.POST.get('version_type', 'H2.4'),
                    type_liaison=request.POST.get('type_liaison', 'L'),
                    liste_prix=request.POST.get('liste_prix', ''),
                    type_segment_patient=request.POST.get('type_segment_patient', 'P'),
                    rang_segment_patient=request.POST.get('rang_segment_patient', 'D'),
                    type_code=request.POST.get('type_code', 'L'),
                    priorite=request.POST.get('priorite', 'C'),
                    code_action=request.POST.get('code_action', 'N'),
                    date_heure_resultats=request.POST.get('date_heure_resultats') or None,
                    statuts_resultats=request.POST.get('statuts_resultats', 'F'),
                    couts_transport=request.POST.get('couts_transport', 'WALK'),
                    type_segment_qbr=request.POST.get('type_segment_qbr', 'QBR'),
                    type_segment_l=request.POST.get('type_segment_l', 'L'),
                )
                # Lignes
                types_ids   = request.POST.getlist('ligne_type[]')
                delais      = request.POST.getlist('ligne_delai[]')
                prix_list   = request.POST.getlist('ligne_prix[]')
                instructions = request.POST.getlist('ligne_instructions[]')
                for i, tid in enumerate(types_ids):
                    if not tid:
                        continue
                    LigneDemandeExamen.objects.create(
                        demande=demande,
                        type_examen_id=tid,
                        delai_execution=delais[i] if i < len(delais) else '',
                        prix_vente=prix_list[i] if i < len(prix_list) and prix_list[i] else 0,
                        instructions_speciales=instructions[i] if i < len(instructions) else '',
                    )
                return redirect('soins:demande_examen_detail', pk=demande.pk)

    types_examens = list(TypeExamen.objects.values('pk', 'nom', 'prix', 'delai_resultat_heures'))
    employes      = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    patients_qs   = list(Patient.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms', 'code_patient'))

    return render(request, 'soins/demande_examen/form.html', {
        'is_new': True,
        'initial_soin': initial_soin,
        'initial_patient': initial_soin.patient if initial_soin else None,
        'soin_id': soin_id,
        'types_examens_json': json.dumps(types_examens, default=str),
        'employes_json': json.dumps(employes),
        'patients_json': json.dumps(patients_qs),
    })


@login_required(login_url='login')
def demande_examen_detail(request, pk):
    from .models import DemandeExamen
    demande = get_object_or_404(
        DemandeExamen.objects.select_related('patient', 'medecin_prescripteur', 'soin', 'rendez_vous'),
        pk=pk
    )
    lignes = demande.lignes.select_related('type_examen').all()
    return render(request, 'soins/demande_examen/detail.html', {
        'demande': demande,
        'analyse': demande,  # alias for template compatibility
        'lignes': lignes,
    })


@login_required(login_url='login')
def demande_examen_envoyer(request, pk):
    from .models import DemandeExamen
    demande = get_object_or_404(DemandeExamen, pk=pk)
    if request.method == 'POST' and demande.statut == 'brouillon':
        demande.statut = 'demande'
        demande.save(update_fields=['statut'])
    return redirect('soins:demande_examen_detail', pk=pk)


@login_required(login_url='login')
def demande_examen_terminer(request, pk):
    from .models import DemandeExamen
    demande = get_object_or_404(DemandeExamen, pk=pk)
    if request.method == 'POST':
        transitions = {
            'brouillon': 'demande',
            'demande':   'accepte',
            'accepte':   'en_cours',
            'en_cours':  'termine',
        }
        next_statut = transitions.get(demande.statut)
        if next_statut:
            demande.statut = next_statut
            demande.save(update_fields=['statut'])
    return redirect('soins:demande_examen_detail', pk=pk)


@login_required(login_url='login')
def demande_examen_annuler(request, pk):
    from .models import DemandeExamen
    demande = get_object_or_404(DemandeExamen, pk=pk)
    if request.method == 'POST' and demande.statut != 'termine':
        demande.statut = 'brouillon'
        demande.save(update_fields=['statut'])
    return redirect('soins:demande_examen_detail', pk=pk)


@login_required(login_url='login')
def demande_examen_edit(request, pk):
    from .models import DemandeExamen, LigneDemandeExamen
    from laboratoire.models import TypeExamen

    demande = get_object_or_404(DemandeExamen, pk=pk)
    if demande.statut != 'brouillon':
        return redirect('soins:demande_examen_detail', pk=pk)

    if request.method == 'POST':
        patient_id = request.POST.get('patient') or ''
        medecin_id = request.POST.get('medecin_prescripteur') or None

        if patient_id:
            try:
                pat = Patient.objects.get(pk=patient_id)
                demande.patient = pat
            except Patient.DoesNotExist:
                pass

        demande.medecin_prescripteur_id = medecin_id if medecin_id else None
        demande.lab_groupe = request.POST.get('lab_groupe', '')
        demande.est_demande_groupe = bool(request.POST.get('est_demande_groupe'))
        demande.type_test = request.POST.get('type_test', '')
        demande.centre_collecte = request.POST.get('centre_collecte', '')
        demande.envoyer_autre_lab = bool(request.POST.get('envoyer_autre_lab'))
        demande.sampler = request.POST.get('sampler', '')
        demande.date_actes = request.POST.get('date_actes') or None
        demande.echantillon_du_test = bool(request.POST.get('echantillon_du_test'))
        demande.raison_refus = request.POST.get('raison_refus', '')
        demande.type_segment = request.POST.get('type_segment', 'H')
        demande.nom_fichier = request.POST.get('nom_fichier', 'WAL001.HPR')
        demande.code_emetteur = request.POST.get('code_emetteur', '001')
        demande.nom_emetteur = request.POST.get('nom_emetteur', '')
        demande.code_recepteur = request.POST.get('code_recepteur', '002')
        demande.nom_recepteur = request.POST.get('nom_recepteur', 'CMSWALE.0000')
        demande.identifiant_recepteur = request.POST.get('identifiant_recepteur', 'WALE.SYSLAM')
        demande.type_message = request.POST.get('type_message', 'DRA')
        demande.mode_traitement = request.POST.get('mode_traitement', 'P')
        demande.version_type = request.POST.get('version_type', 'H2.4')
        demande.type_liaison = request.POST.get('type_liaison', 'L')
        demande.liste_prix = request.POST.get('liste_prix', '')
        demande.save()

        # Rebuild lignes
        demande.lignes.all().delete()
        types_ids    = request.POST.getlist('ligne_type[]')
        delais       = request.POST.getlist('ligne_delai[]')
        prix_list    = request.POST.getlist('ligne_prix[]')
        instructions = request.POST.getlist('ligne_instructions[]')
        for i, tid in enumerate(types_ids):
            if not tid:
                continue
            LigneDemandeExamen.objects.create(
                demande=demande,
                type_examen_id=tid,
                delai_execution=delais[i] if i < len(delais) else '',
                prix_vente=prix_list[i] if i < len(prix_list) and prix_list[i] else 0,
                instructions_speciales=instructions[i] if i < len(instructions) else '',
            )
        return redirect('soins:demande_examen_detail', pk=demande.pk)

    types_examens = list(TypeExamen.objects.values('pk', 'nom', 'prix', 'delai_resultat_heures'))
    employes      = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    patients_qs   = list(Patient.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms', 'code_patient'))

    existing_lignes = []
    for ligne in demande.lignes.select_related('type_examen').all():
        existing_lignes.append({
            'type_examen': ligne.type_examen_id,
            'delai_execution': ligne.delai_execution,
            'prix_vente': str(ligne.prix_vente),
            'instructions_speciales': ligne.instructions_speciales,
        })

    return render(request, 'soins/demande_examen/form.html', {
        'instance': demande,
        'is_new': False,
        'initial_soin': demande.soin,
        'initial_patient': demande.patient,
        'soin_id': demande.soin_id or '',
        'date_str': demande.date.strftime('%Y-%m-%dT%H:%M') if demande.date else '',
        'date_actes_str': demande.date_actes.strftime('%Y-%m-%dT%H:%M') if demande.date_actes else '',
        'types_examens_json': json.dumps(types_examens, default=str),
        'employes_json': json.dumps(employes),
        'patients_json': json.dumps(patients_qs),
        'existing_lignes_json': json.dumps(existing_lignes),
    })
