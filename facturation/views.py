from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Facture, LigneFacture, Acte, Paiement
from .forms import FactureForm


@login_required(login_url='login')
def facturation_create(request):
    from patients.models import Patient, RendezVous

    patient_id = request.GET.get('patient_id')

    # Étape 1 : sélection du patient
    if not patient_id:
        patients = Patient.objects.filter(actif=True).order_by('nom', 'prenoms')
        return render(request, 'facturation/select_patient.html', {'patients': patients})

    patient = get_object_or_404(Patient, pk=patient_id)

    # Pré-remplissage depuis un RDV si fourni
    rdv_id = request.GET.get('rdv_id')
    rdv = None
    type_facture = 'consultation'
    if rdv_id:
        try:
            rdv = RendezVous.objects.get(pk=rdv_id)
            if rdv.type_rdv in dict(Facture.TYPE):
                type_facture = rdv.type_rdv
        except RendezVous.DoesNotExist:
            pass

    # Auto-création de la facture brouillon
    facture = Facture.objects.create(
        patient=patient,
        cree_par=request.user,
        type_facture=type_facture,
        statut='brouillon',
        montant_total=0,
    )

    # Ligne initiale si lié à un RDV
    if rdv:
        LigneFacture.objects.create(
            facture=facture,
            libelle=f"Consultation - {rdv.get_type_rdv_display()}",
            quantite=1,
            prix_unitaire=0,
            remise=0,
        )

    return redirect('facture_detail', pk=facture.pk)


@login_required(login_url='login')
def facture_detail(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    lignes = facture.lignes.all()
    paiements = facture.paiements.all()
    return render(request, 'facturation/detail.html', {
        'facture': facture,
        'lignes': lignes,
        'paiements': paiements,
        'next_url': request.GET.get('next', ''),
    })


@login_required(login_url='login')
def facture_edit(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    actes = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    lignes = list(facture.lignes.all())

    if request.method == 'POST':
        form = FactureForm(request.POST, instance=facture)
        if form.is_valid():
            facture = form.save(commit=False)

            total = 0
            lignes_data = []
            i = 0
            while f'ligne_libelle_{i}' in request.POST:
                libelle = request.POST.get(f'ligne_libelle_{i}', '').strip()
                acte_id = request.POST.get(f'ligne_acte_{i}') or None
                qte = _parse_float(request.POST.get(f'ligne_qte_{i}'), 1)
                prix = _parse_float(request.POST.get(f'ligne_prix_{i}'), 0)
                remise = _parse_float(request.POST.get(f'ligne_remise_{i}'), 0)

                if libelle or acte_id:
                    montant = qte * prix * (1 - remise / 100)
                    total += montant
                    lignes_data.append({
                        'libelle': libelle,
                        'acte_id': acte_id,
                        'quantite': qte,
                        'prix_unitaire': prix,
                        'remise': remise,
                    })
                i += 1

            facture.montant_total = round(total, 2)
            facture.save()

            facture.lignes.all().delete()
            for l in lignes_data:
                LigneFacture.objects.create(
                    facture=facture,
                    acte_id=l['acte_id'],
                    libelle=l['libelle'] or (
                        Acte.objects.get(pk=l['acte_id']).libelle if l['acte_id'] else '—'
                    ),
                    quantite=l['quantite'],
                    prix_unitaire=l['prix_unitaire'],
                    remise=l['remise'],
                )

            messages.success(request, f"Facture {facture.numero} mise à jour.")
            return redirect('facture_detail', pk=facture.pk)

        return render(request, 'facturation/edit.html', {
            'form': form,
            'facture': facture,
            'actes': actes,
            'lignes': lignes,
        })

    form = FactureForm(instance=facture)
    return render(request, 'facturation/edit.html', {
        'form': form,
        'facture': facture,
        'actes': actes,
        'lignes': lignes,
    })


@login_required(login_url='login')
@require_POST
def facture_valider(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if facture.statut == 'brouillon':
        facture.statut = 'emise'
        facture.save()
        messages.success(request, f"Facture {facture.numero} validée et émise.")
    return redirect('facture_detail', pk=facture.pk)


@login_required(login_url='login')
@require_POST
def facture_annuler(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    next_url = request.POST.get('next', '')
    if facture.statut == 'brouillon':
        facture.delete()
        messages.info(request, "Facture brouillon supprimée.")
        return redirect(next_url) if next_url else redirect('facturation_list')
    return redirect('facture_detail', pk=facture.pk)


def _parse_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
