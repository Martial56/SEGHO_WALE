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


# ─── Revenir d'une action annexe sans perdre sa saisie ─────────────────────────

class TestUrlDeRetour(TestCase):
    """Le module qui fabrique et valide les adresses de retour.

    L'adresse vient du navigateur : mal filtrée, elle renverrait l'utilisateur
    sur un autre site en lui laissant croire qu'il est toujours chez lui.
    """

    def setUp(self):
        from django.test import RequestFactory
        self.rf = RequestFactory()

    def _requete(self, **post):
        return self.rf.post('/gynecologie/rdv/1/', post)

    def test_une_adresse_du_site_est_acceptee(self):
        from core.retour import url_interne
        r = self._requete()
        self.assertEqual(url_interne(r, '/gynecologie/rdv/1/'), '/gynecologie/rdv/1/')

    def test_une_adresse_etrangere_est_refusee(self):
        from core.retour import url_interne
        r = self._requete()
        for mechante in ('https://ailleurs.example/vol', '//ailleurs.example/vol'):
            with self.subTest(url=mechante):
                self.assertIsNone(url_interne(r, mechante))

    def test_le_retour_s_accroche_sans_ecraser_les_parametres(self):
        from core.retour import vers_avec_retour
        self.assertEqual(
            vers_avec_retour('/laboratoire/nouvelle/?patient=3', '/rdv/1/'),
            '/laboratoire/nouvelle/?patient=3&next=%2Frdv%2F1%2F')
        self.assertEqual(
            vers_avec_retour('/soins/nouveau/', '/rdv/1/'),
            '/soins/nouveau/?next=%2Frdv%2F1%2F')

    def test_l_onglet_ouvert_est_reconduit(self):
        from core.retour import retour_vers_le_rdv
        r = self._requete(_onglet='curative')
        self.assertEqual(retour_vers_le_rdv(r, '/rdv/1/'), '/rdv/1/?onglet=curative')

    def test_un_onglet_inconnu_est_ignore(self):
        """L'onglet vient du navigateur : on ne le recopie pas tel quel."""
        from core.retour import retour_vers_le_rdv
        r = self._requete(_onglet='"><script>')
        self.assertEqual(retour_vers_le_rdv(r, '/rdv/1/'), '/rdv/1/')

    def test_sans_bouton_d_action_on_reste_sur_place(self):
        from core.retour import detour_demande
        self.assertIsNone(detour_demande(self._requete(), '/rdv/1/'))

    def test_une_destination_etrangere_ne_fait_pas_partir(self):
        from core.retour import detour_demande
        r = self._requete(_apres='https://ailleurs.example/vol')
        self.assertIsNone(detour_demande(r, '/rdv/1/'))

    def test_le_detour_emporte_l_adresse_de_retour(self):
        from core.retour import detour_demande
        r = self._requete(_apres='/laboratoire/nouvelle/?patient=3', _onglet='curative')
        self.assertEqual(
            detour_demande(r, '/gynecologie/rdv/1/'),
            '/laboratoire/nouvelle/?patient=3&next=%2Fgynecologie%2Frdv%2F1%2F%3Fonglet%3Dcurative')


class TestLaFicheRdvEnregistreAvantDePartir(TestCase):
    """Le cœur du besoin : cliquer « Demande de lab » ne doit rien perdre.

    Les quatre boutons étaient de simples liens posés dans le formulaire. Le
    navigateur quittait la page, et les 376 champs saisis disparaissaient.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from django.utils import timezone
        from patients.models import Patient, RendezVous
        self.user = User.objects.create_superuser('medecin_rdv', password='x')
        self.client.force_login(self.user)
        self.patient = Patient.objects.create(
            nom='Retour', prenoms='Test', date_naissance='1990-01-01',
            sexe='F', telephone='0700000000')
        from medecins.models import Departement
        self.departement, _ = Departement.objects.get_or_create(
            code='GYN', defaults={'nom': 'Gynécologie'})
        self.rdv = RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now(),
            departement=self.departement,
            statut='en_consultation', motif='Consultation')
        from django.urls import reverse
        self.url = reverse('patients:rdv_edit', kwargs={'pk': self.rdv.pk})

    def _post(self, **extra):
        donnees = {
            'patient': self.patient.pk,
            'departement': self.departement.pk,
            'date_heure': self.rdv.date_heure.strftime('%Y-%m-%dT%H:%M'),
            'motif': 'Consultation',
            'cur_motif_consultation': 'douleurs abdominales',
        }
        donnees.update(extra)
        return self.client.post(self.url, donnees)

    def test_l_url_de_la_fiche_repond(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_le_clic_enregistre_la_saisie_avant_de_partir(self):
        from patients.models import RegistreCuratif
        self._post(_apres='/laboratoire/nouvelle/?patient=%d' % self.patient.pk,
                   _onglet='curative')
        registre = RegistreCuratif.objects.get(rdv=self.rdv)
        self.assertEqual(registre.donnees['cur_motif_consultation'], 'douleurs abdominales')

    def test_le_clic_emmene_vers_la_destination_avec_le_retour(self):
        reponse = self._post(
            _apres='/laboratoire/nouvelle/?patient=%d' % self.patient.pk,
            _onglet='curative')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/laboratoire/nouvelle/', reponse['Location'])
        self.assertIn('next=', reponse['Location'])
        self.assertIn('onglet%3Dcurative', reponse['Location'])

    def test_sans_bouton_d_action_on_revient_sur_la_fiche(self):
        reponse = self._post()
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(str(self.rdv.pk), reponse['Location'])
        self.assertNotIn('laboratoire', reponse['Location'])

    def test_une_destination_etrangere_ne_fait_pas_quitter_le_site(self):
        reponse = self._post(_apres='https://ailleurs.example/vol')
        self.assertEqual(reponse.status_code, 302)
        self.assertNotIn('ailleurs.example', reponse['Location'])

    def test_les_quatre_boutons_soumettent_au_lieu_de_quitter(self):
        """Un `<a href>` ne soumet rien : c'est ce qui perdait la saisie."""
        page = self.client.get(self.url).content.decode()
        self.assertEqual(page.count('name="_apres"'), 4)
        self.assertEqual(page.count('name="_onglet"'), 1)


# ─── Modèles vierges des spécialités et des départements ───────────────────────

class TestModelesDImportMedecins(TestCase):
    """Mêmes colonnes que l'import, une ligne d'exemple, rien à deviner.

    Le département est en tête de la chaîne : une prestation s'y rattache par
    son code. S'il n'existe pas encore, le rattachement est ignoré — d'où
    l'intérêt de pouvoir le créer en masse sans se tromper de colonnes.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('mod_med', password='x'))

    def _classeur(self, url):
        import io
        import openpyxl
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        return reponse, openpyxl.load_workbook(io.BytesIO(reponse.content))

    def test_les_deux_modeles_se_telechargent(self):
        for url, fichier in (
            ('/medecins/config/specialites/export/modele/', 'modele_import_specialites.xlsx'),
            ('/medecins/config/departements/export/modele/', 'modele_import_departements.xlsx'),
        ):
            with self.subTest(url=url):
                reponse, _ = self._classeur(url)
                self.assertIn(fichier, reponse['Content-Disposition'])

    def test_les_colonnes_sont_celles_de_l_export(self):
        from core.views import _DEPT_HDR, _SPEC_HDR
        for url, entetes in (
            ('/medecins/config/specialites/export/modele/', _SPEC_HDR),
            ('/medecins/config/departements/export/modele/', _DEPT_HDR),
        ):
            with self.subTest(url=url):
                _, wb = self._classeur(url)
                self.assertEqual([c.value for c in wb.active[1]], entetes)

    def test_la_colonne_actif_propose_un_et_zero(self):
        """Sans la liste, Excel écrit « VRAI » et l'import ne le reconnaît pas."""
        _, wb = self._classeur('/medecins/config/departements/export/modele/')
        valeurs = {c.value for ligne in wb['Listes'].iter_rows() for c in ligne if c.value}
        self.assertEqual(valeurs, {'1', '0'})

    def test_un_modele_de_departement_rempli_s_importe(self):
        import io
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile
        from medecins.models import Departement

        _, wb = self._classeur('/medecins/config/departements/export/modele/')
        ws = wb.active
        ws.delete_rows(2)
        ws.append(['ZZD', 'Département de test', 'essai', '1'])
        tampon = io.BytesIO()
        wb.save(tampon)
        tampon.seek(0)
        self.client.post('/medecins/config/departements/import/', {
            'fichier': SimpleUploadedFile(
                'm.xlsx', tampon.read(),
                content_type='application/vnd.openxmlformats-officedocument.'
                             'spreadsheetml.sheet')})

        departement = Departement.objects.get(code='ZZD')
        self.assertEqual(departement.nom, 'Département de test')
        self.assertTrue(departement.actif)

    def test_un_modele_de_specialite_rempli_s_importe(self):
        import io
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile
        from medecins.models import Specialite

        _, wb = self._classeur('/medecins/config/specialites/export/modele/')
        ws = wb.active
        ws.delete_rows(2)
        ws.append(['ZZS', 'Spécialité de test', 'essai'])
        tampon = io.BytesIO()
        wb.save(tampon)
        tampon.seek(0)
        self.client.post('/medecins/config/specialites/import/', {
            'fichier': SimpleUploadedFile(
                'm.xlsx', tampon.read(),
                content_type='application/vnd.openxmlformats-officedocument.'
                             'spreadsheetml.sheet')})

        self.assertEqual(Specialite.objects.get(code='ZZS').nom, 'Spécialité de test')
