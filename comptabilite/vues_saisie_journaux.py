"""Écran « Saisie des journaux » (Sage 100) : la liste journal × mois, puis le
journal d'un mois, où l'on consulte et saisit. Les règles vivent dans
comptabilite/saisie_journaux.py et comptabilite/ecritures.py."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import ecritures as moteur
from . import saisie_journaux as regles
from .models import Compte, Convention, Exercice, Journal, Tiers
from .vues_compta import _date, _exiger, lignes_ecriture, lignes_postees, lignes_vides


@login_required(login_url='login')
def saisie_journaux(request):
    _exiger(request.user, 'comptabilite.view_ecriture')
    aujourdhui = timezone.localdate()
    exercice = (Exercice.objects.filter(pk=request.GET.get('exercice')).first()
                if request.GET.get('exercice', '').isdigit() else None) \
        or Exercice.objects.filter(date_debut__lte=aujourdhui, date_fin__gte=aujourdhui).first() \
        or Exercice.objects.order_by('-date_debut').first()
    code = request.GET.get('journal', '')
    mouvementes = request.GET.get('mouvementes') == '1'
    filtre = request.GET.get('etat', '')
    lignes = regles.periodes(exercice, code or None, mouvementes, filtre) if exercice else []
    return render(request, 'comptabilite/saisie_journaux.html', {
        'exercice': exercice, 'exercices': Exercice.objects.order_by('-date_debut'),
        'journaux': Journal.objects.filter(actif=True).order_by('code'), 'code': code,
        'mouvementes': mouvementes, 'lignes': lignes, 'etats': regles.ETATS,
        'filtre': filtre, 'filtres': [(k, v[0]) for k, v in regles.FILTRES.items()],
        'mois_courant': aujourdhui.replace(day=1),
    })


@login_required(login_url='login')
def journal_mois(request, pk, annee, mois):
    """Le journal d'un mois : ses écritures, ses totaux, et la saisie."""
    _exiger(request.user, 'comptabilite.view_ecriture')
    journal = get_object_or_404(Journal, pk=pk)
    try:
        debut = date(annee, mois, 1)
    except ValueError:
        raise Http404
    fin = regles.fin_du_mois(debut)
    exercice = Exercice.objects.filter(date_debut__lte=debut, date_fin__gte=debut).first()
    peut_passer = request.user.has_perm('comptabilite.passer_ecritures')
    aujourdhui = timezone.localdate()
    lignes_saisies, post = [], {}

    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.add_ecriture')
        post = request.POST
        lignes_saisies = lignes_postees(request.POST)
        try:
            # Comme Sage : on tape le jour, le mois est celui du journal.
            numero_jour = request.POST.get('jour', '').strip()
            if numero_jour.isdigit():
                jour = debut.replace(day=int(numero_jour)) if 1 <= int(numero_jour) <= fin.day else None
            else:
                jour = _date(request.POST.get('date'), None)
            if jour is None or not debut <= jour <= fin:
                raise moteur.ErreurCompta(f"La date doit tomber en {debut:%m/%Y}, le mois de ce journal.")
            libelle = request.POST.get('libelle', '').strip()
            if not libelle:
                raise moteur.ErreurCompta("Indiquez le libellé de l'écriture.")
            ecriture = moteur.creer_ecriture(journal, jour, libelle, lignes_ecriture(lignes_saisies),
                                             piece=request.POST.get('piece', '').strip(), par=request.user,
                                             numero_facture=request.POST.get('numero_facture', '').strip())
            if peut_passer and request.POST.get('action') == 'valider':
                moteur.valider([ecriture], request.user)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"Écriture « {ecriture.libelle} » enregistrée"
                                      + (f" et validée : {ecriture.reference}." if ecriture.statut == 'validee'
                                         else " en brouillon."))
            return redirect(f"{request.path}#e{ecriture.pk}")

    contenu = regles.journal_du_mois(journal, debut)
    saisie_ouverte = (contenu['cloture'] is None and exercice is not None and exercice.statut == 'ouvert'
                      and journal.actif and request.user.has_perm('comptabilite.add_ecriture'))
    lignes_saisies += lignes_vides(max(0, 2 - len(lignes_saisies)))
    precedent, suivant = regles.mois_voisin(debut, -1), regles.mois_voisin(debut, 1)
    return render(request, 'comptabilite/journal_mois.html', {
        'journal': journal, 'mois': debut, 'fin': fin, 'exercice': exercice, **contenu,
        'precedent': precedent, 'suivant': suivant,
        'saisie_ouverte': saisie_ouverte, 'peut_passer': peut_passer, 'post': post,
        'date_defaut': min(max(aujourdhui, debut), fin),
        'lignes': lignes_saisies, 'comptes': Compte.objects.imputables(),
        'plan_tiers': Tiers.objects.filter(actif=True), 'conventions': Convention.objects.filter(statut='active'),
    })
