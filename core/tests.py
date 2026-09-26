"""Les contrôles d'accès reposent sur des permissions, plus sur des noms de groupes.

Neuf gardes comparaient un nom de groupe écrit dans le code — « Caisse »,
« Directeur », « Médecin Chef »… Aucun de ces groupes n'existait en base : les
gardes répondaient « non » à tout le monde sauf au superutilisateur, qui passait
par un autre chemin. Et renommer un groupe dans /admin/ cassait le contrôle sans
le moindre message.

Ces tests vérifient les deux moitiés de la correction : la permission ouvre la
porte, et le nom du groupe qui la porte n'a aucune importance.
"""
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase

from core.permissions import utilisateurs_avec


#: (garde, permission) pour les neuf contrôles repris. Le nom du groupe n'y
#: figure plus : c'est précisément ce qu'on a retiré du code.
def _gardes():
    from achats.views import can_manage_achats
    from conges.views import can_manage_rh as can_manage_conges
    from employer.views import can_manage_rh as can_manage_personnel
    from facturation.views import can_manage_paiement
    from medecins.views import can_manage_medecins
    from planning.views import can_delete_published, can_manage_planning
    from presence.views import can_unlock_registre
    from stock.views import can_manage_stock
    return [
        (can_manage_paiement,   'facturation.can_encaisser'),
        (can_manage_stock,      'stock.can_gerer_stock'),
        (can_manage_achats,     'achats.can_gerer_achats'),
        (can_manage_conges,     'employer.can_gerer_conges'),
        (can_manage_personnel,  'employer.can_gerer_personnel'),
        (can_manage_medecins,   'medecins.can_gerer_medecins'),
        (can_manage_planning,   'planning.can_gerer_planning'),
        (can_delete_published,  'planning.can_supprimer_planning_publie'),
        (can_unlock_registre,   'presence.can_rouvrir_registre'),
    ]


def _permission(code):
    app_label, codename = code.split('.')
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _utilisateur_avec_groupe(username, nom_du_groupe, code_permission):
    user = User.objects.create_user(username, password='x')
    groupe, _ = Group.objects.get_or_create(name=nom_du_groupe)
    groupe.permissions.add(_permission(code_permission))
    user.groups.add(groupe)
    # Le cache de permissions est peuplé au premier has_perm : on relit.
    return User.objects.get(pk=user.pk)


# ─── Les neuf gardes ───────────────────────────────────────────────────────────

class TestLesGardesLisentUnePermission(TestCase):

    def test_toutes_les_permissions_existent(self):
        """Une permission absente ferait répondre « non » à tout le monde."""
        for _, code in _gardes():
            with self.subTest(permission=code):
                self.assertIsNotNone(_permission(code))

    def test_un_utilisateur_nu_est_refuse_partout(self):
        user = User.objects.create_user('nu', password='x')
        for garde, code in _gardes():
            with self.subTest(permission=code):
                self.assertFalse(garde(user))

    def test_la_permission_ouvre_la_porte_quel_que_soit_le_nom_du_groupe(self):
        """Le cœur de la correction : des noms libres, jamais ceux d'avant."""
        noms = ['Guichet du lundi', 'Équipe de nuit', 'Bureau 12', 'Les gens bien',
                'Permanence', 'Groupe A', 'Étage 2', 'Roulement B', 'Divers']
        for (garde, code), nom in zip(_gardes(), noms):
            with self.subTest(permission=code, groupe=nom):
                user = _utilisateur_avec_groupe(f'u_{code.replace(".", "_")}', nom, code)
                self.assertTrue(garde(user))

    def test_un_groupe_sans_la_permission_reste_refuse(self):
        for garde, code in _gardes():
            with self.subTest(permission=code):
                user = User.objects.create_user(f'v_{code.replace(".", "_")}', password='x')
                groupe, _ = Group.objects.get_or_create(name='Groupe vide')
                user.groups.add(groupe)
                self.assertFalse(garde(User.objects.get(pk=user.pk)))

    def test_le_superutilisateur_passe_partout(self):
        su = User.objects.create_superuser('su_gardes', password='x')
        for garde, code in _gardes():
            with self.subTest(permission=code):
                self.assertTrue(garde(su))

    def test_les_anciens_noms_de_groupe_n_ouvrent_plus_rien(self):
        """Un groupe nommé « Caisse » ou « Directeur » n'a plus aucun pouvoir
        propre : c'est ce qui rend le renommage sans danger."""
        for nom in ('Caisse', 'Directeur', 'Administrateur', 'RH', 'Médecin Chef'):
            with self.subTest(groupe=nom):
                user = User.objects.create_user(f'ancien_{nom[:6]}', password='x')
                groupe, _ = Group.objects.get_or_create(name=nom)
                user.groups.add(groupe)
                user = User.objects.get(pk=user.pk)
                for garde, code in _gardes():
                    self.assertFalse(garde(user), f'{nom} ouvre encore {code}')


# ─── Chercher les utilisateurs d'une permission ────────────────────────────────

class TestUtilisateursAvec(TestCase):

    CODE = 'employer.can_gerer_conges'

    def test_trouve_par_le_groupe(self):
        user = _utilisateur_avec_groupe('via_groupe', 'Bureau 3', self.CODE)
        self.assertIn(user, utilisateurs_avec(self.CODE))

    def test_trouve_par_la_permission_directe(self):
        user = User.objects.create_user('via_direct', password='x')
        user.user_permissions.add(_permission(self.CODE))
        self.assertIn(user, utilisateurs_avec(self.CODE))

    def test_trouve_le_superutilisateur(self):
        su = User.objects.create_superuser('su_uav', password='x')
        self.assertIn(su, utilisateurs_avec(self.CODE))

    def test_ignore_qui_n_a_pas_la_permission(self):
        user = User.objects.create_user('sans', password='x')
        self.assertNotIn(user, utilisateurs_avec(self.CODE))

    def test_ignore_les_comptes_desactives(self):
        user = _utilisateur_avec_groupe('inactif', 'Bureau 4', self.CODE)
        user.is_active = False
        user.save(update_fields=['is_active'])
        self.assertNotIn(user, utilisateurs_avec(self.CODE))

    def test_ne_compte_pas_deux_fois_qui_la_detient_deux_fois(self):
        """Deux groupes porteurs, plus la permission en direct : une seule ligne."""
        user = _utilisateur_avec_groupe('double', 'Bureau 5', self.CODE)
        second, _ = Group.objects.get_or_create(name='Bureau 6')
        second.permissions.add(_permission(self.CODE))
        user.groups.add(second)
        user.user_permissions.add(_permission(self.CODE))
        self.assertEqual(list(utilisateurs_avec(self.CODE)).count(user), 1)

    def test_une_permission_inconnue_ne_leve_pas(self):
        """Entre deux migrations la permission peut manquer : seuls les
        superutilisateurs passent, comme le dirait `has_perm`."""
        su = User.objects.create_superuser('su_inconnue', password='x')
        User.objects.create_user('quidam', password='x')
        trouves = utilisateurs_avec('employer.permission_qui_n_existe_pas')
        self.assertEqual(list(trouves), [su])
