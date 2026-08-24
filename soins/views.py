import json
import re
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test

_staff_required = user_passes_test(lambda u: u.is_staff, login_url='login')
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef, Prefetch
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Soin, ProcedureSoin
from .forms import SoinForm, ProcedureSoinForm
from patients.models import RendezVous, Patient
from patients.models import Pathologie
from laboratoire.models import AnalyseLaboratoire, ExamenImagerie
from employer.models import Employe
from services.models import Articleservice
from core.views import log_event, get_logs
from patients.selecteur import patient_affiche


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


def _save_procedures_from_lignes(soin, post_data, user=None):
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
            for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    date = timezone.make_aware(datetime.strptime(date_str, fmt))
                    break
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
            cree_par=user,
        )


def _patient_counts(patient):
    return {
        'rdv': RendezVous.objects.filter(patient=patient).count(),
        'analyses': AnalyseLaboratoire.objects.filter(patient=patient).count(),
        'imageries': ExamenImagerie.objects.filter(patient=patient).count(),
    }


def _form_extras():
    services = list(Articleservice.objects.filter(
        categorie__code='SN'
    ).values('pk', 'nom', 'prix_vente'))
    employes = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    # Plus de liste de patients sérialisée : le sélecteur du formulaire
    # (includes/_patient_picker.html) interroge /patients/recherche/ à la
    # frappe. Sur ce centre cela retirait 383 dossiers du HTML de chaque page.
    return {
        'services_json': json.dumps(services, default=str),
        'employes_json': json.dumps(employes),
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
    """Liste des soins infirmiers.

    Filtres cumulables et regroupements imbriqués viennent de core.listing,
    comme les listes de rendez-vous, du registre des naissances et de la
    gynécologie : cette vue ne fait que déclarer le jeu de départ et assembler
    le contexte. Auparavant chaque critère écrasait le précédent — un seul
    statut, une seule période — et la recherche restait prisonnière du repli sur
    la journée en cours.
    """
    from django.core.paginator import Paginator

    from core.listing import Listing, menu_filtres, menu_groupes, paginer_groupes
    from .soin_listing import (CHAMPS_RECHERCHE, FILTRES_DEFAUT, TRIS,
                               construire_dimensions, familles_soins, libelle_periode)

    today = timezone.now().date()
    q = request.GET.get('q', '').strip()
    groupes = request.GET.getlist('group')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    patient_id = request.GET.get('patient_id', '').strip()
    hospitalisation_id = request.GET.get('hospitalisation_id', '').strip()

    base_qs = Soin.objects.select_related(
        'patient', 'hospitalisation', 'infirmier', 'departement'
    ).prefetch_related(
        Prefetch(
            'procedures',
            queryset=ProcedureSoin.objects.select_related('infirmier').order_by('date'),
            to_attr='procedures_list'
        )
    ).annotate(
        est_paye=Exists(
            ProcedureSoin.objects.filter(
                soin=OuterRef('pk'),
                facture__statut__in=['payee']
            )
        )
    )

    # Deux entrées ciblées, conservées telles quelles : on arrive ici depuis une
    # fiche patient ou une hospitalisation, la période par défaut n'a alors plus
    # de sens et le filtre est imposé en amont de la brique.
    cible = bool(hospitalisation_id or patient_id)
    if hospitalisation_id:
        base_qs = base_qs.filter(hospitalisation_id=hospitalisation_id)
    elif patient_id:
        base_qs = base_qs.filter(patient_id=patient_id)

    declarees = construire_dimensions()
    listing = Listing(
        recherche=CHAMPS_RECHERCHE,
        familles=familles_soins(),
        dimensions=list(declarees.values()),
        par_page=25,
        filtres_defaut=() if cible else FILTRES_DEFAUT,
        tri_defaut=('-date_creation',),
        tris=TRIS,
    )

    filtres = listing.filtres_demandes(request)
    qs = listing.appliquer_recherche(base_qs, q)
    qs = listing.appliquer_filtres(qs, filtres, {
        'aujourdhui': today, 'date_from': date_from, 'date_to': date_to,
    })
    tri, tri_sens = listing.tri_demande(request)
    qs = listing.trier(qs, groupes, tri, tri_sens)

    # Avec un regroupement on pagine les **groupes** : toutes les lignes des
    # groupes affichés sont chargées, si bien que déplier n'appelle jamais le
    # serveur.
    dims = [declarees[g] for g in groupes if g in declarees]
    arbre = []
    if dims:
        arbre, page_obj, nb_groupes = paginer_groupes(qs, dims, request.GET.get('page'))
        # Avec un regroupement, la pagination porte sur les groupes : le compteur
        # du titre doit rester celui des soins, pas celui des bandes.
        total = qs.count()
    else:
        nb_groupes = 0
        page_obj = Paginator(qs, listing.par_page).get_page(request.GET.get('page'))
        total = page_obj.paginator.count

    stats = {
        'aujourdhui': Soin.objects.filter(date_creation__date=today).count(),
        'ce_mois': Soin.objects.filter(date_creation__month=today.month, date_creation__year=today.year).count(),
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

    hospitalisation_filtre = None
    if hospitalisation_id:
        from hospitalisation.models import Hospitalisation
        try:
            hospitalisation_filtre = Hospitalisation.objects.select_related('patient').get(pk=hospitalisation_id)
        except Hospitalisation.DoesNotExist:
            pass

    return render(request, 'soins/list.html', {
        'page_obj': page_obj,
        'arbre': arbre,
        'nb_groupes': nb_groupes,
        'total': total,
        'stats': stats,
        'q': q,
        'tri': tri,
        'tri_sens': tri_sens,
        'filters': filtres,
        'groups': groupes,
        'date_from': date_from,
        'date_to': date_to,
        'filtre_pose': bool(filtres),
        'selection_active': bool(q or groupes or not listing.est_selection_par_defaut(filtres)),
        'periode_libelle': libelle_periode(filtres, date_from, date_to),
        # Menus générés depuis la déclaration : le gabarit ne fait que parcourir.
        'listing_filtres': menu_filtres(listing.familles, filtres, date_from, date_to),
        'listing_groupes': menu_groupes(list(declarees.values()), groupes),
        'today': today,
        'patient_id': patient_id,
        'patient_filtre': patient_filtre,
        'hospitalisation_id': hospitalisation_id,
        'hospitalisation_filtre': hospitalisation_filtre,
        'user_peut_creer_facture': request.user.has_perm('soins.can_creer_facture'),
    })


@login_required(login_url='login')
def soins_detail(request, pk):
    soin = get_object_or_404(
        Soin.objects.select_related(
            'patient', 'departement', 'facture',
            'cree_par', 'modifie_par', 'termine_par',
        ),
        pk=pk
    )
    counts = _patient_counts(soin.patient)
    counts['examens'] = counts['analyses'] + counts['imageries']
    counts['soins'] = ProcedureSoin.objects.filter(patient=soin.patient).count()
    procedures = list(soin.procedures.select_related('soin_type', 'infirmier', 'facture').all())
    total_prix = sum(p.prix for p in procedures)
    if soin.hospitalisation_id:
        from hospitalisation.models import ServiceAFacturer
        facture_payee = ServiceAFacturer.objects.filter(
            hospitalisation_id=soin.hospitalisation_id,
            source__in=['soin', 'manuel'],
            facture__statut='payee'
        ).exists()
    else:
        facture_payee = (
            soin.facture is not None and
            soin.facture.statut == 'payee'
        )
    peut_administrer = (
        soin.statut == 'en_cours' and
        facture_payee and
        request.user.has_perm('soins.can_administrer_soin')
    )
    peut_creer_facture = (
        soin.statut == 'en_attente_de_paiement' and
        not soin.facture_id and
        request.user.has_perm('soins.can_creer_facture')
    )
    peut_voir_facture = (
        soin.facture_id is not None and (
            soin.statut != 'en_attente_de_paiement' or
            request.user.has_perm('soins.can_creer_facture')
        )
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
        'logs': get_logs(soin),
    })


@login_required(login_url='login')
def soins_create(request):
    if request.method == 'POST':
        form = SoinForm(request.POST, request.FILES)
        if form.is_valid():
            soin = form.save(commit=False)
            soin.cree_par = request.user
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
            log_event(soin, request.user, 'Soin créé.', type='system')
            _save_procedures_from_lignes(soin, request.POST, user=request.user)
            return redirect('soins:detail', pk=soin.pk)
    else:
        form = SoinForm()

    extras = _form_extras()
    patient_id = request.GET.get('patient_id', '')
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

    # Dossier auto-géré par une hospitalisation
    hosp_warning = None
    if soin.hospitalisation_id:
        hosp = soin.hospitalisation
        if not request.user.is_superuser:
            messages.warning(
                request,
                f"Ce dossier de soins est géré automatiquement depuis l'hospitalisation "
                f"N°{hosp.numero}. Modification manuelle désactivée."
            )
            return redirect('soins:detail', pk=pk)
        # Superuser : accès autorisé mais avec bandeau d'avertissement dans le formulaire
        hosp_warning = hosp

    # Verrouillage : seul l'admin peut modifier un soin hors brouillon
    if soin.statut != 'brouillon' and not request.user.is_superuser:
        messages.warning(request, "Ce soin ne peut plus être modifié.")
        return redirect('soins:detail', pk=pk)

    if request.method == 'POST':
        form = SoinForm(request.POST, request.FILES, instance=soin)
        if form.is_valid():
            soin = form.save(commit=False)
            soin.modifie_par = request.user
            soin.date_modification = timezone.now()
            action = request.POST.get('action', 'save')
            if action == 'enregistrer':
                if not _has_at_least_one_ligne(request.POST):
                    messages.error(request, "Ajoutez au moins une ligne de soin avant d'enregistrer.")
                else:
                    soin.statut = 'en_attente_de_paiement'
                    soin.save()
                    log_event(soin, request.user, 'Soin modifié.', type='modif')
                    _save_procedures_from_lignes(soin, request.POST, user=request.user)
                    return redirect('soins:detail', pk=soin.pk)
            else:
                soin.statut = 'brouillon'
            soin.save()
            log_event(soin, request.user, 'Soin modifié.', type='modif')
            _save_procedures_from_lignes(soin, request.POST, user=request.user)
            return redirect('soins:detail', pk=soin.pk)
    else:
        form = SoinForm(instance=soin)

    counts = _patient_counts(soin.patient)
    counts['examens'] = counts['analyses'] + counts['imageries']
    extras = _form_extras()

    procedures_qs = list(soin.procedures.select_related('patient', 'infirmier', 'soin_type').all())

    # Inject any services from existing procedures that fall outside the 'SN' category
    # filter used in _form_extras() — otherwise the select shows blank for those lines.
    existing_pks = {p.soin_type_id for p in procedures_qs if p.soin_type_id}
    loaded_services = json.loads(extras['services_json'])
    loaded_pks = {s['pk'] for s in loaded_services}
    missing_pks = existing_pks - loaded_pks
    if missing_pks:
        missing = list(Articleservice.objects.filter(pk__in=missing_pks).values('pk', 'nom', 'prix_vente'))
        loaded_services.extend(missing)
        extras['services_json'] = json.dumps(loaded_services, default=str)

    procedures_json = json.dumps([
        {
            'patient':      p.patient_id,
            'patient_code': p.patient.code_patient if p.patient else '',
            'service':      p.soin_type_id,
            'prix':         float(p.prix),
            'infirmier':    p.infirmier_id,
            'date':         p.date.strftime('%Y-%m-%dT%H:%M') if p.date else '',
            'statut':       p.statut,
        }
        for p in procedures_qs
    ], default=str)

    return render(request, 'soins/form.html', {
        'form': form,
        'soin': soin,
        'is_new': False,
        'counts': counts,
        'procedures_json': procedures_json,
        'hosp_warning': hosp_warning,
        **extras,
    })


@login_required(login_url='login')
def soins_administrer(request, pk):
    """Marque le soin comme terminé (dispensé). Réservé au groupe Soins."""
    if not request.user.has_perm('soins.can_administrer_soin'):
        messages.error(request, "Vous n'avez pas la permission d'administrer un soin.")
        return redirect('soins:detail', pk=pk)
    if request.method != 'POST':
        return redirect('soins:detail', pk=pk)
    soin = get_object_or_404(Soin.objects.select_related('facture'), pk=pk)
    if soin.statut != 'en_cours':
        messages.error(request, "Ce soin n'est pas en cours.")
        return redirect('soins:detail', pk=pk)
    if soin.hospitalisation_id:
        from hospitalisation.models import ServiceAFacturer
        saf_paye = ServiceAFacturer.objects.filter(
            hospitalisation_id=soin.hospitalisation_id,
            source__in=['soin', 'manuel'],
            facture__statut='payee'
        ).exists()
        if not saf_paye:
            messages.error(request, "Une facture complémentaire payée est requise avant d'administrer ce soin.")
            return redirect('soins:detail', pk=pk)
    elif not soin.facture or soin.facture.statut != 'payee':
        messages.error(request, "La facture doit être payée avant d'administrer le soin.")
        return redirect('soins:detail', pk=pk)
    soin.statut = 'termine'
    soin.termine_par = request.user
    soin.date_termine = timezone.now()
    soin.save(update_fields=['statut', 'termine_par', 'date_termine'])
    log_event(soin, request.user, 'Soin administré — statut : Terminé.', type='statut')
    _sync_procedures(soin, 'termine')
    messages.success(request, f"Soin de {soin.patient} marqué comme terminé.")
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
        return redirect('facturation:detail', pk=soin.facture.pk)

    from facturation.models import Facture, LigneFacture
    procedures = list(soin.procedures.select_related('soin_type').all())
    if not procedures:
        messages.error(request, "Ce soin n'a pas de lignes de soin à facturer.")
        return redirect('soins:detail', pk=pk)

    total = sum(p.prix for p in procedures)
    facture = Facture.objects.create(
        patient=soin.patient,
        cree_par=request.user,
        type_facture='soins',
        statut='emise',
        montant_total=total,
    )
    for proc in procedures:
        LigneFacture.objects.create(
            facture=facture,
            libelle=proc.soin_type.nom if proc.soin_type else f"Soin – {proc.numero}",
            quantite=1,
            prix_unitaire=proc.prix,
            remise=0,
        )
        proc.facture = facture
        proc.save(update_fields=['facture'])

    soin.facture = facture
    soin.save(update_fields=['facture'])
    log_event(soin, request.user, f'Facture {facture.numero if hasattr(facture, "numero") else ""} créée.', type='system')
    log_event(facture, request.user, 'Facture créée.', type='system')
    from django.urls import reverse
    detail_url = reverse('facturation:detail', kwargs={'pk': facture.pk})
    back_url = f'/soins/{soin.pk}/'
    return redirect(f'{detail_url}?next={back_url}')




@login_required(login_url='login')
def soins_terminer(request, pk):
    """Conservé pour compatibilité admin uniquement."""
    if request.method != 'POST':
        return redirect('soins:detail', pk=pk)
    soin = get_object_or_404(Soin, pk=pk)
    if request.user.is_superuser and soin.statut == 'en_cours':
        soin.statut = 'termine'
        soin.termine_par = request.user
        soin.date_termine = timezone.now()
        soin.save(update_fields=['statut', 'termine_par', 'date_termine'])
        log_event(soin, request.user, 'Soin terminé (admin).', type='statut')
        _sync_procedures(soin, 'termine')
    return redirect('soins:detail', pk=pk)


# ─── LISTE DES SOINS (ProcedureSoin) ───────────────────────────────────────

def _procedure_extras():
    services = list(Articleservice.objects.filter(
        type_article__in=['service', 'prestation']
    ).values('pk', 'nom', 'prix_vente'))
    employes = list(Employe.objects.order_by('nom', 'prenoms').values('pk', 'nom', 'prenoms'))
    # Ni rendez-vous ni factures sérialisés : le champ rendez-vous est commenté
    # dans le gabarit et la liste des factures se construit depuis le queryset du
    # formulaire. Les deux JSON pesaient 90 Ko par ouverture de page sans que
    # rien ne les lise — comme la liste de patients retirée avant eux.
    return {
        'services_json': json.dumps(services, default=str),
        'employes_json': json.dumps(employes),
        'maladies': Pathologie.objects.filter(actif=True),
    }


@login_required(login_url='login')
def procedure_list(request):
    """Liste des soins (procédures).

    Même brique que les soins infirmiers et les listes de rendez-vous : les
    filtres se cumulent, les regroupements s'imbriquent, les compteurs sont
    calculés en base. Auparavant un seul statut et une seule date à la fois,
    et la recherche annulait le filtre patient.
    """
    from django.core.paginator import Paginator

    from core.listing import Listing, menu_filtres, menu_groupes, paginer_groupes
    from .procedure_listing import (CHAMPS_RECHERCHE, FILTRES_DEFAUT,
                                    TRIS as TRIS_PROCEDURE,
                                    construire_dimensions, familles_procedures,
                                    libelle_periode)

    today = timezone.now().date()
    q = request.GET.get('q', '').strip()
    groupes = request.GET.getlist('group')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    patient_id = request.GET.get('patient_id', '').strip()

    base_qs = ProcedureSoin.objects.select_related(
        'patient', 'infirmier', 'departement', 'soin_type', 'maladie', 'facture'
    )
    # Entrée ciblée depuis une fiche patient : le filtre est imposé en amont de
    # la brique, et la recherche s'applique alors *à l'intérieur* de ce patient
    # au lieu de l'écraser comme avant.
    if patient_id:
        base_qs = base_qs.filter(patient_id=patient_id)

    declarees = construire_dimensions()
    listing = Listing(
        recherche=CHAMPS_RECHERCHE,
        familles=familles_procedures(),
        dimensions=list(declarees.values()),
        par_page=25,
        filtres_defaut=FILTRES_DEFAUT,
        tri_defaut=('-date',),
        tris=TRIS_PROCEDURE,
    )

    filtres = listing.filtres_demandes(request)
    qs = listing.appliquer_recherche(base_qs, q)
    qs = listing.appliquer_filtres(qs, filtres, {
        'aujourdhui': today, 'date_from': date_from, 'date_to': date_to,
    })
    tri, tri_sens = listing.tri_demande(request)
    qs = listing.trier(qs, groupes, tri, tri_sens)

    dims = [declarees[g] for g in groupes if g in declarees]
    arbre = []
    if dims:
        arbre, page_obj, nb_groupes = paginer_groupes(qs, dims, request.GET.get('page'))
        # La pagination porte sur les groupes : le compteur du titre doit rester
        # celui des procédures.
        total = qs.count()
    else:
        nb_groupes = 0
        page_obj = Paginator(qs, listing.par_page).get_page(request.GET.get('page'))
        total = page_obj.paginator.count

    stats = {
        'aujourdhui': ProcedureSoin.objects.filter(date__date=today).count(),
        'ce_mois': ProcedureSoin.objects.filter(date__month=today.month, date__year=today.year).count(),
        'en_cours': ProcedureSoin.objects.filter(statut='en_cours').count(),
        'termines': ProcedureSoin.objects.filter(statut='termine').count(),
    }

    patient_filtre = None
    if patient_id:
        try:
            patient_filtre = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            pass

    return render(request, 'soins/procedure/list.html', {
        'page_obj': page_obj,
        'arbre': arbre,
        'nb_groupes': nb_groupes,
        'total': total,
        'stats': stats,
        'q': q,
        'tri': tri,
        'tri_sens': tri_sens,
        'filters': filtres,
        'groups': groupes,
        'date_from': date_from,
        'date_to': date_to,
        'filtre_pose': bool(filtres),
        'selection_active': bool(q or groupes or filtres),
        'periode_libelle': libelle_periode(filtres, date_from, date_to),
        'listing_filtres': menu_filtres(listing.familles, filtres, date_from, date_to),
        'listing_groupes': menu_groupes(list(declarees.values()), groupes),
        'today': today,
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
        type_facture='soins',
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
            proc.cree_par = request.user
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
        'patient_affiche': patient_affiche(form),
        **_procedure_extras(),
    })


@login_required(login_url='login')
def procedure_detail(request, pk):
    proc = get_object_or_404(
        ProcedureSoin.objects.select_related(
            'patient', 'infirmier', 'departement', 'soin_type', 'maladie', 'rendez_vous', 'facture',
            'cree_par', 'modifie_par',
        ),
        pk=pk
    )
    facture_payee = (
        proc.facture is not None and
        proc.facture.statut == 'payee'
    )
    return render(request, 'soins/procedure/detail.html', {
        'proc': proc,
        'facture_payee': facture_payee,
        'logs': get_logs(proc),
    })


@login_required(login_url='login')
def procedure_edit(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    # Même règle que soins_edit : une fiche close reste ouverte à l'administration.
    peut_tout_modifier = request.user.is_superuser

    if (request.method == 'POST' and not peut_tout_modifier
            and proc.statut in ProcedureSoinForm.STATUTS_CLOS):
        # Le formulaire fige déjà tous les champs d'une procédure close, mais il
        # ne couvre pas les boutons de transition (`action`) qui court-circuitent
        # les champs. On refuse donc l'écriture en amont.
        messages.warning(request, "Cette procédure est clôturée : elle n'est plus modifiable.")
        return redirect('soins:procedure_detail', pk=proc.pk)
    if request.method == 'POST':
        form = ProcedureSoinForm(request.POST, instance=proc,
                                 peut_tout_modifier=peut_tout_modifier)
        if form.is_valid():
            proc = form.save(commit=False)
            proc.modifie_par = request.user
            proc.date_modification = timezone.now()
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
        form = ProcedureSoinForm(instance=proc, peut_tout_modifier=peut_tout_modifier)

    return render(request, 'soins/procedure/form.html', {
        'form': form,
        'proc': proc,
        'is_new': False,
        'peut_tout_modifier': peut_tout_modifier,
        'patient_affiche': patient_affiche(form),
        **_procedure_extras(),
    })


@login_required(login_url='login')
def procedure_terminer(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    if request.method == 'POST' and proc.statut == 'en_cours':
        proc.statut = 'termine'
        proc.save()
        log_event(proc, request.user, 'Procédure terminée.', type='statut')
    return redirect('soins:procedure_detail', pk=pk)


@login_required(login_url='login')
def procedure_annuler(request, pk):
    proc = get_object_or_404(ProcedureSoin, pk=pk)
    if request.method == 'POST' and proc.statut not in ('termine', 'annule'):
        proc.statut = 'annule'
        proc.save()
        log_event(proc, request.user, 'Procédure annulée.', type='statut')
    return redirect('soins:procedure_detail', pk=pk)


# ─── FACTURATION DEPUIS SOINS ───────────────────────────────────────────────

def _facturation_context(patient):
    from facturation.models import Acte
    from caisse.models import Caisse
    return {
        'actes': Acte.objects.filter(actif=True).order_by('categorie', 'libelle'),
        'caisses': Caisse.objects.filter(actif=True),
        'patient': patient,
    }


def _process_facturation_post(request, patient, origin_url):
    from facturation.models import Facture, LigneFacture, Acte, Paiement
    from facturation.forms import FactureForm

    def parse_float(val, default=0):
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    form = FactureForm(request.POST)
    if form.is_valid():
        facture = form.save(commit=False)
        facture.patient = patient
        facture.cree_par = request.user

        total = 0
        lignes_data = []
        i = 0
        while f'ligne_libelle_{i}' in request.POST:
            libelle = request.POST.get(f'ligne_libelle_{i}', '').strip()
            qte = parse_float(request.POST.get(f'ligne_qte_{i}'), 1)
            prix = parse_float(request.POST.get(f'ligne_prix_{i}'), 0)
            remise = parse_float(request.POST.get(f'ligne_remise_{i}'), 0)
            if libelle:
                montant = qte * prix * (1 - remise / 100)
                total += montant
                lignes_data.append({
                    'libelle': libelle,
                    'quantite': qte,
                    'prix_unitaire': prix,
                    'remise': remise,
                })
            i += 1

        facture.montant_total = round(total, 2)
        facture.save()

        for l in lignes_data:
            LigneFacture.objects.create(
                facture=facture,
                libelle=l['libelle'],
                quantite=l['quantite'],
                prix_unitaire=l['prix_unitaire'],
                remise=l['remise'],
            )

        pay_montant = parse_float(request.POST.get('pay_montant'), 0)
        pay_mode = request.POST.get('pay_mode', 'especes')
        pay_memo = request.POST.get('pay_memo', '')
        if pay_montant > 0:
            Paiement.objects.create(
                facture=facture,
                montant=pay_montant,
                mode_paiement=pay_mode,
                reference=pay_memo,
                recu_par=request.user,
            )
            facture.montant_paye = pay_montant
            facture.statut = 'payee'
            facture.save()

        messages.success(request, f"Facture {facture.numero} créée avec succès.")
        return redirect('facturation:list')

    return form


@login_required(login_url='login')
def soin_facturer(request, pk):
    from facturation.models import Facture, LigneFacture
    from django.urls import reverse

    soin = get_object_or_404(
        Soin.objects.select_related('patient'), pk=pk
    )
    procedures = list(soin.procedures.select_related('soin_type').all())

    if procedures:
        total = sum(p.prix for p in procedures)
        facture = Facture.objects.create(
            patient=soin.patient,
            cree_par=request.user,
            type_facture='soins',
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
        facture = Facture.objects.create(
            patient=soin.patient,
            cree_par=request.user,
            type_facture='soins',
            statut='brouillon',
            montant_total=0,
        )
        LigneFacture.objects.create(
            facture=facture,
            libelle="Soins infirmiers",
            quantite=1,
            prix_unitaire=0,
            remise=0,
        )

    detail_url = reverse('facturation:detail', kwargs={'pk': facture.pk})
    return redirect(f'{detail_url}?next=/soins/{pk}/')


@login_required(login_url='login')
def procedure_facturer(request, pk):
    from facturation.models import Facture, LigneFacture
    from django.urls import reverse

    proc = get_object_or_404(
        ProcedureSoin.objects.select_related('patient', 'soin_type', 'facture'), pk=pk
    )

    if proc.facture_id:
        messages.warning(request, "Cette procédure est déjà associée à la facture.")
        return redirect('soins:procedure_detail', pk=pk)

    # Une procédure annulée ne se facture pas : l'acte n'a pas eu lieu. Le
    # bouton est masqué dans le gabarit, mais l'URL restait atteignable et
    # créait la facture sans rien vérifier.
    if proc.statut == 'annule':
        messages.error(request, "Une procédure annulée ne peut pas être facturée.")
        return redirect('soins:procedure_detail', pk=pk)

    soin_label = proc.soin_type.nom if proc.soin_type else "Soin"
    libelle = f"{soin_label} - {proc.numero}"

    facture = Facture.objects.create(
        patient=proc.patient,
        cree_par=request.user,
        type_facture='soins',
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

    detail_url = reverse('facturation:detail', kwargs={'pk': facture.pk})
    return redirect(f'{detail_url}?next=/soins/procedures/{pk}/')
