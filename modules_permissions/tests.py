import json

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, Group, User
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from modules_permissions.admin import CustomUserAdmin, GroupAdminWithModules, ModuleAdmin
from modules_permissions.context_processors import user_modules
from modules_permissions.models import GroupModule, Module, UserModuleOverride, get_user_modules


# ─── Helpers de création ───────────────────────────────────────────────────────

def _module(code, **kwargs):
    defaults = {'name': kwargs.pop('name', code.title())}
    defaults.update(kwargs)
    module, _ = Module.objects.get_or_create(code=code, defaults=defaults)
    return module


def _group(name):
    group, _ = Group.objects.get_or_create(name=name)
    return group


def _user(username, **kwargs):
    return User.objects.create_user(username=username, password='x', **kwargs)


# ─── Tests modèle Module ────────────────────────────────────────────────────────

class TestModuleModel(TestCase):

    def test_str_contient_icone_et_nom(self):
        module = _module('zt_str', name='Module Test', icon='🔧')
        self.assertEqual(str(module), '🔧 Module Test')

    def test_code_doit_etre_unique(self):
        _module('zt_unique_code')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Module.objects.create(code='zt_unique_code', name='Doublon')

    def test_valeurs_par_defaut(self):
        module = Module.objects.create(code='zt_defaults', name='Défauts')
        self.assertEqual(module.icon, '📦', "L'icône par défaut devrait être 📦")
        self.assertTrue(module.is_active, "Un module devrait être actif par défaut")
        self.assertEqual(module.order, 0, "L'ordre par défaut devrait être 0")
        self.assertEqual(module.url_name, '')
        self.assertEqual(module.description, '')

    def test_ordering_meta_tri_par_order_puis_nom(self):
        _module('zt_order_b', name='B Module', order=5)
        _module('zt_order_a', name='A Module', order=5)
        _module('zt_order_c', name='C Module', order=1)
        codes = list(
            Module.objects.filter(code__in=['zt_order_a', 'zt_order_b', 'zt_order_c'])
            .values_list('code', flat=True)
        )
        self.assertEqual(codes, ['zt_order_c', 'zt_order_a', 'zt_order_b'],
                          "Le tri par défaut doit se faire par order puis par name")


# ─── Tests modèle GroupModule ───────────────────────────────────────────────────

class TestGroupModuleModel(TestCase):

    def test_str_format(self):
        group = _group('zt_gm_group')
        module = _module('zt_gm_module', name='Module GM')
        gm = GroupModule.objects.create(group=group, module=module)
        self.assertEqual(str(gm), 'zt_gm_group → Module GM')

    def test_unicite_couple_group_module(self):
        group = _group('zt_gm_unique_group')
        module = _module('zt_gm_unique_module')
        GroupModule.objects.create(group=group, module=module)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GroupModule.objects.create(group=group, module=module)


# ─── Tests modèle UserModuleOverride ────────────────────────────────────────────

class TestUserModuleOverrideModel(TestCase):

    def test_str_format(self):
        user = _user('zt_umo_user')
        module = _module('zt_umo_module', name='Module UMO')
        override = UserModuleOverride.objects.create(
            user=user, module=module, override_type='grant'
        )
        self.assertEqual(str(override), 'zt_umo_user — grant — Module UMO')

    def test_unicite_couple_user_module(self):
        user = _user('zt_umo_unique_user')
        module = _module('zt_umo_unique_module')
        UserModuleOverride.objects.create(user=user, module=module)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserModuleOverride.objects.create(user=user, module=module)

    def test_override_type_par_defaut_grant(self):
        user = _user('zt_umo_default_user')
        module = _module('zt_umo_default_module')
        override = UserModuleOverride.objects.create(user=user, module=module)
        self.assertEqual(override.override_type, 'grant')


# ─── Tests get_user_modules ─────────────────────────────────────────────────────

class TestGetUserModules(TestCase):

    def test_superuser_voit_tous_les_modules_actifs(self):
        superuser = User.objects.create_superuser('zt_gum_su', password='x')
        actif = _module('zt_gum_su_actif', order=100)
        inactif = _module('zt_gum_su_inactif', order=101, is_active=False)
        modules = get_user_modules(superuser)
        self.assertIn(actif, modules, "Le superuser doit voir tous les modules actifs")
        self.assertNotIn(inactif, modules, "Le superuser ne doit pas voir les modules inactifs")

    def test_utilisateur_sans_groupe_ni_override_ne_voit_rien(self):
        user = _user('zt_gum_none')
        _module('zt_gum_none_mod')
        modules = get_user_modules(user)
        self.assertEqual(modules.count(), 0,
                          "Un utilisateur sans groupe ni override ne doit voir aucun module")

    def test_utilisateur_voit_les_modules_de_son_groupe(self):
        user = _user('zt_gum_group')
        group = _group('zt_gum_group_g')
        user.groups.add(group)
        module = _module('zt_gum_group_mod')
        GroupModule.objects.create(group=group, module=module)
        modules = get_user_modules(user)
        self.assertIn(module, modules)
        self.assertEqual(modules.count(), 1)

    def test_grant_individuel_ajoute_un_module_hors_groupe(self):
        user = _user('zt_gum_grant')
        module = _module('zt_gum_grant_mod')
        UserModuleOverride.objects.create(user=user, module=module, override_type='grant')
        modules = get_user_modules(user)
        self.assertIn(module, modules, "Un grant individuel doit donner accès au module")

    def test_revoke_individuel_retire_un_module_du_groupe(self):
        user = _user('zt_gum_revoke')
        group = _group('zt_gum_revoke_g')
        user.groups.add(group)
        module = _module('zt_gum_revoke_mod')
        GroupModule.objects.create(group=group, module=module)
        UserModuleOverride.objects.create(user=user, module=module, override_type='revoke')
        modules = get_user_modules(user)
        self.assertNotIn(module, modules,
                          "Un revoke individuel doit retirer l'accès même si le groupe l'accorde")

    def test_module_inactif_exclu_meme_si_accorde_individuellement(self):
        user = _user('zt_gum_inactive')
        module = _module('zt_gum_inactive_mod', is_active=False)
        UserModuleOverride.objects.create(user=user, module=module, override_type='grant')
        modules = get_user_modules(user)
        self.assertNotIn(module, modules,
                          "Un module inactif ne doit jamais être retourné, même accordé")

    def test_resultat_trie_par_order_puis_nom(self):
        user = _user('zt_gum_order')
        group = _group('zt_gum_order_g')
        user.groups.add(group)
        mod_b = _module('zt_gum_order_b', name='B', order=5)
        mod_a = _module('zt_gum_order_a', name='A', order=5)
        mod_c = _module('zt_gum_order_c', name='C', order=1)
        for m in (mod_a, mod_b, mod_c):
            GroupModule.objects.create(group=group, module=m)
        modules = list(get_user_modules(user))
        self.assertEqual(modules, [mod_c, mod_a, mod_b])


# ─── Tests context processor user_modules ──────────────────────────────────────

class TestUserModulesContextProcessor(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_utilisateur_anonyme_retourne_listes_vides(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        ctx = user_modules(request)
        self.assertEqual(ctx['user_modules'], [])
        self.assertEqual(ctx['user_module_codes'], set())

    def test_utilisateur_authentifie_retourne_ses_modules_et_codes(self):
        user = _user('zt_ctx_user')
        group = _group('zt_ctx_group')
        user.groups.add(group)
        module = _module('zt_ctx_mod')
        GroupModule.objects.create(group=group, module=module)

        request = self.factory.get('/')
        request.user = user
        ctx = user_modules(request)
        self.assertIn(module, ctx['user_modules'])
        self.assertIn('zt_ctx_mod', ctx['user_module_codes'])


# ─── Tests des données de seed (migrations 0002 à 0005) ────────────────────────

class TestDonneesSeedMigrations(TestCase):
    """
    Vérifie l'état final des modules insérés/mis à jour par les migrations
    de données (0002_populate_modules à 0005_update_facturation_url), sans
    ré-exécuter la logique de migration : on interroge directement le modèle,
    tel qu'il a été peuplé lors de la construction de la base de test.
    """

    def test_module_patients_reflete_les_mises_a_jour_de_migration_0003(self):
        module = Module.objects.get(code='patients')
        self.assertEqual(module.icon, '👤')
        self.assertEqual(module.url_name, 'patients:list')
        self.assertEqual(module.order, 1)

    def test_module_facturation_url_name_mis_a_jour_par_migration_0005(self):
        module = Module.objects.get(code='facturation')
        self.assertEqual(module.name, 'Comptabilité')
        self.assertEqual(module.url_name, 'facturation:list')

    def test_module_gynecologie_url_name_mis_a_jour_par_migration_0004(self):
        module = Module.objects.get(code='gynecologie')
        self.assertEqual(module.url_name, 'patients:gynecologie_rdv')

    def test_module_admin_renomme_en_parametres(self):
        module = Module.objects.get(code='admin')
        self.assertEqual(module.name, 'Paramètres')
        self.assertEqual(module.url_name, 'admin:index')
        self.assertEqual(module.order, 23)

    def test_tous_les_modules_de_seed_sont_presents(self):
        codes_attendus = {
            'patients', 'medecins', 'consultations', 'pharmacie', 'laboratoire',
            'hospitalisation', 'facturation', 'caisse', 'ressources_humaines',
            'rapports', 'admin', 'rendezvous', 'assurance', 'services',
            'ordonnances', 'gynecologie', 'medicaments', 'stock', 'achats',
            'planning', 'evaluation', 'presence', 'conges',
        }
        codes_presents = set(
            Module.objects.filter(code__in=codes_attendus).values_list('code', flat=True)
        )
        self.assertEqual(codes_presents, codes_attendus,
                          "Tous les modules attendus des migrations de seed doivent exister")


# ─── Tests admin.py (logique interne) ───────────────────────────────────────────

class TestModuleAdminGroupesCount(TestCase):

    def test_groupes_count_reflete_le_nombre_de_groupes_lies(self):
        module_admin = ModuleAdmin(Module, admin.site)
        module = _module('zt_admin_count')
        GroupModule.objects.create(group=_group('zt_admin_count_g1'), module=module)
        GroupModule.objects.create(group=_group('zt_admin_count_g2'), module=module)
        resultat = str(module_admin.groupes_count(module))
        self.assertIn('2', resultat)


class TestGroupAdminModulesList(TestCase):

    def test_modules_list_affiche_les_modules_du_groupe(self):
        group_admin = GroupAdminWithModules(Group, admin.site)
        group = _group('zt_admin_list_g')
        module = _module('zt_admin_list_mod', name='Mod Liste')
        GroupModule.objects.create(group=group, module=module)
        resultat = str(group_admin.modules_list(group))
        self.assertIn('Mod Liste', resultat)

    def test_modules_list_affiche_message_si_aucun_module(self):
        group_admin = GroupAdminWithModules(Group, admin.site)
        group = _group('zt_admin_list_empty_g')
        resultat = str(group_admin.modules_list(group))
        self.assertIn('Aucun module', resultat)


class TestCustomUserAdminModulesParGroupeView(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.user_admin = CustomUserAdmin(User, admin.site)

    def test_retourne_les_modules_dedupliques_pour_plusieurs_groupes(self):
        groupe1 = _group('zt_admin_view_g1')
        groupe2 = _group('zt_admin_view_g2')
        module_commun = _module('zt_admin_view_commun')
        module_g2 = _module('zt_admin_view_g2_only')
        GroupModule.objects.create(group=groupe1, module=module_commun)
        GroupModule.objects.create(group=groupe2, module=module_commun)
        GroupModule.objects.create(group=groupe2, module=module_g2)

        request = self.factory.get('/', {'group_ids': [str(groupe1.id), str(groupe2.id)]})
        response = self.user_admin.modules_par_groupe_view(request)
        data = json.loads(response.content)

        ids = [m['id'] for m in data['modules']]
        self.assertEqual(len(ids), len(set(ids)), "les modules ne doivent pas être dupliqués")
        self.assertIn(module_commun.id, ids)
        self.assertIn(module_g2.id, ids)

    def test_group_ids_invalides_retourne_une_liste_vide(self):
        request = self.factory.get('/', {'group_ids': ['abc']})
        response = self.user_admin.modules_par_groupe_view(request)
        data = json.loads(response.content)
        self.assertEqual(data['modules'], [])

    def test_group_ids_absents_retourne_une_liste_vide(self):
        request = self.factory.get('/')
        response = self.user_admin.modules_par_groupe_view(request)
        data = json.loads(response.content)
        self.assertEqual(data['modules'], [])


# ─── Tests francisation des permissions ───────────────────────────────────────

class TestFrancisationPermissions(TestCase):

    def test_aucune_permission_anglaise_apres_migrate(self):
        # La base de test est créée par migrate : le post_migrate a déjà tourné.
        from django.contrib.auth.models import Permission
        anglaises = Permission.objects.filter(name__startswith='Can ')
        self.assertFalse(anglaises.exists(), list(anglaises.values_list('name', flat=True)[:5]))

    def test_nom_anglais_renomme_codename_inchange(self):
        from django.contrib.auth.models import Permission
        from modules_permissions.francisation import franciser_permissions
        perm = Permission.objects.get(content_type__app_label='auth', codename='add_group')
        perm.name = 'Can add group'
        perm.save()
        self.assertEqual(franciser_permissions(), 1)
        perm.refresh_from_db()
        self.assertEqual(perm.name, 'Peut créer : groupe')
        self.assertEqual(perm.codename, 'add_group')

    def test_nom_ecrit_a_la_main_jamais_reecrit(self):
        from django.contrib.auth.models import Permission
        from modules_permissions.francisation import franciser_permissions
        perm = Permission.objects.get(content_type__app_label='auth', codename='view_group')
        perm.name = 'Peut voir les groupes'
        perm.save()
        franciser_permissions()
        perm.refresh_from_db()
        self.assertEqual(perm.name, 'Peut voir les groupes')

    def test_sigle_garde_sa_majuscule(self):
        from modules_permissions.francisation import nom_francais
        self.assertEqual(nom_francais('view', None, 'VIH dépistage'), 'Peut consulter : VIH dépistage')
        self.assertEqual(nom_francais('add', None, 'Patient'), 'Peut créer : patient')


class TestChaqueMenuDuNavEstCochable(TestCase):
    """Un menu qui se masque doit avoir sa case dans l'admin, et inversement.

    Les barres de navigation testent `'<code>' not in hidden_navitem_codes`.
    Si aucune ligne `NavItem` ne porte ce code, le gabarit interroge un
    identifiant que la base ignore : le menu s'affiche toujours, et il
    n'apparaît nulle part dans la checklist — impossible de le retirer à un
    groupe, puisqu'il n'y a rien à décocher. Rien ne le signale : le menu
    fonctionne, seul le masquage est muet.

    C'était le cas de `facturation.config` et de `presence.biometrie`. À
    l'inverse `caisse.list` existait en base sans qu'aucun gabarit ne le
    consulte : une case qu'on coche et qui ne fait rien, ce qui est pire que
    pas de case du tout.

    Le test lit les gabarits plutôt qu'une liste écrite à la main : une liste
    recopiée se serait désynchronisée au premier menu ajouté, c'est-à-dire
    exactement ce qu'on veut attraper.
    """

    #: `'patients.pathologie_config' not in hidden_navitem_codes`
    MOTIF = r"""['"]([a-z_]+\.[a-z_0-9]+)['"]\s+not in\s+hidden_navitem_codes"""

    def _codes_des_gabarits(self):
        import re
        from pathlib import Path

        from django.conf import settings
        codes = set()
        for gabarit in Path(settings.BASE_DIR, 'templates').rglob('*.html'):
            codes.update(re.findall(self.MOTIF, gabarit.read_text()))
        return codes

    def _codes_en_base(self):
        from modules_permissions.models import NavItem
        return set(NavItem.objects.values_list('code', flat=True))

    def test_le_relevé_des_gabarits_n_est_pas_vide(self):
        """Témoin : sans lui, une expression régulière cassée rendrait les deux
        tests suivants verts sans rien vérifier."""
        codes = self._codes_des_gabarits()
        self.assertGreater(len(codes), 50,
                           'le relevé des gabarits a cessé de fonctionner')
        self.assertIn('facturation.config', codes)

    def test_chaque_menu_masquable_a_sa_ligne(self):
        manquants = sorted(self._codes_des_gabarits() - self._codes_en_base())
        self.assertEqual(
            manquants, [],
            'ces menus se testent contre hidden_navitem_codes sans exister en '
            'base : ils ne peuvent pas être décochés')

    def test_aucune_ligne_ne_promet_un_masquage_mort(self):
        orphelins = sorted(self._codes_en_base() - self._codes_des_gabarits())
        self.assertEqual(
            orphelins, [],
            "ces lignes n'ont plus de gabarit : on coche la case et rien ne se "
            'passe')
