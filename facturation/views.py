from datetime import date, datetime as dt

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.urls import reverse

from .models import Facture, LigneFacture, Acte, Paiement, Caisse
from .forms import FactureForm
from core.views import log_event, get_logs
from soins.regles import demarrer_soin_de_facture
from pharmacie.disponibilite import pharmacie_active
from pharmacie.sorties import (produits_indisponibles, rendre_les_produits,
                               sortir_les_produits)

def can_manage_paiement(user):
    """Peut enregistrer un encaissement.

    La permission s'attribue à un groupe dans /admin/ ; elle ne dépend plus du
    nom que porte ce groupe.
    """
    return user.has_perm('facturation.can_encaisser')


@login_required(login_url='login')
def facturation_list(request):
    """Liste des factures, bâtie sur core.listing comme les autres modules.

    Le menu de filtres écrit à la main dans le gabarit ne portait qu'un statut,
    un type et un intervalle de dates, sans regroupement ni compteurs. Il est
    remplacé par la brique commune : les filtres se cumulent, les regroupements
    s'imbriquent, et les comptes des en-têtes sont calculés en base sur toute la
    sélection.
    """
    from core.listing import Listing, menu_filtres, menu_groupes, paginer_groupes
    from .facture_listing import (CHAMPS_RECHERCHE, FILTRES_DEFAUT, TRIS,
                                  construire_dimensions, familles_factures,
                                  libelle_periode)

    today = date.today()
    q = request.GET.get('q', '').strip()
    groupes = request.GET.getlist('group')
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    base_qs = (Facture.objects
               .select_related('patient', 'centre')
               # Le regroupement par caisse lit les paiements de chaque facture :
               # sans ce préchargement, une requête par ligne affichée.
               .prefetch_related('paiements__caisse')
               # `solde_restant` est une propriété Python : la colonne « Reste »
               # ne serait pas triable sans cette annotation.
               .annotate(reste=F('montant_total') - F('montant_paye')))

    declarees = construire_dimensions()
    listing = Listing(
        recherche=CHAMPS_RECHERCHE,
        familles=familles_factures(),
        dimensions=list(declarees.values()),
        par_page=25,
        filtres_defaut=FILTRES_DEFAUT,
        tri_defaut=('-date_emission',),
        tris=TRIS,
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
        # La pagination porte alors sur les groupes : le compteur du titre doit
        # rester celui des factures.
        total = qs.count()
    else:
        nb_groupes = 0
        page_obj = Paginator(qs, listing.par_page).get_page(request.GET.get('page'))
        total = page_obj.paginator.count

    # Les cartes du haut portent sur la sélection, et non sur tout le centre :
    # une liste filtrée sur la journée affichait le total facturé depuis
    # l'ouverture, ce qui ne se rapportait à rien de ce qu'on avait sous les yeux.
    # `order_by()` vide l'ordre : il n'a pas de sens dans une agrégation, et
    # laissé en place il ajouterait ses colonnes au GROUP BY.
    sommes = qs.order_by().aggregate(
        total=Sum('montant_total'),
        paye=Sum('montant_paye'),
        nb=Count('id'),
        nb_payees=Count('id', filter=Q(statut='payee')),
        nb_emises=Count('id', filter=Q(statut='emise')),
    )
    montant_total = sommes['total'] or 0
    montant_recu  = sommes['paye'] or 0

    stats = {
        'montant_total':   int(montant_total),
        'montant_recu':    int(montant_recu),
        'montant_attente': int(montant_total - montant_recu),
        'nb_factures':     sommes['nb'],
        'nb_payees':       sommes['nb_payees'],
        'nb_emises':       sommes['nb_emises'],
    }

    return render(request, 'facturation/list.html', {
        'page_obj':          page_obj,
        'arbre':             arbre,
        'nb_groupes':        nb_groupes,
        'total':             total,
        'stats':             stats,
        'q':                 q,
        'tri':               tri,
        'tri_sens':          tri_sens,
        'filters':           filtres,
        'groups':            groupes,
        'date_from':         date_from,
        'date_to':           date_to,
        'filtre_pose':       bool(filtres),
        'selection_active':  bool(q or groupes or filtres),
        'periode_libelle':   libelle_periode(filtres, date_from, date_to),
        'listing_filtres':   menu_filtres(listing.familles, filtres, date_from, date_to),
        'listing_groupes':   menu_groupes(list(declarees.values()), groupes),
        'today':             today,
        # Largeur des bandes de groupe : la colonne Centre n'existe
        # que pour le superutilisateur.
        'colonnes':          9 if request.user.is_superuser else 8,
    })


@login_required(login_url='login')
def facture_create(request):
    from patients.models import Patient, RendezVous
    from services.models import Articleservice

    patient_pk = request.GET.get('patient') or request.POST.get('patient_id')
    patient    = get_object_or_404(Patient.all_objects, pk=patient_pk) if patient_pk else None
    actes      = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses    = Caisse.objects.filter(actif=True).order_by('nom')
    services   = _designations_proposees(request)

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
            demande_obj = DemandeExamen.all_objects.prefetch_related('lignes__type_examen').get(pk=demande_pk)
        except Exception:
            pass

    ordonnance_obj = None
    ordonnance_pk  = request.GET.get('ordonnance') or request.POST.get('ordonnance_id')
    if ordonnance_pk:
        try:
            from consultations.models import Ordonnance
            ordonnance_obj = Ordonnance.objects.prefetch_related(
                'lignes__produit'
            ).get(pk=ordonnance_pk)
        except Exception:
            pass

    initial_lignes = []
    if demande_obj:
        for ligne in demande_obj.lignes.select_related('type_examen', 'article_service').all():
            libelle = ligne.libelle or (str(ligne.type_examen) if ligne.type_examen else '')
            initial_lignes.append({
                'libelle': libelle,
                'prix': ligne.prix,
                'qte': 1,
                'remise': 0,
                # L'article manquait : sans lui la ligne ne comptait pour
                # aucune nature, et le type de la facture ne pouvait plus se
                # déduire de son contenu.
                'reference': f'a:{ligne.article_service_id}' if ligne.article_service_id else '',
                # D'où vient la ligne : ce qui reste à la validation est payé.
                'ligne_demande': ligne.pk,
            })
    elif ordonnance_obj:
        for ligne in ordonnance_obj.lignes.all():
            if ligne.produit:
                libelle = ligne.produit.nom
                # `float()` rendait « 15000.0 » dans la case Prix. Le Decimal
                # du catalogue s'y affiche tel qu'il est saisi.
                prix    = ligne.produit.prix_vente
                # La référence manquait : le gabarit la lit pour rattacher la
                # ligne au produit du stock. Sans elle, une facture née d'une
                # ordonnance encaissait le bon montant et ne décomptait rien.
                reference = f'p:{ligne.produit_id}'
            elif ligne.medicament_libre:
                libelle = ligne.medicament_libre
                prix    = 0
                reference = ''
            else:
                continue
            initial_lignes.append({
                'libelle':   libelle,
                'prix':      prix,
                'qte':       ligne.quantite,
                'remise':    0,
                'reference': reference,
                # D'où vient la ligne. Ce qui reste à la validation est payé ;
                # ce qui a disparu de la grille ne l'est pas, et la pharmacie
                # ne le servira pas.
                'ligne_ordonnance': ligne.pk,
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
        has_ligne = any(
            k.startswith('ligne_libelle_') and v.strip()
            for k, v in request.POST.items()
        )
        if not has_ligne:
            messages.error(request, "Ajoutez au moins une ligne avec une désignation avant d'enregistrer.")
            return redirect(request.get_full_path())
        if ordonnance_obj and Facture.objects.filter(ordonnance=ordonnance_obj).exclude(statut='annulee').exists():
            messages.error(request, 'Cette ordonnance a déjà été facturée.')
            return redirect('ordonnance_detail', pk=ordonnance_obj.pk)
        if form.is_valid():
            facture = form.save(commit=False)
            facture.patient  = patient
            facture.cree_par = request.user
            if hosp_obj:
                facture.hospitalisation = hosp_obj
                facture.type_facture    = 'hospitalisation'
            if rdv_obj:
                facture.rendez_vous = rdv_obj
            facture.save()

            total = _save_lignes(facture, request.POST,
                                 pharmacie_active(request))
            facture.montant_total = total
            # Le type suit ce qu'on a mis dedans : une seule nature donne ce
            # type, plusieurs donnent « Mixte ». Le caissier n'a plus à y
            # toucher, et ne peut plus se tromper.
            facture.appliquer_type_deduit(save=False)
            facture.save()

            if demande_obj:
                demande_obj.facture = facture
                demande_obj.save(update_fields=['facture'])
                _sync_lignes_demande_examen(facture)

            if ordonnance_obj:
                facture.ordonnance = ordonnance_obj
                facture.save(update_fields=['ordonnance'])

            log_event(facture, request.user, 'Facture créée.', type='system')

            if request.POST.get('pay_montant', '').strip() and not can_manage_paiement(request.user):
                messages.warning(request, "Facture créée, mais le paiement n'a pas été enregistré : cette action est réservée à la Caisse.")
            else:
                facture = _handle_paiement(facture, request.POST, request.user,
                                           total, request)

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
        # Même piège que `_save_lignes` : s'arrêter au premier indice absent
        # faisait disparaître, à la ré-affichage, toutes les lignes situées
        # après celle que la caissière venait de retirer.
        _post_lignes = [{
            'libelle': request.POST.get(f'ligne_libelle_{_i}'),
            'prix':    request.POST.get(f'ligne_prix_{_i}', 0),
            'qte':     request.POST.get(f'ligne_qte_{_i}', 1),
            'remise':  request.POST.get(f'ligne_remise_{_i}', 0),
            'reference': request.POST.get(f'ligne_service_{_i}', ''),
            'ligne_ordonnance': request.POST.get(f'ligne_ordonnance_{_i}', ''),
            'ligne_demande': request.POST.get(f'ligne_demande_{_i}', ''),
        } for _i in _indices_des_lignes(request.POST)]
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
        'modes_paiement':       Paiement.MODE,
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
    facture   = get_object_or_404(Facture.objects.select_related('centre'), pk=pk)
    lignes    = facture.lignes.all()
    paiements = facture.paiements.select_related('caisse').order_by('date_paiement') if hasattr(facture, 'paiements') else []
    logs      = get_logs(facture)
    back_url  = request.GET.get('next', reverse('facturation:list'))

    # Médecin associé à la facture — selon l'origine (rendez-vous, consultation,
    # hospitalisation). Ne pas prendre depuis `soins.Soin` (infirmier, sans rapport).
    docteur = None
    if facture.rendez_vous_id and facture.rendez_vous.medecin_id:
        docteur = facture.rendez_vous.medecin
    elif facture.consultation_id and facture.consultation.medecin_id:
        docteur = facture.consultation.medecin
    elif facture.hospitalisation_id and facture.hospitalisation.medecin_traitant_id:
        docteur = facture.hospitalisation.medecin_traitant

    return render(request, 'facturation/detail.html', {
        'facture':   facture,
        'lignes':    lignes,
        'paiements': paiements,
        'logs':      logs,
        'docteur':   docteur,
        'is_admin':  request.user.is_superuser or request.user.is_staff,
        'can_manage_paiement': can_manage_paiement(request.user),
        # La modale d'encaissement de cet écran proposait cinq journaux écrits
        # en dur — « CAISSE ACCUEIL », « BANQUE »… — dont aucun n'existait en
        # base. Elle lit désormais les mêmes caisses que l'écran de création.
        'caisses':   Caisse.objects.filter(actif=True).order_by('nom'),
        'modes_paiement': Paiement.MODE,
        'back_url':  back_url,
    })


@login_required(login_url='login')
def facture_valider(request, pk):
    facture  = get_object_or_404(Facture, pk=pk)
    back_url = request.POST.get('next', reverse('facturation:list'))
    if request.method == 'POST' and facture.statut == 'brouillon':
        if not request.user.has_perm('facturation.can_valider_facture'):
            messages.error(request, "Vous n'avez pas la permission de valider une facture.")
        else:
            facture.statut = 'emise'
            facture.save()
            log_event(facture, request.user, 'Statut changé : émise', type='statut')
            messages.success(request, f"Facture {facture.numero} validée et émise.")
    return redirect(f"{reverse('facturation:detail', kwargs={'pk': pk})}?next={back_url}")


@login_required(login_url='login')
def facture_payer(request, pk):
    if not can_manage_paiement(request.user):
        raise PermissionDenied
    facture  = get_object_or_404(Facture, pk=pk)
    if request.method != 'POST':
        return redirect('facturation:detail', pk=pk)
    back_url = request.POST.get('next', reverse('facturation:list'))

    _montant, erreur = _montant_paiement(request.POST.get('pay_montant'), facture)
    if erreur:
        messages.error(request, erreur)
    elif facture.statut in ('brouillon', 'emise'):
        # Cette vue refaisait mot pour mot le travail de `_handle_paiement`, à
        # quelques différences près — pas de journal du paiement, une référence
        # lue dans un autre champ. Deux portes vers le même geste, c'est deux
        # endroits où brancher la sortie de stock et un qu'on oublie. Elle
        # délègue désormais, et il n'y a plus qu'un seul encaissement.
        _handle_paiement(facture, request.POST, request.user,
                         facture.montant_total, request)

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
    if facture.statut != 'payee':
        messages.error(request, "L'aperçu n'est disponible qu'une fois la facture entièrement payée.")
        back_url = request.GET.get('next') or reverse('facturation:list')
        return redirect(f"{reverse('facturation:detail', kwargs={'pk': pk})}?next={back_url}")
    return render(request, 'facturation/apercu.html', {
        'facture':   facture,
        'lignes':    facture.lignes.select_related('acte').all(),
        'paiements': facture.paiements.all(),
        'back_url':  request.GET.get('next', reverse('facturation:list')),
    })


@login_required(login_url='login')
def facture_edit(request, pk):
    from services.models import Articleservice

    facture  = get_object_or_404(Facture, pk=pk)
    retour = f"{reverse('facturation:detail', kwargs={'pk': pk})}?next={request.GET.get('next') or reverse('facturation:list')}"
    if not request.user.has_perm('facturation.change_facture'):
        messages.error(request, "Vous n'avez pas la permission de modifier une facture.")
        return redirect(retour)
    # Une facture payée ou annulée est close : les actions de workflow plus bas
    # ne l'acceptent déjà que pour un superutilisateur, mais la sauvegarde du
    # formulaire, elle, ne vérifiait rien — on pouvait en réécrire les lignes en
    # postant directement sur cette URL. La règle vaut maintenant pour toute la
    # vue.
    if facture.statut in ('payee', 'annulee') and not request.user.is_superuser:
        messages.error(request, "Une facture payée ou annulée ne peut être modifiée que par un administrateur.")
        return redirect(retour)
    actes    = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses  = Caisse.objects.filter(actif=True).order_by('nom')
    services = _designations_proposees(request)
    is_admin = request.user.is_superuser
    back_url = request.GET.get('next', reverse('facturation:detail', kwargs={'pk': pk}))

    if request.method == 'POST':
        back_url = request.POST.get('next', back_url)
        detail_url = reverse('facturation:detail', kwargs={'pk': pk})

        # ── Actions workflow ────────────────────────────────────────────────
        if 'action_emettre' in request.POST:
            if not request.user.has_perm('facturation.can_valider_facture'):
                messages.error(request, "Vous n'avez pas la permission de valider une facture.")
            elif facture.statut == 'brouillon' or is_admin:
                facture.statut = 'emise'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Émise', type='statut')
                messages.success(request, 'Facture émise.')
            return redirect(f'{detail_url}?next={back_url}')

        if 'action_payer' in request.POST:
            if not can_manage_paiement(request.user):
                raise PermissionDenied
            pharmacie = pharmacie_active(request)
            manquants = produits_indisponibles(facture, pharmacie)
            if manquants:
                # Seconde porte vers « payée », soumise à la même règle que
                # l'encaissement : on ne solde pas une facture dont la pharmacie
                # ne peut plus honorer les produits.
                detail = ', '.join(f"{nom} (demandé {demande:g}, en rayon {dispo:g})"
                                   for nom, demande, dispo in manquants)
                messages.error(request, "Facture non soldée — la pharmacie ne peut "
                                        f"plus servir : {detail}")
            elif facture.statut in ('emise', 'brouillon') or is_admin:
                facture.statut = 'payee'
                facture.save()
                log_event(facture, request.user, 'Statut changé : Payée', type='statut')
                sortis = sortir_les_produits(facture, pharmacie, request.user)
                if sortis:
                    log_event(facture, request.user,
                              f'{sortis} produit(s) sortis du stock de la pharmacie.',
                              type='modif')
                demarrer_soin_de_facture(facture)
                messages.success(request, 'Facture marquée comme payée.')
            return redirect(f'{detail_url}?next={back_url}')

        if 'action_annuler' in request.POST:
            if facture.statut != 'annulee' or is_admin:
                facture.statut = 'annulee'
                facture.save()
                log_event(facture, request.user, 'Facture annulée', type='statut')
                # Les produits déjà sortis retournent en rayon : la facture
                # annulée ne les a finalement pas remis au patient.
                rendus = rendre_les_produits(facture, pharmacie_active(request),
                                             request.user)
                if rendus:
                    log_event(facture, request.user,
                              f'{rendus} produit(s) remis en stock.', type='modif')
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
            total = _save_lignes(facture, request.POST,
                                 pharmacie_active(request))
            facture.montant_total = total
            facture.appliquer_type_deduit(save=False)
            facture.save()
            _sync_lignes_demande_examen(facture)
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
            # Sans lui, rouvrir une facture puis l'enregistrer perdrait le lien
            # vers l'article — et donc la nature de chaque ligne.
            # Référence préfixée : l'article 12 et le produit 12 se ressemblent.
            'reference': (f'a:{l.article_id}' if l.article_id
                          else f'p:{l.produit_id}' if l.produit_id else ''),
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
        'modes_paiement': Paiement.MODE,
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


def _caisse_choisie(POST):
    """Caisse désignée par le champ « Journal » de l'écran d'encaissement.

    Tolérante à dessein : un identifiant vide, illisible ou pointant sur une
    caisse supprimée rend None, et le paiement s'enregistre quand même sans
    caisse. Perdre un encaissement parce qu'un journal a été désactivé entre
    l'affichage du formulaire et sa validation serait pire que de l'ignorer.
    """
    brut = (POST.get('pay_journal') or '').strip()
    if not brut:
        return None
    try:
        return Caisse.objects.filter(pk=int(brut)).first()
    except (TypeError, ValueError):
        return None


def _montant_recu(POST, mode):
    """Ce que le patient a tendu, pour en déduire la monnaie à rendre.

    Seulement en espèces : ailleurs le compte est juste par construction, et un
    champ resté rempli d'un mode précédent fausserait le reçu. Une saisie
    illisible ou négative est ignorée plutôt que refusée — l'encaissement compte
    plus que cette information d'appoint.
    """
    if mode != 'especes':
        return None
    brut = (POST.get('pay_recu') or '').strip()
    if not brut:
        return None
    try:
        valeur = float(brut)
    except (TypeError, ValueError):
        return None
    return valeur if valeur >= 0 else None


def _montant_paiement(brut, facture):
    """Le montant à encaisser, ou None s'il n'y a rien à créer.

    Renvoie `(montant, erreur)` — l'un des deux vaut toujours None.

    Un paiement de 0 F n'est accepté que si la facture ne réclame plus rien :
    c'est le cas d'une prestation gratuite, qu'il faut malgré tout pouvoir
    tracer — qui l'a traitée, quand, par quel mode. Ailleurs, 0 est presque
    toujours un champ vidé par mégarde : l'accepter poserait une ligne de
    paiement sans valeur sur une facture qui reste due, sans prévenir personne.

    Le champ vide et le zéro délibéré doivent aussi être distingués : `float('')`
    lève, et l'ancien code rabattait l'échec sur 0. Tant que 0 était refusé cela
    ne se voyait pas ; en l'acceptant, un champ vide aurait créé un paiement.
    """
    brut = (brut or '').strip()
    if not brut:
        return None, None            # aucun paiement demandé, ce n'est pas une erreur
    try:
        montant = float(brut)
    except (TypeError, ValueError):
        return None, "Montant de paiement invalide."
    if montant < 0:
        return None, "Le montant d'un paiement ne peut pas être négatif."
    if montant == 0 and facture.solde_restant > 0:
        return None, ("Un paiement de 0 F n'est possible que sur une facture "
                      "sans solde à régler.")
    # Le gabarit pose déjà `max` sur le solde, mais c'est le navigateur qui
    # l'applique : une requête envoyée hors de la page passait outre et la
    # caisse enregistrait plus que ce qui était dû. La borne doit tenir ici.
    if montant > float(facture.solde_restant):
        return None, ("Le montant dépasse le solde restant de la facture "
                      "(%s F)." % int(facture.solde_restant))
    return montant, None


def _designations_proposees(request):
    """Tout ce qu'on peut poser sur une ligne de facture, en une seule liste.

    Deux catalogues s'y mêlent, et c'est voulu : `services.Articleservice` porte
    les actes et les examens, `stock.Produit` les médicaments et les
    consommables. Les seconds manquaient à l'écran — on ne pouvait pas facturer
    les gants d'un examen, ni la boîte de paracétamol remise au comptoir.

    Les produits sont ceux de la pharmacie du centre actif, avec leur stock
    réel : facturer un produit que Yamoussoukro possède et que Toumbokro n'a pas
    laisserait le patient repartir les mains vides. Les ruptures restent
    affichées, grisées et non sélectionnables — cachées, elles seraient
    ressaisies à la main.

    `src` distingue les deux à l'enregistrement : `a` pour un article, `p` pour
    un produit. Ils vivent dans deux tables, donc deux clés étrangères.
    """
    from services.models import Articleservice

    from pharmacie.disponibilite import produits_pour_ecran

    designations = [
        {'src': 'a', 'pk': a.pk, 'nom': a.nom, 'prix': float(a.prix_vente or 0),
         'stock': None, 'rupture': False}
        for a in Articleservice.objects.select_related('categorie')
                                       .filter(actif=True).order_by('nom')
    ]
    designations += [
        {'src': 'p', 'pk': p['pk'], 'nom': p['designation'],
         'prix': p['prix_vente'], 'stock': p['stock_actuel'],
         'rupture': p['rupture']}
        for p in produits_pour_ecran(request)
    ]
    return designations


def _poser_origine(ligne, reference, pharmacie):
    """Rattache la ligne à l'article ou au produit choisi dans la liste.

    La référence est préfixée — `a:12` ou `p:7` — parce que les deux catalogues
    numérotent chacun de leur côté : sans le préfixe, l'article 12 et le produit
    12 seraient indiscernables.

    Un produit que la pharmacie ne peut pas servir n'est pas rattaché : la ligne
    reste, avec son libellé, mais elle cesse de prétendre sortir d'un stock qui
    ne l'a pas. L'écran grise déjà ces produits ; ce contrôle-ci est celui qui
    compte, puisqu'une liste déroulante ne protège de rien.
    """
    from pharmacie.disponibilite import est_disponible

    if not reference or ':' not in reference:
        return
    source, _, brut = reference.partition(':')
    try:
        pk = int(brut)
    except (TypeError, ValueError):
        return
    if source == 'a':
        ligne.article_id = pk
    elif source == 'p' and est_disponible(pk, pharmacie, ligne.quantite):
        ligne.produit_id = pk


def _poser_ligne_ordonnance(ligne, brut):
    """Rattache la ligne à la ligne d'ordonnance qu'elle facture.

    Vide sur une ligne ajoutée au comptoir : la caissière peut ajouter ce que
    le médecin n'a pas prescrit, et la pharmacie le servira quand même — c'est
    la facture qui commande la dispensation, pas la prescription.
    """
    if not brut:
        return
    try:
        ligne.ligne_ordonnance_id = int(brut)
    except (TypeError, ValueError):
        pass


def _indices_des_lignes(POST):
    """Les indices de lignes présents dans le formulaire, dans l'ordre.

    On s'arrêtait au premier indice absent. Or le bouton « × » retire la ligne
    du tableau sans renuméroter les suivantes, et les indices sont distribués
    par un compteur qui ne redescend jamais : retirer une ligne creuse un trou.

    Le résultat était silencieux et coûteux. Retirer une ligne du milieu de
    cinq n'en facturait plus que deux ; retirer la première laissait une
    facture **vide, à zéro franc**. C'est le geste le plus courant de la
    caisse — le patient dit qu'il a déjà tel médicament, on l'enlève — et il
    faisait perdre le reste de la facture.
    """
    indices = []
    for cle in POST:
        if cle.startswith('ligne_libelle_'):
            try:
                indices.append(int(cle[len('ligne_libelle_'):]))
            except ValueError:
                continue
    return sorted(indices)


def _poser_ligne_demande(ligne, brut):
    """Rattache la ligne à la ligne de demande d'examen qu'elle facture."""
    if not brut:
        return
    try:
        ligne.ligne_demande_examen_id = int(brut)
    except (TypeError, ValueError):
        pass


def _save_lignes(facture, POST, pharmacie=None):
    total = 0
    for i in _indices_des_lignes(POST):
        libelle = POST.get(f'ligne_libelle_{i}')
        if libelle and libelle.strip():
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
            # L'origine de la ligne, d'où se déduira le type de la facture.
            # Absente d'une ligne tapée à la main : elle ne comptera alors pour
            # aucune nature, plutôt que d'en deviner une d'après son libellé.
            _poser_origine(ligne, POST.get(f'ligne_service_{i}'), pharmacie)
            _poser_ligne_ordonnance(ligne, POST.get(f'ligne_ordonnance_{i}'))
            _poser_ligne_demande(ligne, POST.get(f'ligne_demande_{i}'))
            ligne.save()
            total += qte * prix * (1 - remise / 100)
    return total


def _sync_lignes_demande_examen(facture):
    """Reporte sur la demande d'examen ce que la caisse a fait de la facture.

    La fonction **effaçait toutes les lignes de la demande** et les recréait
    d'après la facture. Deux dégâts, l'un visible et l'autre pas :

    * un examen retiré à la caisse disparaissait de la demande, sans trace.
      Le médecin ne pouvait plus voir ce qu'il avait demandé, ni personne
      pourquoi l'examen n'avait pas été fait ;
    * la recréation ne reposait que le libellé, le prix et les instructions.
      `article_service` et `type_examen` étaient perdus à chaque enregistrement
      de la facture — or c'est `article_service` qui porte le **code HPRIM**
      envoyé au laboratoire partenaire (voir laboratoire.hprim.integration).
      La demande partait donc sans code dès qu'elle était facturée.

    Désormais on ne supprime rien. Les lignes demandées restent ; celles que la
    facture ne porte pas se liront « non payé » (voir `_examens_non_payes`).
    Un examen ajouté au comptoir est ajouté à la demande — le laboratoire doit
    le faire — et rattaché à sa ligne de facture.

    Ignorée si la facture n'est pas liée à une demande, ou à plusieurs.
    """
    from laboratoire.models import LigneDemandeExamen

    demandes = list(facture.demandes_examens.all())
    if len(demandes) != 1:
        return
    demande = demandes[0]

    lignes_facture = list(facture.lignes.all())
    deja_liees = {l.ligne_demande_examen_id for l in lignes_facture
                  if l.ligne_demande_examen_id}

    # Les examens ajoutés à la caisse, que le médecin n'avait pas demandés.
    for ligne in lignes_facture:
        if ligne.ligne_demande_examen_id or not _est_un_examen(ligne):
            continue
        nouvelle = LigneDemandeExamen.objects.create(
            demande=demande,
            libelle=ligne.libelle,
            prix=ligne.montant_ligne,
            article_service=ligne.article,
            origine='caisse',
        )
        ligne.ligne_demande_examen = nouvelle
        ligne.save(update_fields=['ligne_demande_examen'])
        deja_liees.add(nouvelle.pk)

    # Le prix facturé fait foi sur celui qui avait été estimé à la demande.
    montants = {l.ligne_demande_examen_id: l.montant_ligne
                for l in facture.lignes.all() if l.ligne_demande_examen_id}
    total = 0
    for ligne in demande.lignes.all():
        montant = montants.get(ligne.pk)
        if montant is None:
            continue        # retiré à la caisse : ne compte pas dans le total
        if ligne.prix != montant:
            ligne.prix = montant
            ligne.save(update_fields=['prix'])
        total += montant

    demande.montant_total = total
    demande.save(update_fields=['montant_total'])


def _est_un_examen(ligne):
    """Cette ligne de facture est-elle un examen de laboratoire ?

    Une facture d'examens n'est pas faite que d'examens : la caisse y ajoute
    volontiers une boîte de gants ou une consultation. Sans ce tri, tout ce
    qu'elle ajoutait partait sur la demande, et le laboratoire se voyait
    réclamer d'« exécuter » un consommable.

    On tranche par la **catégorie de l'article**, la même table qui donne son
    type à la facture. Une ligne rattachée à un produit du stock n'est jamais
    un examen. Une ligne tapée à la main n'a pas de catégorie : dans le doute
    on ne l'envoie pas au laboratoire — un examen manquant se voit et se
    rattrape, un consommable sur un bulletin d'analyses sème le doute.
    """
    from .models import CATEGORIE_VERS_TYPE

    if ligne.produit_id or not ligne.article_id:
        return False
    code = getattr(getattr(ligne.article, 'categorie', None), 'code', None)
    return CATEGORIE_VERS_TYPE.get(code) in ('laboratoire', 'imagerie')


def _examens_non_payes(demande):
    """Identifiants des lignes de la demande qu'aucune facture ne porte.

    Déduit et non stocké, comme pour l'ordonnance : rien à resynchroniser, et
    la réponse suit toute modification ultérieure de la facture.
    """
    from facturation.models import LigneFacture

    facture = getattr(demande, 'facture', None)
    if facture is None or facture.statut == 'annulee':
        return set()
    payees = set(
        LigneFacture.objects
        .filter(facture=facture, ligne_demande_examen__isnull=False)
        .values_list('ligne_demande_examen_id', flat=True))
    return {l.pk for l in demande.lignes.all() if l.pk not in payees}


def _handle_paiement(facture, POST, user, total, request=None):
    if not can_manage_paiement(user):
        return facture
    pay_montant, _erreur = _montant_paiement(POST.get('pay_montant'), facture)
    if pay_montant is None:
        return facture

    # Facturer un produit, c'est le remettre au patient : on refuse d'encaisser
    # ce que la pharmacie ne peut plus servir. La dernière boîte a pu partir
    # entre la saisie de la ligne et l'encaissement — prendre l'argent quand
    # même laisserait le stock mentir et le patient repartir les mains vides.
    pharmacie = pharmacie_active(request)
    manquants = produits_indisponibles(facture, pharmacie)
    if manquants:
        detail = ', '.join(f"{nom} (demandé {demande:g}, en rayon {dispo:g})"
                           for nom, demande, dispo in manquants)
        if request is not None:
            messages.error(request, "Paiement refusé — la pharmacie ne peut plus "
                                    f"servir : {detail}")
        return facture

    mode      = POST.get('pay_mode', 'especes')
    # Les deux écrans ne nomment pas ce champ pareil : « mémo » à la création,
    # « référence » sur la fiche. Le premier renseigné fait foi.
    memo      = POST.get('pay_memo') or POST.get('pay_reference', '')
    # `pay_compte` (« compte bancaire du bénéficiaire ») a été retiré de l'écran :
    # sa liste n'a jamais contenu la moindre option, donc la référence retombait
    # déjà toujours sur le mémo.
    reference = memo

    Paiement.objects.create(
        facture=facture,
        montant=pay_montant,
        mode_paiement=mode,
        caisse=_caisse_choisie(POST),
        montant_recu=_montant_recu(POST, mode),
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
    # Le stock bouge quand la facture est soldée, pas avant : un règlement
    # partiel ne donne pas droit à la marchandise. L'opération se relance sans
    # dommage — chaque mouvement porte le numéro de la facture.
    if facture.statut == 'payee':
        sortis = sortir_les_produits(facture, pharmacie, user)
        if sortis:
            log_event(facture, user,
                      f'{sortis} produit(s) sortis du stock de la pharmacie.',
                      type='modif')
    demarrer_soin_de_facture(facture)
    return facture


# ─── Configuration : les caisses (journaux d'encaissement) ────────────────────
#
# Venait de l'application `caisse`, supprimée : elle ne savait rien faire de
# plus qu'afficher une liste figée. La création et la modification passent par
# la modale partagée de configuration, comme dans hospitalisation et medecins —
# les gabarits pleine page restent le repli quand on ouvre l'URL directement.

_CAISSE_TPL_PAGE  = 'facturation/config/caisses/form.html'
_CAISSE_TPL_MODAL = 'facturation/config/caisses/form_modal.html'


def _est_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@login_required(login_url='login')
@permission_required('facturation.view_caisse', raise_exception=True)
def caisses_list(request):
    q = request.GET.get('q', '').strip()
    # `total` annoté ici plutôt que via la propriété `Caisse.total_encaisse` :
    # celle-ci ferait une requête par ligne du tableau.
    # `order_by` explicite : le GROUP BY ajouté par l'annotation fait tomber
    # l'ordre déclaré dans Meta, et la pagination avertit alors sur une liste
    # non triée.
    qs = Caisse.objects.annotate(total=Sum('paiements__montant')).order_by('nom')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    page_obj = Paginator(qs, 25).get_page(request.GET.get('page', 1))
    return render(request, 'facturation/config/caisses/list.html', {
        'page_obj': page_obj,
        'q': q,
    })


@login_required(login_url='login')
@permission_required('facturation.add_caisse', raise_exception=True)
def caisse_create(request):
    from .forms import CaisseForm
    ajax = _est_ajax(request)
    if request.method == 'POST':
        form = CaisseForm(request.POST)
        if form.is_valid():
            caisse = form.save()
            if ajax:
                return JsonResponse({'ok': True, 'message': 'Caisse « %s » créée.' % caisse.nom})
            messages.success(request, 'Caisse « %s » créée.' % caisse.nom)
            return redirect('facturation:caisses_list')
    else:
        form = CaisseForm()
    return render(request, _CAISSE_TPL_MODAL if ajax else _CAISSE_TPL_PAGE, {
        'form': form, 'titre': 'Nouvelle caisse', 'edit': False,
    })


@login_required(login_url='login')
@permission_required('facturation.change_caisse', raise_exception=True)
def caisse_edit(request, pk):
    from .forms import CaisseForm
    caisse = get_object_or_404(Caisse, pk=pk)
    ajax = _est_ajax(request)
    if request.method == 'POST':
        form = CaisseForm(request.POST, instance=caisse)
        if form.is_valid():
            form.save()
            if ajax:
                return JsonResponse({'ok': True, 'message': 'Caisse « %s » modifiée.' % caisse.nom})
            messages.success(request, 'Caisse « %s » modifiée.' % caisse.nom)
            return redirect('facturation:caisses_list')
    else:
        form = CaisseForm(instance=caisse)
    return render(request, _CAISSE_TPL_MODAL if ajax else _CAISSE_TPL_PAGE, {
        'form': form, 'titre': 'Modifier la caisse', 'edit': True, 'objet': caisse,
    })


@login_required(login_url='login')
@permission_required('facturation.delete_caisse', raise_exception=True)
def caisse_delete(request, pk):
    caisse = get_object_or_404(Caisse, pk=pk)
    if request.method != 'POST':
        return redirect('facturation:caisses_list')
    nom = caisse.nom
    caisse.delete()
    if _est_ajax(request):
        return JsonResponse({'ok': True, 'message': 'Caisse « %s » supprimée.' % nom})
    messages.success(request, 'Caisse « %s » supprimée.' % nom)
    return redirect('facturation:caisses_list')
