from datetime import date
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator

import json

from consultations.models import (Consultation, LigneOrdonnance, Ordonnance,
                                  date_expiration_par_defaut)
from pharmacie.models import PHARMACIE_CENTRE_CODE
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

    if date_debut or date_fin:
        if date_debut:
            qs = qs.filter(date_emission__date__gte=date_debut)
        if date_fin:
            qs = qs.filter(date_emission__date__lte=date_fin)
    else:
        qs = qs.filter(date_emission__date=date.today())

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
        ).prefetch_related('lignes__produit'),
        pk=pk
    )
    patient = ordonnance.patient or (
        ordonnance.consultation.patient if ordonnance.consultation else None
    )
    # La colonne Stock affichait `produit.stock_actuel`, c'est-à-dire la réserve
    # centrale : un chiffre rassurant qui ne dit rien de ce que le comptoir a
    # sous la main. On pose sur chaque ligne la quantité de la pharmacie du
    # centre actif, celle qui décide si le patient repartira servi.
    from pharmacie.disponibilite import pharmacie_active
    from pharmacie.models import StockPharmacie

    lignes = list(ordonnance.lignes.select_related('produit'))
    quantites = dict(
        StockPharmacie.objects
        .filter(pharmacie=pharmacie_active(request),
                produit_id__in=[l.produit_id for l in lignes if l.produit_id])
        .values_list('produit_id', 'quantite')
    )
    for ligne in lignes:
        ligne.stock_pharma = quantites.get(ligne.produit_id)

    from facturation.models import Facture
    # `all_objects` : la facture est retrouvée par la clé étrangère de cette
    # ordonnance, qui porte déjà le cloisonnement par centre. Passer par le
    # manager filtré ferait dire « pas encore facturée » à une ordonnance qui
    # l'est, dès que le centre actif ne correspond pas.
    facture_existante = (Facture.all_objects.filter(ordonnance=ordonnance)
                         .exclude(statut='annulee').first())

    # L'état de chaque ligne, déduit et non stocké — rien à resynchroniser.
    #
    # L'écran ne savait dire que « facturée » ou « pas facturée », en bloc.
    # Or le patient qui annonce à la caisse avoir déjà tel médicament le voit
    # retirer de la facture : quatre lignes payées sur cinq, et l'ordonnance
    # entière s'affichait comme réglée. Le médecin ne pouvait pas voir ce que
    # son patient avait réellement pris.
    if facture_existante:
        payees = set(
            facture_existante.lignes
            .filter(ligne_ordonnance__isnull=False)
            .values_list('ligne_ordonnance_id', flat=True))
        for ligne in lignes:
            ligne.non_payee = ligne.pk not in payees

    return render(request, 'pharmacie/ordonnance/ordonnance_detail.html', {
        'ordonnance':       ordonnance,
        'lignes':           lignes,
        'patient':          patient,
        'today':            date.today(),
        'facture_existante': facture_existante,
    })


@login_required(login_url='login')
def ordonnance_print(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__patient', 'consultation__medecin'
        ).prefetch_related('lignes__produit'),
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
        if c.rendez_vous and c.rendez_vous.departement and c.rendez_vous.departement.code == 'GYN':
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
    from pharmacie.disponibilite import produits_de_la_pharmacie, pharmacie_active

    q = request.GET.get('q', '').strip()
    qs = produits_de_la_pharmacie(pharmacie_active(request))
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(dci__icontains=q) | Q(code__icontains=q))
    data = [
        {
            'id': p.pk,
            'designation': p.nom,
            'forme': p.get_forme_display() if p.forme else '',
            'dosage': p.dosage or '',
            'stock': float(p.stock_pharma),
            'rupture': p.stock_pharma <= 0,
        }
        for p in qs[:25]
    ]
    return JsonResponse({'results': data})


def _pharmacie_du_medecin(medecin):
    """Pharmacie (code `PHARMACIES_WALE`) dont dépend ce médecin prescripteur,
    déterminée par le(s) centre(s) rattachés à son compte utilisateur — ou
    None si indéterminable (médecin sans compte, ou affecté aux deux centres
    sans centre actif choisi). Dans ce cas les appelants retombent sur le
    stock cumulé des deux pharmacies plutôt que d'en exclure une."""
    if medecin is None or medecin.user_id is None:
        return None
    try:
        profile = medecin.user.profile
    except AttributeError:
        return None

    centre = profile.centre_actif
    if centre is None:
        centres = list(profile.centres.all()[:2])
        if len(centres) == 1:
            centre = centres[0]
    if centre is None:
        return None

    for pharmacie, centre_code in PHARMACIE_CENTRE_CODE.items():
        if centre_code == centre.code:
            return pharmacie
    return None


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

        lignes, problemes = _lignes_du_formulaire(request)
        if problemes or not lignes:
            _signaler_les_problemes(request, problemes)
            if not problemes:
                messages.error(request, MESSAGE_ORDONNANCE_VIDE)
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'consultation':      consultation,
                'patient':           consultation.patient,
                'medecin_preselect': medecin or consultation.medecin,
                'medecins':          medecins,
                'types':             types,
                'medicaments_dispo': _medicaments_dispo_json(request),
                'date_expiration_defaut': date_expiration_par_defaut(),
                'initial_lignes':    _lignes_a_reafficher(request),
            })

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            medecin=medecin,
            type_ordonnance=type_ord,
            date_expiration=date_exp,
            notes=notes,
        )
        _enregistrer_les_lignes(ordonnance, lignes)

        messages.success(request, f'Ordonnance {ordonnance.numero} créée avec succès.')
        return redirect('ordonnance_detail', pk=ordonnance.pk)

    medecin_preselect = consultation.medecin
    return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
        'consultation':      consultation,
        'patient':           consultation.patient,
        'medecin_preselect': medecin_preselect,
        'medecins':          medecins,
        'types':             types,
        'medicaments_dispo': _medicaments_dispo_json(request),
        'date_expiration_defaut': date_expiration_par_defaut(),
    })


def _lignes_du_formulaire(request):
    """Les lignes exploitables du formulaire, lues avant toute écriture.

    Les trois écrans de prescription créaient l'ordonnance d'abord, puis
    bouclaient sur les lignes. Un envoi sans médicament laissait donc une
    ordonnance vide enregistrée, que rien ne rattrapait ensuite : ni la
    pharmacie ni la facturation n'ont quoi que ce soit à en faire. On lit
    maintenant le formulaire d'abord, et la vue décide ensuite s'il y a lieu
    de créer quoi que ce soit.

    Une ligne est retenue dès qu'elle porte quelque chose — un produit, une
    désignation libre ou une posologie. Deux des trois écrans exigeaient une
    posologie : un médicament choisi dans la liste mais dont on avait oublié
    la posologie disparaissait sans un mot.

    Retourne `(lignes, problemes)` : les lignes prêtes à enregistrer, et un
    message en clair par ligne refusée.
    """
    med_ids    = request.POST.getlist('medicament[]')
    med_libres = request.POST.getlist('medicament_libre[]')
    posologies = request.POST.getlist('posologie[]')
    durees     = request.POST.getlist('duree[]')
    quantites  = request.POST.getlist('quantite[]')

    lignes, problemes = [], []
    for i in range(max(len(posologies), len(med_ids), len(med_libres))):
        med_id    = med_ids[i].strip()    if i < len(med_ids)    else ''
        med_libre = med_libres[i].strip() if i < len(med_libres) else ''
        posologie = posologies[i].strip() if i < len(posologies) else ''
        if not (med_id or med_libre or posologie):
            continue
        try:
            qte = max(1, int(quantites[i] if i < len(quantites) else 1))
        except (ValueError, TypeError):
            qte = 1

        souci = _probleme_de_la_ligne(med_id, med_libre, qte, request)
        if souci:
            problemes.append(souci)
            continue
        lignes.append({
            'produit_id': int(med_id),
            'posologie':  posologie,
            'duree':      durees[i].strip() if i < len(durees) else '',
            'quantite':   qte,
        })

    doublons = _produits_en_double(lignes)
    if doublons:
        problemes.extend(_message_de_doublon(pid, infos, request)
                         for pid, infos in doublons.items())
        lignes = []
    return lignes, problemes


def _produits_en_double(lignes):
    """Les produits qui reviennent sur plusieurs lignes, avec leur total.

    Chaque ligne était vérifiée seule : deux lignes de 6 sur un produit qui en
    a 10 passaient toutes les deux, alors que l'ordonnance en promettait 12.
    La facturation, elle, somme bien par produit au moment du paiement — le
    refus tombait donc plus tard, à la caisse.
    """
    compte = {}
    for ligne in lignes:
        pid = ligne['produit_id']
        nb, total = compte.get(pid, (0, 0))
        compte[pid] = (nb + 1, total + ligne['quantite'])
    return {pid: infos for pid, infos in compte.items() if infos[0] > 1}


def _message_de_doublon(produit_id, infos, request):
    """Nommer le produit en double, et dire ce que ça ferait au total."""
    from pharmacie.disponibilite import pharmacie_active, quantite_en_rayon

    nb, total = infos
    nom = Produit.objects.filter(pk=produit_id).values_list(
        'nom', flat=True).first() or 'Ce produit'
    dispo = quantite_en_rayon(produit_id, pharmacie_active(request))
    return (f"« {nom} » est sur {nb} lignes : regroupez-les en une seule "
            f"({total} demandé(s) au total, {dispo:.0f} en rayon)")


def _probleme_de_la_ligne(med_id, med_libre, quantite, request):
    """Ce qui empêche d'enregistrer cette ligne, en clair, ou None.

    Le garde-fou du serveur. L'écran signale déjà ces trois cas, mais un écran
    ne protège de rien : un onglet resté ouvert une heure, une URL forgée, ou
    simplement la dernière boîte partie entre l'affichage et l'enregistrement.

    Jusqu'ici une ligne que la pharmacie ne pouvait pas servir basculait
    silencieusement en texte libre, « à acheter en externe ». C'était contraire
    à la règle posée : une rupture n'est pas prescriptible, et l'ordonnance
    partait quand même — pour se bloquer plus tard à la caisse, patient devant
    le guichet.
    """
    from pharmacie.disponibilite import (TYPES_PROPOSES, pharmacie_active,
                                         quantite_en_rayon)

    designation = med_libre or 'ligne sans désignation'
    if not med_id:
        return (f"« {designation} » n'a pas été choisi dans la liste : "
                "seuls les produits de la pharmacie peuvent être prescrits")
    try:
        produit = Produit.objects.get(
            pk=int(med_id), type__in=TYPES_PROPOSES, actif=True)
    except (Produit.DoesNotExist, ValueError, TypeError):
        return f"« {designation} » n'existe plus au catalogue"

    dispo = quantite_en_rayon(produit.pk, pharmacie_active(request))
    if dispo <= 0:
        return f"« {produit.nom} » est en rupture à la pharmacie"
    if dispo < quantite:
        return (f"« {produit.nom} » : {quantite} demandé(s), "
                f"{dispo:.0f} en rayon")
    return None


def _lignes_a_reafficher(request):
    """Ce qui était saisi, remis dans le formulaire après un refus.

    Le gabarit relit ces clés pour préremplir ses lignes — les mêmes que celles
    d'un renouvellement. Sans ça, un envoi refusé pour une autre raison (patient
    ou prescripteur manquant) renvoyait une grille vide, et cinq médicaments
    saisis étaient à retaper.
    """
    med_ids    = request.POST.getlist('medicament[]')
    med_libres = request.POST.getlist('medicament_libre[]')
    posologies = request.POST.getlist('posologie[]')
    durees     = request.POST.getlist('duree[]')
    quantites  = request.POST.getlist('quantite[]')

    saisies = []
    for i in range(max(len(posologies), len(med_ids), len(med_libres))):
        med_id    = med_ids[i].strip()    if i < len(med_ids)    else ''
        med_libre = med_libres[i].strip() if i < len(med_libres) else ''
        posologie = posologies[i].strip() if i < len(posologies) else ''
        if not (med_id or med_libre or posologie):
            continue
        try:
            qte = max(1, int(quantites[i] if i < len(quantites) else 1))
        except (ValueError, TypeError):
            qte = 1
        saisies.append({
            'med_id':    med_id,
            'med_nom':   med_libre,
            'posologie': posologie,
            'duree':     durees[i].strip() if i < len(durees) else '',
            'quantite':  quantites[i] if i < len(quantites) else '1',
            # Le message dit ce qui ne va pas, ce drapeau dit *où* : sans lui,
            # un toast nommant un produit laisse chercher la ligne dans la
            # grille.
            'indisponible': bool(
                _probleme_de_la_ligne(med_id, med_libre, qte, request)),
        })

    # Un doublon ne se voit pas ligne par ligne : les deux lignes sont
    # correctes prises séparément, c'est leur rencontre qui pose problème. Les
    # deux se marquent, pour qu'on voie laquelle garder.
    vus = {}
    for saisie in saisies:
        vus.setdefault(saisie['med_id'], []).append(saisie)
    for med_id, groupe in vus.items():
        if med_id and len(groupe) > 1:
            for saisie in groupe:
                saisie['indisponible'] = True
    return saisies


MESSAGE_ORDONNANCE_VIDE = ("Aucun médicament saisi : l'ordonnance n'a pas été "
                           "enregistrée.")


def _enregistrer_les_lignes(ordonnance, lignes):
    """Écrit les lignes déjà validées par `_lignes_du_formulaire`."""
    LigneOrdonnance.objects.bulk_create([
        LigneOrdonnance(ordonnance=ordonnance, **ligne) for ligne in lignes])


def _signaler_les_problemes(request, problemes):
    """Un message par ligne refusée — le cycle de messages fait le toast."""
    for souci in problemes:
        messages.error(request, souci)


def _medicaments_dispo_data(request=None):
    """Ce que la pharmacie du centre actif a en rayon — médicaments et consommables.

    Cette fonction lisait `Produit` filtré sur la pharmacie du *médecin
    prescripteur*, et retombait sur la somme des deux pharmacies dès que ce
    rattachement échouait — c'est-à-dire toujours, aucun des 59 médecins du
    fichier n'ayant de compte utilisateur. Un prescripteur de Toumbokro se
    voyait donc proposer ce qui dort à Yamoussoukro, à quarante kilomètres.

    La pharmacie se déduit désormais du centre où l'on est connecté : c'est là
    que le patient sera servi. Les consommables entrent dans la liste, et les
    ruptures y restent en portant `rupture`, pour être grisées plutôt que
    cachées. La règle vit dans pharmacie.disponibilite, partagée avec la
    facturation.
    """
    from pharmacie.disponibilite import produits_pour_ecran

    return produits_pour_ecran(request)


def _medicaments_dispo_json(request=None):
    return json.dumps(_medicaments_dispo_data(request))


@login_required(login_url='login')
def medicaments_dispo_par_medecin(request):
    """Endpoint AJAX : liste des médicaments dispo (avec stock) pour la
    pharmacie du médecin passé en paramètre — appelé quand l'utilisateur
    change le médecin prescripteur sur le formulaire d'ordonnance, pour que
    la liste et le stock affichés restent ceux de la bonne pharmacie."""
    medecin_id = request.GET.get('medecin_id', '').strip()
    from pharmacie.disponibilite import pharmacie_active

    # `medecin_id` n'est plus lu : la pharmacie est celle du centre où l'on est
    # connecté, pas celle du prescripteur choisi dans la liste. Le paramètre
    # reste accepté pour que le JavaScript déjà en place continue d'appeler.
    pharmacie = pharmacie_active(request)
    return JsonResponse({'medicaments': _medicaments_dispo_data(request), 'pharmacie': pharmacie})


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
        patient = get_object_or_404(Patient.all_objects, pk=patient_id_get)
    if medecin_id_get and medecin_preselect is None:
        try:
            medecin_preselect = Medecin.objects.get(pk=int(medecin_id_get))
        except (Medecin.DoesNotExist, ValueError):
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
            patient = get_object_or_404(Patient.all_objects, pk=patient_id)
            consultation = None
        else:
            messages.error(request, 'Veuillez sélectionner un patient.')
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'types': types,
                'medecins': medecins,
                'medicaments_dispo': _medicaments_dispo_json(request),
                'date_expiration_defaut': date_expiration_par_defaut(),
                'initial_lignes': _lignes_a_reafficher(request),
            })

        if not medecin_id_post:
            messages.error(request, 'Veuillez sélectionner le médecin prescripteur.')
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'types': types,
                'medecins': medecins,
                'patient': patient,
                'consultation': consultation,
                'medecin_preselect': medecin_preselect,
                'medicaments_dispo': _medicaments_dispo_json(request),
                'date_expiration_defaut': date_expiration_par_defaut(),
                'initial_lignes': _lignes_a_reafficher(request),
            })

        medecin = None
        try:
            medecin = Medecin.objects.get(pk=int(medecin_id_post))
        except (Medecin.DoesNotExist, ValueError):
            pass

        lignes, problemes = _lignes_du_formulaire(request)
        if problemes or not lignes:
            _signaler_les_problemes(request, problemes)
            if not problemes:
                messages.error(request, MESSAGE_ORDONNANCE_VIDE)
            return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
                'consultation':      consultation,
                'patient':           patient,
                'medecin_preselect': medecin_preselect,
                'medecins':          medecins,
                'types':             types,
                'medicaments_dispo': _medicaments_dispo_json(request),
                'date_expiration_defaut': date_expiration_par_defaut(),
                'initial_lignes':    _lignes_a_reafficher(request),
            })

        ordonnance = Ordonnance.objects.create(
            consultation=consultation,
            patient=patient if not consultation else None,
            medecin=medecin,
            type_ordonnance=type_ord,
            date_expiration=date_exp,
            notes=notes,
        )
        _enregistrer_les_lignes(ordonnance, lignes)

        messages.success(request, f'Ordonnance {ordonnance.numero} créée avec succès.')
        return redirect('ordonnance_detail', pk=ordonnance.pk)

    return render(request, 'pharmacie/ordonnance/ordonnance_create.html', {
        'consultation':      consultation,
        'patient':           patient,
        'medecin_preselect': medecin_preselect,
        'medecins':          medecins,
        'types':             types,
        'medicaments_dispo': _medicaments_dispo_json(request),
        'date_expiration_defaut': date_expiration_par_defaut(),
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
