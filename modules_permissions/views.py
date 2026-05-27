from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from .models import Module, GroupModule, UserModuleOverride, get_user_modules


# ─── Helpers ────────────────────────────────────────────────────────────────

def _require_staff(request):
    """Retourne True si ok, redirige sinon."""
    return request.user.is_authenticated and request.user.is_staff


# ─── Dashboard ──────────────────────────────────────────────────────────────

@login_required
def parametres_dashboard(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    nb_groupes = Group.objects.count()
    nb_comptes = User.objects.count()
    nb_modules_actifs = Module.objects.filter(is_active=True).count()

    groupes = Group.objects.prefetch_related(
        Prefetch('group_modules', queryset=GroupModule.objects.select_related('module').order_by('module__order'))
    ).annotate(member_count=Count('user')).order_by('name')

    groupes_with_modules = []
    for g in groupes:
        gms = g.group_modules.all()
        groupes_with_modules.append({
            'group': g,
            'modules': [gm.module for gm in gms],
            'member_count': g.member_count,
        })

    return render(request, 'parametres/dashboard.html', {
        'nb_groupes': nb_groupes,
        'nb_comptes': nb_comptes,
        'nb_modules_actifs': nb_modules_actifs,
        'groupes_with_modules': groupes_with_modules,
    })


# ─── Groupes ────────────────────────────────────────────────────────────────

@login_required
def groupes_list(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    groupes = Group.objects.prefetch_related(
        Prefetch('group_modules', queryset=GroupModule.objects.select_related('module').order_by('module__order'))
    ).annotate(user_count=Count('user')).order_by('name')

    groupes_data = []
    for g in groupes:
        groupes_data.append({
            'pk': g.pk,
            'name': g.name,
            'user_count': g.user_count,
            'modules': [gm.module for gm in g.group_modules.all()],
        })

    return render(request, 'parametres/groupes_list.html', {
        'groupes': groupes_data,
    })


@login_required
def groupe_create(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    modules = Module.objects.filter(is_active=True).order_by('order', 'name')
    errors = []

    if request.method == 'POST':
        group_name = request.POST.get('group_name', '').strip()
        selected_module_ids = request.POST.getlist('modules')

        if not group_name:
            errors.append("Le nom du groupe est obligatoire.")
        elif Group.objects.filter(name=group_name).exists():
            errors.append(f"Un groupe nommé « {group_name} » existe déjà.")

        if not errors:
            group = Group.objects.create(name=group_name)
            for mid in selected_module_ids:
                try:
                    mod = Module.objects.get(pk=int(mid))
                    GroupModule.objects.get_or_create(group=group, module=mod)
                except (Module.DoesNotExist, ValueError):
                    pass
            messages.success(request, f"Groupe « {group_name} » créé avec succès.")
            return redirect('parametres:groupes')

        return render(request, 'parametres/groupe_form.html', {
            'modules': modules,
            'selected_modules': [int(m) for m in selected_module_ids if m.isdigit()],
            'group_name': group_name,
            'errors': errors,
        })

    return render(request, 'parametres/groupe_form.html', {
        'modules': modules,
        'selected_modules': [],
        'group_name': '',
        'errors': [],
    })


@login_required
def groupe_edit(request, group_id):
    if not request.user.is_staff:
        return redirect('dashboard')

    group = get_object_or_404(Group, pk=group_id)
    modules = Module.objects.filter(is_active=True).order_by('order', 'name')
    errors = []

    current_module_ids = list(
        GroupModule.objects.filter(group=group).values_list('module_id', flat=True)
    )

    if request.method == 'POST':
        group_name = request.POST.get('group_name', '').strip()
        selected_module_ids = request.POST.getlist('modules')

        if not group_name:
            errors.append("Le nom du groupe est obligatoire.")
        elif Group.objects.filter(name=group_name).exclude(pk=group_id).exists():
            errors.append(f"Un groupe nommé « {group_name} » existe déjà.")

        if not errors:
            group.name = group_name
            group.save()

            new_ids = set()
            for mid in selected_module_ids:
                try:
                    new_ids.add(int(mid))
                except ValueError:
                    pass

            # Supprimer les modules non sélectionnés
            GroupModule.objects.filter(group=group).exclude(module_id__in=new_ids).delete()
            # Ajouter les nouveaux
            for mid in new_ids:
                try:
                    mod = Module.objects.get(pk=mid)
                    GroupModule.objects.get_or_create(group=group, module=mod)
                except Module.DoesNotExist:
                    pass

            messages.success(request, f"Groupe « {group_name} » mis à jour.")
            return redirect('parametres:groupes')

        return render(request, 'parametres/groupe_form.html', {
            'group': group,
            'modules': modules,
            'selected_modules': [int(m) for m in selected_module_ids if m.isdigit()],
            'group_name': group_name,
            'errors': errors,
        })

    return render(request, 'parametres/groupe_form.html', {
        'group': group,
        'modules': modules,
        'selected_modules': current_module_ids,
        'group_name': group.name,
        'errors': [],
    })


@login_required
def groupe_delete(request, group_id):
    if not request.user.is_superuser:
        messages.error(request, "Seul un superuser peut supprimer un groupe.")
        return redirect('parametres:groupes')

    if request.method == 'POST':
        group = get_object_or_404(Group, pk=group_id)
        name = group.name
        group.delete()
        messages.success(request, f"Groupe « {name} » supprimé.")

    return redirect('parametres:groupes')


# ─── Comptes ────────────────────────────────────────────────────────────────

@login_required
def comptes_list(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    users = User.objects.prefetch_related('groups').select_related('employe_profile').order_by('username')

    total = users.count()
    total_actifs = users.filter(is_active=True).count()
    total_admins = users.filter(is_staff=True).count()
    total_sans_employe = sum(1 for u in users if not hasattr(u, 'employe_profile') or u.employe_profile is None)

    # Enrichir chaque user avec son employe
    users_list = []
    for u in users:
        try:
            emp = u.employe_profile
        except Exception:
            emp = None
        users_list.append({
            'pk': u.pk,
            'username': u.username,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'email': u.email,
            'is_active': u.is_active,
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
            'groups': u.groups.all(),
            'employe': emp,
            # Pour accès direct dans template
            'get_full_name': u.get_full_name(),
        })

    return render(request, 'parametres/comptes_list.html', {
        'users': users,
        'total': total,
        'total_actifs': total_actifs,
        'total_admins': total_admins,
        'total_sans_employe': total_sans_employe,
    })


@login_required
def compte_create(request):
    if not request.user.is_staff:
        return redirect('dashboard')

    all_groups = Group.objects.annotate(
        module_count=Count('group_modules')
    ).order_by('name')
    errors = []
    form_data = {}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        is_staff = request.POST.get('is_staff') == 'on'
        group_ids = request.POST.getlist('groups')

        form_data = {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'groups': group_ids,
        }

        if not username:
            errors.append("L'identifiant est obligatoire.")
        elif User.objects.filter(username=username).exists():
            errors.append(f"L'identifiant « {username} » est déjà utilisé.")

        if not password1:
            errors.append("Le mot de passe est obligatoire.")
        elif len(password1) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères.")
        elif password1 != password2:
            errors.append("Les mots de passe ne correspondent pas.")

        if not errors:
            user = User.objects.create_user(
                username=username,
                password=password1,
                first_name=first_name,
                last_name=last_name,
                email=email,
            )
            user.is_active = is_active
            user.is_staff = is_staff
            user.save()

            groups = Group.objects.filter(pk__in=[int(g) for g in group_ids if g.isdigit()])
            user.groups.set(groups)

            messages.success(request, f"Compte « {username} » créé avec succès.")
            return redirect('parametres:comptes')

        return render(request, 'parametres/compte_form.html', {
            'all_groups': all_groups,
            'errors': errors,
            'form_data': form_data,
        })

    return render(request, 'parametres/compte_form.html', {
        'all_groups': all_groups,
        'errors': [],
        'form_data': {},
    })


@login_required
def compte_edit(request, user_id):
    if not request.user.is_staff:
        return redirect('dashboard')

    user_obj = get_object_or_404(User, pk=user_id)
    all_groups = Group.objects.annotate(
        module_count=Count('group_modules')
    ).order_by('name')
    user_groups = list(user_obj.groups.values_list('pk', flat=True))
    user_modules = get_user_modules(user_obj)
    errors = []

    if request.method == 'POST':
        action = request.POST.get('action', 'profil')

        if action == 'profil':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            group_ids = request.POST.getlist('groups')

            user_obj.first_name = first_name
            user_obj.last_name = last_name
            user_obj.email = email
            user_obj.save()

            groups = Group.objects.filter(pk__in=[int(g) for g in group_ids if g.isdigit()])
            user_obj.groups.set(groups)
            user_groups = list(user_obj.groups.values_list('pk', flat=True))

            messages.success(request, "Profil mis à jour.")
            return redirect(f"{request.path}?tab=profil")

        elif action == 'acces':
            if not user_obj.is_superuser:
                user_obj.is_active = request.POST.get('is_active') == 'on'
                user_obj.is_staff = request.POST.get('is_staff') == 'on'
                user_obj.save()
                messages.success(request, "Statut d'accès mis à jour.")
            else:
                messages.warning(request, "Impossible de modifier le statut d'un superuser.")
            return redirect(f"{request.path}?tab=acces")

        elif action == 'password':
            password1 = request.POST.get('password1', '')
            password2 = request.POST.get('password2', '')

            if not password1:
                errors.append("Le nouveau mot de passe est obligatoire.")
            elif len(password1) < 8:
                errors.append("Le mot de passe doit contenir au moins 8 caractères.")
            elif password1 != password2:
                errors.append("Les mots de passe ne correspondent pas.")

            if not errors:
                user_obj.set_password(password1)
                user_obj.save()
                messages.success(request, "Mot de passe modifié avec succès.")
                return redirect(f"{request.path}?tab=password")

    return render(request, 'parametres/compte_form.html', {
        'user_obj': user_obj,
        'all_groups': all_groups,
        'user_groups': user_groups,
        'user_modules': user_modules,
        'errors': errors,
    })


@login_required
def compte_toggle_active(request, user_id):
    if not request.user.is_staff:
        return redirect('dashboard')

    if request.method == 'POST':
        user_obj = get_object_or_404(User, pk=user_id)
        if user_obj.is_superuser:
            messages.error(request, "Impossible de modifier le statut d'un superuser.")
        else:
            user_obj.is_active = not user_obj.is_active
            user_obj.save()
            status = "activé" if user_obj.is_active else "désactivé"
            messages.success(request, f"Compte « {user_obj.username} » {status}.")

    return redirect('parametres:comptes')
