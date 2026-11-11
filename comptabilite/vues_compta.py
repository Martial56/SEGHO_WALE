"""Écrans de comptabilité générale : écritures, passage, OD, plan comptable,
correspondances (lot 3). Les règles vivent dans comptabilite/ecritures.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ecritures as moteur
from .models import Compte, Convention, Correspondance, Ecriture, Journal, Tiers

ZERO = Decimal('0')


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _date(valeur, defaut):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


@login_required(login_url='login')
def ecritures(request):
    """Liste des écritures, génération et passage (validation)."""
    _exiger(request.user, 'comptabilite.view_ecriture')
    peut_passer = request.user.has_perm('comptabilite.passer_ecritures')
    aujourdhui = timezone.localdate()

    if request.method == 'POST':
        if not peut_passer:
            raise PermissionDenied
        action = request.POST.get('action')
        if action == 'generer':
            debut = _date(request.POST.get('debut'), aujourdhui.replace(month=1, day=1))
            fin = _date(request.POST.get('fin'), aujourdhui)
            resultat = moteur.generer(debut, fin)
            messages.success(request, f"{resultat['crees']} écriture(s) générée(s) en brouillon "
                                      f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}.")
            for erreur in resultat['erreurs'][:10]:
                messages.warning(request, erreur)
            if len(resultat['erreurs']) > 10:
                messages.warning(request, f"… et {len(resultat['erreurs']) - 10} autre(s) pièce(s) en erreur.")
        elif action == 'valider':
            ids = request.POST.getlist('ecriture')
            choisies = list(Ecriture.objects.filter(pk__in=ids, statut='brouillon')
                            .select_related('journal', 'exercice'))
            try:
                n = moteur.valider(choisies, request.user)
            except moteur.ErreurCompta as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"{n} écriture(s) validée(s).")
        return redirect(request.get_full_path())

    debut = _date(request.GET.get('debut'), aujourdhui.replace(day=1))
    fin = _date(request.GET.get('fin'), aujourdhui)
    statut = request.GET.get('statut', 'brouillon')
    code_journal = request.GET.get('journal', '')
    qs = (Ecriture.objects.filter(date__range=[debut, fin])
          .select_related('journal', 'exercice').prefetch_related('lignes__compte')
          .annotate(total=Sum('lignes__debit')).order_by('date', 'journal__code', 'pk'))
    if statut in ('brouillon', 'validee'):
        qs = qs.filter(statut=statut)
    if code_journal:
        qs = qs.filter(journal__code=code_journal)
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'comptabilite/ecritures.html', {
        'page': page, 'debut': debut, 'fin': fin, 'statut': statut, 'code_journal': code_journal,
        'journaux': Journal.objects.filter(actif=True), 'peut_passer': peut_passer,
        'nb_brouillons': Ecriture.objects.filter(statut='brouillon').count(),
        'debut_exercice': aujourdhui.replace(month=1, day=1), 'aujourdhui': aujourdhui,
    })


@login_required(login_url='login')
def ecriture_detail(request, pk):
    _exiger(request.user, 'comptabilite.view_ecriture')
    ecriture = get_object_or_404(Ecriture.objects.select_related(
        'journal', 'exercice', 'cree_par', 'validee_par', 'contre_passation_de'), pk=pk)
    debit, credit = ecriture.totaux()
    return render(request, 'comptabilite/ecriture_detail.html', {
        'ecriture': ecriture, 'lignes': ecriture.lignes.select_related('compte', 'compte_tiers'),
        'debit': debit, 'credit': credit,
        'contre_passee_par': getattr(ecriture, 'contre_passee_par', None),
        'peut_passer': request.user.has_perm('comptabilite.passer_ecritures'),
    })


@login_required(login_url='login')
@require_POST
def ecriture_action(request, pk):
    _exiger(request.user, 'comptabilite.passer_ecritures')
    ecriture = get_object_or_404(Ecriture, pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'valider':
            moteur.valider([ecriture], request.user)
            messages.success(request, f"Écriture validée : {ecriture.reference}.")
        elif action == 'contre_passer':
            inverse = moteur.contre_passer(ecriture, request.user)
            messages.success(request, "Contre-passation préparée en brouillon : validez-la au passage des écritures.")
            return redirect('comptabilite:ecriture', pk=inverse.pk)
        elif action == 'supprimer':
            moteur.supprimer_brouillon(ecriture)
            messages.success(request, "Brouillon supprimé. S'il venait de la facturation, il sera "
                                      "recréé à la prochaine génération.")
            return redirect('comptabilite:ecritures')
    except moteur.ErreurCompta as e:
        messages.error(request, str(e))
    return redirect('comptabilite:ecriture', pk=ecriture.pk)


def _montant(valeur):
    try:
        m = Decimal(str(valeur or '0').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise moteur.ErreurCompta(f"Montant illisible : « {valeur} ».")
    if m < 0:
        raise moteur.ErreurCompta("Les montants sont positifs : choisissez la colonne débit ou crédit.")
    return m


@login_required(login_url='login')
def od_saisie(request):
    """Saisie d'une opération diverse (salaires, loyers, régularisations…)."""
    _exiger(request.user, 'comptabilite.add_ecriture')
    aujourdhui = timezone.localdate()
    lignes_saisies = []
    if request.method == 'POST':
        n = 0
        while f'compte_{n}' in request.POST:
            lignes_saisies.append({k: request.POST.get(f'{k}_{n}', '') for k in
                                   ('compte', 'libelle', 'tiers', 'debit', 'credit', 'convention')})
            n += 1
        try:
            jour = _date(request.POST.get('date'), None)
            if jour is None:
                raise moteur.ErreurCompta("Indiquez la date de l'opération.")
            libelle = request.POST.get('libelle', '').strip()
            if not libelle:
                raise moteur.ErreurCompta("Indiquez le libellé de l'opération.")
            journal_ = get_object_or_404(Journal, pk=request.POST.get('journal'))
            lignes = []
            for l in lignes_saisies:
                if not l['compte'] and not l['debit'] and not l['credit']:
                    continue
                c = Compte.objects.imputables().filter(numero=l['compte'].split(' ')[0].strip()).first()
                if c is None:
                    raise moteur.ErreurCompta(f"Compte inconnu : « {l['compte']} ».")
                d, cr = _montant(l['debit']), _montant(l['credit'])
                if d and cr:
                    raise moteur.ErreurCompta(f"Compte {c.numero} : une ligne est au débit ou au crédit, pas les deux.")
                convention = (Convention.objects.filter(pk=l['convention']).first()
                              if l['convention'].isdigit() else None)
                lignes.append((c, l['libelle'], d, cr, _tiers_saisi(l['tiers']), convention))
            ecriture = moteur.creer_ecriture(journal_, jour, libelle, lignes,
                                             piece=request.POST.get('piece', '').strip(), par=request.user)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Opération enregistrée en brouillon : validez-la au passage des écritures.")
            return redirect('comptabilite:ecriture', pk=ecriture.pk)
    while len(lignes_saisies) < 4:
        lignes_saisies.append({'compte': '', 'libelle': '', 'tiers': '', 'debit': '', 'credit': '',
                               'convention': ''})
    return render(request, 'comptabilite/od_saisie.html', {
        'journaux': Journal.objects.filter(actif=True).order_by('code'),
        'journal_defaut': Journal.objects.filter(code='OD').first(),
        'comptes': Compte.objects.imputables(),
        'lignes': lignes_saisies, 'aujourdhui': aujourdhui, 'post': request.POST,
        'conventions': Convention.objects.filter(statut='active'),
        'plan_tiers': Tiers.objects.filter(actif=True),
    })


def _tiers_saisi(texte):
    """« 40110002 CIE » (choisi dans la liste) → le compte tiers 40110002 ;
    un autre texte reste un simple nom."""
    texte = (texte or '').strip()
    tiers = Tiers.objects.filter(numero=texte.split(' ')[0].upper()).first() if texte else None
    return moteur.NomTiers(tiers.intitule, tiers) if tiers else texte


@login_required(login_url='login')
def plan_comptable(request, pk=None):
    from django import forms

    _exiger(request.user, 'comptabilite.view_compte')
    peut_modifier = request.user.has_perm('comptabilite.change_compte')

    class CompteForm(forms.ModelForm):
        class Meta:
            model = Compte
            fields = ['numero', 'intitule', 'nature', 'totalisation', 'actif', 'a_valider']

        def clean_numero(self):
            numero = self.cleaned_data['numero'].strip()
            if not numero.isdigit() or numero[0] == '0':
                raise forms.ValidationError("Un numéro de compte est fait de chiffres et commence par une classe de 1 à 9.")
            if self.instance.pk and self.instance.numero != numero and self.instance.lignes.exists():
                raise forms.ValidationError("Ce compte porte déjà des écritures : son numéro ne change plus.")
            return numero

        def clean_totalisation(self):
            from .plan_import import comptes_utilises
            total = self.cleaned_data['totalisation']
            if total and self.instance.pk and not self.instance.totalisation                     and self.instance.pk in comptes_utilises():
                raise forms.ValidationError("Ce compte est déjà mouvementé ou désigné ailleurs : "
                                            "il ne peut pas devenir un compte de totalisation.")
            return total

    objet = get_object_or_404(Compte, pk=pk) if pk else None
    form = CompteForm(request.POST or None, instance=objet)
    for champ in ('numero', 'intitule', 'nature'):
        form.fields[champ].widget.attrs['class'] = 'cpt-input'
    if request.method == 'POST':
        if not peut_modifier:
            raise PermissionDenied
        if form.is_valid():
            c = form.save()
            messages.success(request, f"Compte {c} enregistré.")
            return redirect('comptabilite:plan_comptable')
    q = request.GET.get('q', '').strip()
    comptes = Compte.objects.all()
    if q:
        comptes = comptes.filter(Q(numero__startswith=q) | Q(intitule__icontains=q))
    return render(request, 'comptabilite/plan_comptable.html', {
        'comptes': comptes, 'form': form, 'objet': objet, 'q': q, 'peut_modifier': peut_modifier,
        'nb_a_valider': Compte.objects.filter(a_valider=True).count(),
        'import_en_attente': CLE_IMPORT_PLAN in request.session,
    })


CLE_IMPORT_PLAN = 'comptabilite_import_plan'


@login_required(login_url='login')
def plan_comptable_export(request):
    from django.http import HttpResponse
    from .plan_import import classeur

    _exiger(request.user, 'comptabilite.view_compte')
    reponse = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reponse['Content-Disposition'] = f'attachment; filename="plan_comptable_{timezone.localdate():%Y%m%d}.xlsx"'
    classeur().save(reponse)
    return reponse


@login_required(login_url='login')
def plan_comptable_import(request):
    """Import en deux temps : le fichier est lu et l'aperçu montré ; rien
    n'est écrit avant « Confirmer l'import »."""
    from . import plan_import

    _exiger(request.user, 'comptabilite.change_compte')
    _exiger(request.user, 'comptabilite.add_compte')
    en_attente = request.session.get(CLE_IMPORT_PLAN)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'annuler':
            request.session.pop(CLE_IMPORT_PLAN, None)
            messages.info(request, "Import abandonné : le plan comptable n'a pas changé.")
            return redirect('comptabilite:plan_comptable')
        if action == 'confirmer' and en_attente:
            rapport = plan_import.appliquer(en_attente['comptes'])
            request.session.pop(CLE_IMPORT_PLAN, None)
            messages.success(request, f"Plan comptable importé : {len(rapport['nouveaux'])} compte(s) créé(s), "
                                      f"{len(rapport['modifies'])} mis à jour, {rapport['identiques']} inchangé(s).")
            if rapport['conflits']:
                messages.warning(request, f"{len(rapport['conflits'])} compte(s) en conflit laissé(s) tel(s) quel(s).")
            return redirect('comptabilite:plan_comptable')
        fichier = request.FILES.get('fichier')
        if not fichier:
            messages.error(request, "Choisissez le fichier Excel du plan comptable.")
            return redirect('comptabilite:plan_comptable')
        try:
            comptes, anomalies = plan_import.lire(fichier)
        except plan_import.ErreurImport as e:
            messages.error(request, str(e))
            return redirect('comptabilite:plan_comptable')
        request.session[CLE_IMPORT_PLAN] = {'fichier': fichier.name, 'comptes': comptes, 'anomalies': anomalies}
        return redirect('comptabilite:plan_comptable_import')
    if not en_attente:
        return redirect('comptabilite:plan_comptable')
    rapport = plan_import.analyser(en_attente['comptes'])
    return render(request, 'comptabilite/plan_import.html', {
        'fichier': en_attente['fichier'], 'anomalies': en_attente['anomalies'], 'rapport': rapport,
        'nb_fichier': len(en_attente['comptes']),
        'nb_totaux': sum(1 for c in en_attente['comptes'] if c['totalisation']),
        'natures': plan_import.NATURES,
        'absents_utilises': sum(1 for a in rapport['absents'] if a['utilise']),
    })


@login_required(login_url='login')
def correspondances(request):
    _exiger(request.user, 'comptabilite.view_correspondance')
    peut_modifier = request.user.has_perm('comptabilite.change_correspondance')
    from facturation.models import Caisse
    from patients.models import Assurance
    from .models import CorrespondanceTiers, Tiers

    # Le client du plan tiers de chaque caisse (ses patients) et de chaque assureur.
    designes = {c.cle: c for c in CorrespondanceTiers.objects.select_related('tiers')}
    clients_du_centre = ([(f'caisse:{c.code}', f'Caisse {c.nom}') for c in Caisse.objects.order_by('nom')]
                         + [(f'assurance:{a.code}', f'Assurance {a.nom}') for a in Assurance.objects.order_by('nom')])
    tiers_clients = list(Tiers.objects.filter(type='client', actif=True))

    lignes = list(Correspondance.objects.select_related('compte').order_by('cle'))
    # Une caisse sans compte n'est pas comptabilisée : l'expert-comptable crée
    # son sous-compte 571 dans le plan, puis on le désigne ici.
    designees = {corr.cle for corr in lignes}
    caisses_sans_compte = [c for c in Caisse.objects.order_by('nom') if f'caisse:{c.code}' not in designees]
    if request.method == 'POST':
        if not peut_modifier:
            raise PermissionDenied
        comptes = {c.pk: c for c in Compte.objects.imputables()}
        changes = 0
        for corr in lignes:
            choix = request.POST.get(f'corr_{corr.pk}')
            if choix and choix.isdigit() and int(choix) in comptes and int(choix) != corr.compte_id:
                corr.compte = comptes[int(choix)]
                corr.save(update_fields=['compte'])
                changes += 1
        for caisse in caisses_sans_compte:
            choix = request.POST.get(f'caisse_{caisse.pk}')
            if choix and choix.isdigit() and int(choix) in comptes:
                Correspondance.objects.create(cle=f'caisse:{caisse.code}', libelle=f'Caisse {caisse.nom}',
                                              compte=comptes[int(choix)])
                changes += 1
        clients = {str(t.pk): t for t in tiers_clients}
        for i, (cle, libelle) in enumerate(clients_du_centre):
            choix, actuel = request.POST.get(f'tiers_{i}', ''), designes.get(cle)
            if choix in clients and (actuel is None or str(actuel.tiers_id) != choix):
                CorrespondanceTiers.objects.update_or_create(cle=cle, defaults={'libelle': libelle,
                                                                                'tiers': clients[choix]})
                changes += 1
            elif f'tiers_{i}' in request.POST and not choix and actuel:
                actuel.delete()
                changes += 1
        messages.success(request, f"{changes} correspondance(s) modifiée(s).")
        return redirect('comptabilite:correspondances')
    return render(request, 'comptabilite/correspondances.html', {
        'lignes': lignes, 'comptes': Compte.objects.imputables(), 'peut_modifier': peut_modifier,
        'caisses_sans_compte': caisses_sans_compte,
        'clients_du_centre': [(cle, libelle, designes.get(cle)) for cle, libelle in clients_du_centre],
        'tiers_clients': tiers_clients,
        'comptes_caisse': Compte.objects.imputables().filter(numero__startswith='57'),
    })


@login_required(login_url='login')
def journaux(request):
    """Codes journaux de l'expert-comptable, avec le compte de trésorerie de
    chacun : c'est lui qui décide du journal d'une écriture de trésorerie."""
    from django.db.models import Count
    _exiger(request.user, 'comptabilite.view_journal')
    return render(request, 'comptabilite/journaux.html', {
        'journaux': Journal.objects.select_related('compte_tresorerie')
                                   .annotate(nb=Count('ecritures')).order_by('code'),
    })


@login_required(login_url='login')
def plan_tiers(request, pk=None):
    """Plan tiers de l'expert-comptable : fournisseurs, clients, salariés,
    bailleurs et projets, chacun rattaché à son compte collectif."""
    from django import forms
    from django.db.models import Count
    from .models import Tiers

    _exiger(request.user, 'comptabilite.view_tiers')
    peut_modifier = request.user.has_perm('comptabilite.change_tiers')

    class TiersForm(forms.ModelForm):
        class Meta:
            model = Tiers
            fields = ['numero', 'intitule', 'type', 'compte_collectif', 'ville', 'actif']

        def clean_numero(self):
            numero = self.cleaned_data['numero'].strip().upper()
            if not numero.replace(' ', '').isalnum():
                raise forms.ValidationError("Un numéro de tiers est fait de lettres et de chiffres.")
            return numero

    objet = get_object_or_404(Tiers, pk=pk) if pk else None
    form = TiersForm(request.POST or None, instance=objet)
    form.fields['compte_collectif'].queryset = Compte.objects.imputables().filter(numero__startswith='4')
    for champ in ('numero', 'intitule', 'type', 'compte_collectif', 'ville'):
        form.fields[champ].widget.attrs['class'] = 'cpt-input'
    if request.method == 'POST':
        if not peut_modifier:
            raise PermissionDenied
        if form.is_valid():
            t = form.save()
            messages.success(request, f"Tiers {t} enregistré.")
            return redirect('comptabilite:plan_tiers')
    q = request.GET.get('q', '').strip()
    type_ = request.GET.get('type', '')
    tiers = Tiers.objects.select_related('compte_collectif')
    if type_ in dict(Tiers.TYPE):
        tiers = tiers.filter(type=type_)
    if q:
        tiers = tiers.filter(Q(numero__istartswith=q) | Q(intitule__icontains=q))
    comptes_type = dict(Tiers.objects.values_list('type').annotate(n=Count('pk')))
    return render(request, 'comptabilite/plan_tiers.html', {
        'tiers': tiers, 'form': form, 'objet': objet, 'q': q, 'type': type_, 'peut_modifier': peut_modifier,
        'types': [(cle, libelle, comptes_type.get(cle, 0)) for cle, libelle in Tiers.TYPE],
        'nb_total': sum(comptes_type.values()),
        'nb_sans_collectif': Tiers.objects.filter(compte_collectif__isnull=True).count(),
        'import_en_attente': CLE_IMPORT_TIERS in request.session,
    })


CLE_IMPORT_TIERS = 'comptabilite_import_tiers'


@login_required(login_url='login')
def plan_tiers_export(request):
    from django.http import HttpResponse
    from .tiers_import import classeur

    _exiger(request.user, 'comptabilite.view_tiers')
    reponse = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    reponse['Content-Disposition'] = f'attachment; filename="plan_tiers_{timezone.localdate():%Y%m%d}.xlsx"'
    classeur().save(reponse)
    return reponse


@login_required(login_url='login')
def plan_tiers_import(request):
    """Import en deux temps, comme le plan comptable : aperçu, puis
    « Confirmer l'import »."""
    from . import tiers_import

    _exiger(request.user, 'comptabilite.change_tiers')
    _exiger(request.user, 'comptabilite.add_tiers')
    en_attente = request.session.get(CLE_IMPORT_TIERS)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'annuler':
            request.session.pop(CLE_IMPORT_TIERS, None)
            messages.info(request, "Import abandonné : le plan tiers n'a pas changé.")
            return redirect('comptabilite:plan_tiers')
        if action == 'confirmer' and en_attente:
            rapport = tiers_import.appliquer(en_attente['tiers'])
            request.session.pop(CLE_IMPORT_TIERS, None)
            messages.success(request, f"Plan tiers importé : {len(rapport['nouveaux'])} tiers créé(s), "
                                      f"{len(rapport['modifies'])} mis à jour, {rapport['identiques']} inchangé(s).")
            return redirect('comptabilite:plan_tiers')
        fichier = request.FILES.get('fichier')
        if not fichier:
            messages.error(request, "Choisissez le fichier Excel du plan tiers.")
            return redirect('comptabilite:plan_tiers')
        try:
            tiers, anomalies = tiers_import.lire(fichier)
        except tiers_import.ErreurImport as e:
            messages.error(request, str(e))
            return redirect('comptabilite:plan_tiers')
        request.session[CLE_IMPORT_TIERS] = {'fichier': fichier.name, 'tiers': tiers, 'anomalies': anomalies}
        return redirect('comptabilite:plan_tiers_import')
    if not en_attente:
        return redirect('comptabilite:plan_tiers')
    return render(request, 'comptabilite/tiers_import.html', {
        'fichier': en_attente['fichier'], 'anomalies': en_attente['anomalies'],
        'rapport': tiers_import.analyser(en_attente['tiers']), 'nb_fichier': len(en_attente['tiers']),
        'types': tiers_import.TYPES,
    })


@login_required(login_url='login')
def lettrage(request):
    """Lettrage d'un compte de tiers : les lignes validées d'un compte (et
    d'un compte tiers), à cocher pour les lettrer ensemble ; lettrage
    automatique des documents soldés ; délettrage d'une lettre."""
    from . import lettrage as regles_lettrage

    _exiger(request.user, 'comptabilite.view_ecriture')
    peut_lettrer = request.user.has_perm('comptabilite.passer_ecritures')
    numero = request.GET.get('compte', '').strip()
    numero_tiers = request.GET.get('tiers', '').strip().split(' ')[0].upper()
    toutes = request.GET.get('toutes') == '1'
    compte = Compte.objects.filter(numero=numero, numero__startswith='4').first() if numero else None
    tiers = Tiers.objects.filter(numero=numero_tiers).first() if numero_tiers else None
    if tiers and compte is None and tiers.compte_collectif_id:
        compte = tiers.compte_collectif

    if request.method == 'POST':
        if not peut_lettrer:
            raise PermissionDenied
        action = request.POST.get('action')
        try:
            if action == 'lettrer':
                ids = [int(i) for i in request.POST.getlist('ligne') if i.isdigit()]
                lettre = regles_lettrage.lettrer(regles_lettrage.lettrables().filter(pk__in=ids))
                messages.success(request, f"{len(ids)} lignes lettrées « {lettre} ».")
            elif action == 'delettrer':
                n = regles_lettrage.delettrer(compte.pk if compte else None, tiers.pk if tiers else None,
                                              request.POST.get('lettre', ''))
                messages.success(request, f"Lettre « {request.POST.get('lettre')} » retirée de {n} ligne(s).")
            elif action == 'auto':
                n = regles_lettrage.lettrage_automatique(compte, tiers)
                messages.success(request, f"Lettrage automatique : {n} document(s) soldé(s) lettré(s).")
        except regles_lettrage.ErreurLettrage as e:
            messages.error(request, str(e))
        return redirect(request.get_full_path())

    lignes, totaux = [], {}
    if compte:
        qs = (regles_lettrage.lettrables().filter(compte=compte, compte_tiers=tiers)
              .select_related('ecriture__journal').order_by('ecriture__date', 'pk'))
        if not toutes:
            qs = qs.filter(lettre='')
        lignes = list(qs[:1000])
        reste = regles_lettrage.lettrables().filter(compte=compte, compte_tiers=tiers, lettre='') \
            .aggregate(d=Sum('debit'), c=Sum('credit'))
        totaux = {'debit': reste['d'] or ZERO, 'credit': reste['c'] or ZERO}
        totaux['solde'] = totaux['debit'] - totaux['credit']
    return render(request, 'comptabilite/lettrage.html', {
        'compte': compte, 'tiers': tiers, 'toutes': toutes, 'lignes': lignes, 'totaux': totaux,
        'peut_lettrer': peut_lettrer, 'numero': numero, 'numero_tiers': numero_tiers,
        'comptes': Compte.objects.imputables().filter(numero__startswith='4'),
        'plan_tiers': Tiers.objects.filter(actif=True),
    })


@login_required(login_url='login')
def cloture_journaux(request):
    """Clôture des journaux : une grille journaux × mois de l'exercice ;
    un clic clôture (ou rouvre) un mois, un bouton clôture tout jusqu'à un mois."""
    from . import cloture_journaux as regles_cloture
    from .models import Exercice

    _exiger(request.user, 'comptabilite.view_exercice')
    peut_cloturer = request.user.has_perm('comptabilite.cloturer_exercice')
    exercice = (Exercice.objects.filter(pk=request.GET.get('exercice')).first() if request.GET.get('exercice', '').isdigit()
                else None) or Exercice.objects.filter(date_debut__lte=timezone.localdate(),
                                                      date_fin__gte=timezone.localdate()).first() \
        or Exercice.objects.first()
    if request.method == 'POST':
        if not peut_cloturer:
            raise PermissionDenied
        action = request.POST.get('action')
        mois = _date(request.POST.get('mois'), None)
        journal_ = Journal.objects.filter(pk=request.POST.get('journal') or None).first()
        try:
            if mois is None:
                raise moteur.ErreurCompta("Mois illisible.")
            if action == 'cloturer' and journal_:
                regles_cloture.cloturer(journal_, mois, request.user)
                messages.success(request, f"Journal {journal_.code} clôturé pour {mois:%m/%Y}.")
            elif action == 'rouvrir' and journal_:
                regles_cloture.rouvrir(journal_, mois)
                messages.success(request, f"Journal {journal_.code} rouvert pour {mois:%m/%Y}.")
            elif action == 'cloturer_tout':
                faites, refus = regles_cloture.cloturer_jusqu_a(mois, request.user)
                messages.success(request, f"{faites} période(s) clôturée(s) jusqu'à {mois:%m/%Y}.")
                for r in refus[:10]:
                    messages.warning(request, r)
                if len(refus) > 10:
                    messages.warning(request, f"… et {len(refus) - 10} autre(s) période(s) non clôturée(s).")
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
        return redirect(request.get_full_path())
    mois, lignes = regles_cloture.grille(exercice) if exercice else ([], [])
    return render(request, 'comptabilite/cloture_journaux.html', {
        'exercice': exercice, 'exercices': Exercice.objects.all(), 'mois': mois, 'lignes': lignes,
        'peut_cloturer': peut_cloturer and exercice is not None and exercice.statut == 'ouvert',
        'mois_passes': [m for m in mois if m <= timezone.localdate()],
    })
