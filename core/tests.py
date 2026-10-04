"""Les contrôles d'accès reposent sur des permissions, plus sur des noms de groupes.

Neuf gardes comparaient un nom de groupe écrit dans le code — « Caisse »,
« Directeur », « Médecin Chef »… Aucun de ces groupes n'existait en base : les
gardes répondaient « non » à tout le monde sauf au superutilisateur, qui passait
par un autre chemin. Et renommer un groupe dans /admin/ cassait le contrôle sans
le moindre message.

Ces tests vérifient les deux moitiés de la correction : la permission ouvre la
porte, et le nom du groupe qui la porte n'a aucune importance.
"""
import re

from django.contrib.auth.models import Group, Permission, User
from django.test import Client, TestCase
from django.urls import reverse

from core.listing import TOUS_LES_GROUPES
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
            # Obligatoire dès que la consultation a démarré.
            'cur_type_visite': 'consultant',
        }
        donnees.update(extra)
        return self.client.post(self.url, donnees)

    def _type_consultation(self, code_departement):
        from medecins.models import Departement
        from services.models import Articleservice, CategorieArticle
        departement, _ = Departement.objects.get_or_create(
            code=code_departement, defaults={'nom': code_departement})
        categorie, _ = CategorieArticle.objects.get_or_create(
            code='CS', defaults={'nom': 'Consultations'})
        return Articleservice.objects.create(
            nom=f'CONSULTATION {code_departement}', categorie=categorie,
            departement=departement)

    def test_medecine_generale_sans_type_de_visite_curative_rien_n_est_enregistre(self):
        from patients.models import RegistreCuratif
        tc = self._type_consultation('medg')
        reponse = self._post(cur_type_visite='', type_consultation=tc.pk)
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(RegistreCuratif.objects.filter(rdv=self.rdv).exists())

    def test_hors_medecine_generale_le_type_de_visite_curative_est_facultatif(self):
        from patients.models import RegistreCuratif
        tc = self._type_consultation('GYN')
        reponse = self._post(cur_type_visite='', type_consultation=tc.pk)
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(RegistreCuratif.objects.get(rdv=self.rdv)
                         .donnees['cur_motif_consultation'], 'douleurs abdominales')

    def test_la_fiche_connait_les_departements_de_medecine_generale(self):
        tc = self._type_consultation('medg')
        page = self.client.get(self.url).content.decode()
        # 'MEDGEN' (migration medecins/0015) peut s'y trouver aussi.
        import re
        ids = re.search(r'data-medg-departements="([^"]*)"', page).group(1).split(',')
        self.assertIn(str(tc.departement_id), ids)

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

    def test_consultation_terminee_enregistre_les_registres(self):
        """« Consultation terminée » changeait l'état sans garder la saisie."""
        from patients.models import RegistreCuratif
        reponse = self._post(_action='terminer')
        self.assertEqual(reponse.status_code, 302)
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.statut, 'termine')
        registre = RegistreCuratif.objects.get(rdv=self.rdv)
        self.assertEqual(registre.donnees['cur_motif_consultation'], 'douleurs abdominales')

    def test_apres_terminer_on_reste_sur_la_fiche_et_on_modifie_les_registres(self):
        from patients.models import RegistreCuratif
        reponse = self._post(_action='terminer', _onglet='curative')
        # Retour sur la fiche, onglet du registre rouvert — pas sur la liste.
        self.assertEqual(reponse['Location'], self.url + '?onglet=curative')
        page = self.client.get(reponse['Location']).content.decode()
        self.assertIn('autosave_registres', page)

        # Correction du registre une fois la consultation terminée.
        reponse = self._post(cur_motif_consultation='céphalées')
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(RegistreCuratif.objects.get(rdv=self.rdv)
                         .donnees['cur_motif_consultation'], 'céphalées')
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.statut, 'termine')

    def test_l_enregistrement_automatique_garde_les_registres(self):
        from patients.models import RegistreCuratif
        # Ni le formulaire du rendez-vous ni le type de visite ne sont exigés.
        reponse = self.client.post(self.url, {
            '_action': 'autosave_registres',
            'cur_motif_consultation': 'fièvre',
        })
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.json()['ok'])
        registre = RegistreCuratif.objects.get(rdv=self.rdv)
        self.assertEqual(registre.donnees['cur_motif_consultation'], 'fièvre')
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.statut, 'en_consultation')

    def test_l_enregistrement_automatique_attend_la_consultation(self):
        from patients.models import RegistreCuratif
        self.rdv.statut = 'confirme'
        self.rdv.save(update_fields=['statut'])
        reponse = self.client.post(self.url, {
            '_action': 'autosave_registres', 'cur_motif_consultation': 'x'})
        self.assertEqual(reponse.status_code, 403)
        self.assertFalse(RegistreCuratif.objects.filter(rdv=self.rdv).exists())

    def test_la_fiche_charge_l_enregistrement_automatique(self):
        page = self.client.get(self.url).content.decode()
        self.assertIn('autosave_registres', page)

    def test_gynecologie_terminer_et_enregistrement_automatique(self):
        from django.urls import reverse
        from patients.models import RegistreCPN
        url = reverse('gynecologie_rdv_detail', kwargs={'pk': self.rdv.pk})
        self.assertIn('autosave_registres', self.client.get(url).content.decode())

        reponse = self.client.post(url, {
            '_action': 'autosave_registres', 'cpn_mode_entree': 'nouvelle'})
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(RegistreCPN.objects.get(rdv=self.rdv).donnees['cpn_mode_entree'], 'nouvelle')

        reponse = self.client.post(url, {
            '_action': 'terminer', 'cpn_mode_entree': 'ancienne', '_onglet': 'cpn'})
        self.assertEqual(reponse['Location'], url + '?onglet=cpn')
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.statut, 'termine')
        self.assertEqual(self.rdv.cpn_mode_entree, 'ancienne')
        self.assertEqual(RegistreCPN.objects.get(rdv=self.rdv).donnees['cpn_mode_entree'], 'ancienne')


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


# ─── La sélection d'une liste survit à un aller-retour ─────────────────────────

class TestMemoireDesListes(TestCase):
    """Filtrer, ouvrir une fiche, revenir : le filtre doit être encore là.

    Il ne tenait pas : la liste se rouvrait entière, et tout le travail de tri
    était à refaire. La sélection vit dans l'URL, il suffit donc de l'y remettre
    — plutôt que d'inventer un état caché que l'adresse affichée démentirait.
    """

    def setUp(self):
        self.user = User.objects.create_superuser('u_mem', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('patients:rdv_global')

    def _ajax(self, url):
        return self.client.get(url, headers={'x-requested-with': 'XMLHttpRequest'})

    # ── Retenir et restaurer ───────────────────────────────────────────────

    def test_revenir_sans_parametres_restaure_la_selection(self):
        self.client.get(self.url + '?filter=aujourdhui&filter=demain&q=kouassi')
        reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('filter=aujourdhui', reponse.url)
        self.assertIn('filter=demain', reponse.url)
        self.assertIn('q=kouassi', reponse.url)

    def test_les_valeurs_repetees_sont_toutes_gardees(self):
        """Un dictionnaire n'en aurait retenu qu'une : `filter` se répète."""
        self.client.get(self.url + '?filter=a&filter=b&filter=c')
        reponse = self.client.get(self.url)
        for valeur in ('filter=a', 'filter=b', 'filter=c'):
            with self.subTest(valeur=valeur):
                self.assertIn(valeur, reponse.url)

    def test_sans_rien_de_retenu_la_liste_s_affiche_normalement(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # ── Les trois façons d'oublier ─────────────────────────────────────────

    def test_effacer_oublie_la_selection(self):
        """« Effacer » rafraîchit la liste en AJAX, sans aucun paramètre."""
        self.client.get(self.url + '?filter=aujourdhui')
        self.assertEqual(self._ajax(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 200,
                         'La sélection effacée a été restaurée')

    def test_une_nouvelle_selection_ecrase_la_precedente(self):
        self.client.get(self.url + '?filter=aujourdhui')
        self.client.get(self.url + '?filter=semaine')
        reponse = self.client.get(self.url)
        self.assertIn('filter=semaine', reponse.url)
        self.assertNotIn('aujourdhui', reponse.url)

    def test_l_accueil_vide_toutes_les_listes(self):
        self.client.get(self.url + '?filter=aujourdhui')
        self.client.get(reverse('patients:list') + '?q=kouassi')
        self.client.get(reverse('dashboard'))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(reverse('patients:list')).status_code, 200)

    # ── L'état déplié, qui ne recharge rien ────────────────────────────────

    def test_la_note_de_depliage_est_retenue(self):
        """Déplier un groupe ne recharge pas la page : l'état déplié n'arrivait
        donc jamais jusqu'ici, et revenir par le bouton « Retour » d'une fiche
        ramenait le filtre et le regroupement, mais la liste repliée. Le
        navigateur envoie désormais cette note de fond à chaque dépliage."""
        self._ajax(self.url + '?group=statut&ouverts=1:0&_memo=1')
        reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('ouverts=1%3A0', reponse.url)

    def test_la_note_de_depliage_ne_rend_aucune_page(self):
        """Tout son intérêt : elle ne coûte que ce qu'il faut pour retenir."""
        reponse = self._ajax(self.url + '?group=statut&ouverts=1:0&_memo=1')
        self.assertEqual(reponse.status_code, 204)
        self.assertFalse(reponse.content)

    def test_replier_le_dernier_groupe_oublie_l_etat(self):
        """La note suivante ne porte plus `ouverts` : elle doit l'emporter,
        sinon la liste rouvrirait un groupe qu'on vient de fermer."""
        self._ajax(self.url + '?group=statut&ouverts=1:0&_memo=1')
        self._ajax(self.url + '?group=statut&_memo=1')
        self.assertNotIn('ouverts', self.client.get(self.url).url)

    def test_une_note_sans_selection_n_efface_rien(self):
        """Elle voyage en AJAX, comme « Effacer ». Sans le retour anticipé de
        `selection_memorisee`, une note dépourvue de critères passerait pour un
        effacement que personne n'a demandé."""
        self.client.get(self.url + '?filter=aujourdhui')
        self._ajax(self.url + '?_memo=1')
        reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 302,
                         'la note a effacé la sélection retenue')
        self.assertIn('filter=aujourdhui', reponse.url)

    # ── Chaque liste a sa propre mémoire ───────────────────────────────────

    def test_deux_listes_ne_se_melangent_pas(self):
        """Les trois listes de rendez-vous partagent la vue, pas l'adresse."""
        self.client.get(self.url + '?filter=aujourdhui')
        autre = reverse('patients:list')
        self.assertEqual(self.client.get(autre).status_code, 200,
                         "La sélection d'une liste a débordé sur l'autre")
        self.assertEqual(self.client.get(self.url).status_code, 302)

    # ── Ce qui ne doit pas être retenu ─────────────────────────────────────

    def test_la_page_n_est_pas_retenue(self):
        """Retrouver sa liste à la page 7 surprendrait plus que d'aider."""
        self.client.get(self.url + '?filter=aujourdhui&page=3')
        reponse = self.client.get(self.url)
        self.assertNotIn('page=', reponse.url)

    def test_un_parametre_etranger_ne_declenche_rien(self):
        """`?origine=gynecologie` n'est pas une sélection."""
        self.client.get(self.url + '?origine=gynecologie')
        self.assertEqual(self.client.get(self.url).status_code, 200)


# ─── Pagination des groupes ────────────────────────────────────────────────────

class TestLaPaginationDesGroupes(TestCase):
    """Une page groupée doit porter autant d'en-têtes qu'une page à plat de lignes.

    En mode groupé, seuls les en-têtes racines sont visibles : les lignes de
    données et les sous-groupes partent repliés (`display:none` dans
    includes/listing/groupes.html). Le réglage d'origine, huit groupes par page
    quelle que soit la liste, remplissait donc le quart d'un écran — alors que
    les mêmes listes affichent 25, 40 ou 80 lignes sans regroupement.
    """

    def _pagineur(self, tailles, par_page):
        from core.listing import _PaginateurDeGroupes
        return _PaginateurDeGroupes(list(tailles), tailles, par_page)

    def _etendue(self, pagineur, numero):
        page = pagineur.page(numero)
        return len(page.object_list), page.start_index(), page.end_index()

    def test_une_page_porte_autant_d_en_tetes_que_la_liste_de_lignes(self):
        pagineur = self._pagineur({f'g{i}': 1 for i in range(30)}, 25)
        self.assertEqual(pagineur.num_pages, 2)
        self.assertEqual(self._etendue(pagineur, 1), (25, 1, 25))
        self.assertEqual(self._etendue(pagineur, 2), (5, 26, 30))

    def test_chaque_liste_garde_sa_propre_taille(self):
        """80 pour les rendez-vous de gynécologie, 25 pour les factures."""
        tailles = {f'g{i}': 1 for i in range(100)}
        self.assertEqual(self._pagineur(tailles, 80).num_pages, 2)
        self.assertEqual(self._pagineur(tailles, 25).num_pages, 4)

    def test_un_groupe_gros_n_empeche_pas_les_autres_de_tenir(self):
        """Un regroupement très déséquilibré — une ville qui pèse presque tout —
        ne doit pas renvoyer les petits groupes à la page suivante."""
        villes = {'Yamoussoukro': 363, 'Abidjan': 30, 'Bouaké': 12,
                  'Daloa': 8, 'Korhogo': 6, 'Man': 4}
        self.assertEqual(self._pagineur(villes, 40).num_pages, 1)

    def test_le_plafond_coupe_une_page_de_groupes_enormes(self):
        """Les lignes des groupes affichés partent dans le HTML même repliées :
        une page de cinquante gros groupes pèserait pour rien."""
        pagineur = self._pagineur({f'G{i}': 100 for i in range(50)}, 25)
        self.assertEqual(len(pagineur.page(1).object_list), 10)

    def test_le_plafond_ne_descend_jamais_sous_le_minimum(self):
        """Mieux vaut une page lourde qu'une page à un seul groupe."""
        from core.listing import _PaginateurDeGroupes as P
        pagineur = self._pagineur({f'G{i}': 5000 for i in range(5)}, 25)
        self.assertEqual(len(pagineur.page(1).object_list),
                         P.MINIMUM_GROUPES_PAR_PAGE)

    def test_les_bornes_suivent_le_decoupage_reel(self):
        """`Page` les déduit d'une taille constante ; ici elle varie."""
        tailles = {'a': 1, 'b': 1, 'c': 1200, 'd': 2, 'e': 3, 'f': 4, 'g': 5}
        pagineur = self._pagineur(tailles, 25)
        rangs = [self._etendue(pagineur, n)[1:]
                 for n in range(1, pagineur.num_pages + 1)]
        # Les bornes s'enchaînent sans trou ni recouvrement.
        self.assertEqual(rangs[0][0], 1)
        for (_, fin), (debut, _) in zip(rangs, rangs[1:]):
            self.assertEqual(debut, fin + 1)
        self.assertEqual(rangs[-1][1], len(tailles))

    def test_une_selection_vide_garde_une_page(self):
        pagineur = self._pagineur({}, 25)
        self.assertEqual(pagineur.num_pages, 1)
        self.assertEqual(pagineur.count, 0)
        self.assertEqual(list(pagineur.page(1).object_list), [])

    def test_les_onze_listes_passent_leur_taille(self):
        """Le paramètre avait une valeur par défaut et personne ne l'envoyait :
        les onze listes héritaient du même 8."""
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        appels = 0
        for fichier in racine.glob('*/views.py'):
            texte = fichier.read_text()
            appels += texte.count('paginer_groupes(')
            self.assertNotIn("paginer_groupes(qs, dims, request.GET.get('page'))",
                             texte, f'{fichier.name} n\'envoie pas sa taille')
        self.assertEqual(appels, 11)


# ─── Chargement différé des lignes d'un groupe ────────────────────────────────

class TestLesLignesArriventAuDepliage(TestCase):
    """Une liste regroupée ne porte plus les lignes de tous ses groupes.

    Toutes les lignes des groupes affichés partaient dans le HTML, repliées et
    souvent jamais lues. Une ligne pèse plus d'un kilo-octet : un regroupement
    à gros groupes produisait une page de plusieurs dizaines de méga-octets
    pour un écran qui ne montrait que des en-têtes.

    La page part donc avec ses seuls en-têtes. Un groupe sait rendre ses lignes
    à lui (`_groupe=<chemin>`), et la page sait les rendre toutes d'un coup
    (`_groupe=*`) : c'est ce que le navigateur demande en tâche de fond une fois
    la page affichée, pour que déplier ne fasse plus attendre.
    """

    def setUp(self):
        from django.utils import timezone
        from facturation.models import Facture
        from patients.models import Patient

        User.objects.create_superuser('su_lazy', password='x')
        self.client = Client()
        self.client.login(username='su_lazy', password='x')

        patient = Patient.objects.create(
            nom='Lazy', prenoms='Patient', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000')
        for statut, combien in (('emise', 3), ('payee', 2)):
            for _ in range(combien):
                Facture.objects.create(
                    patient=patient, type_facture='consultation', statut=statut,
                    montant_total=1000, date_emission=timezone.now())
        self.url = reverse('facturation:list') + '?filter=&group=statut'

    def _html(self, suffixe=''):
        reponse = self.client.get(self.url + suffixe)
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    @staticmethod
    def _nb_lignes(html):
        """Les lignes de données, repérées par le balisage de leur première
        cellule — jamais par un nom de classe nu, qui vit aussi dans le CSS."""
        return html.count('<td data-col="1" class="td-num">')

    def test_la_page_groupee_ne_porte_aucune_ligne(self):
        html = self._html()
        self.assertIn('data-feuille="1"', html)
        self.assertEqual(self._nb_lignes(html), 0)

    def test_deplier_un_groupe_rend_ses_lignes(self):
        html = self._html('&_groupe=0')
        self.assertEqual(self._nb_lignes(html), 3)

    def test_le_depliage_rend_les_lignes_en_ajax(self):
        """C'est le chemin réel : le script demande la page en AJAX.

        Il ne le faisait pas au départ, par crainte qu'une liste réponde par un
        fragment de `<tr>` nus — que l'analyseur HTML jette hors d'un tableau.
        Aucune n'est dans ce cas, et la page entière coûtait quatre fois plus
        cher : 554 ms et 256 Ko pour trois lignes, contre 146 ms et 44 Ko.

        Si une liste se mettait à répondre sans tableau, c'est ici que ça se
        verrait.
        """
        reponse = self.client.get(
            self.url + '&_groupe=0',
            headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.content.decode()
        self.assertEqual(self._nb_lignes(corps), 3)
        self.assertIn('<table', corps,
                      'des lignes hors tableau seraient jetées par le navigateur')

    def test_chaque_groupe_rend_les_siennes_et_pas_celles_du_voisin(self):
        self.assertEqual(self._nb_lignes(self._html('&_groupe=1')), 2)

    def test_les_lignes_portent_le_chemin_de_leur_groupe(self):
        """C'est par là que le navigateur les retrouve dans la page renvoyée."""
        self.assertIn('data-parent="0"', self._html('&_groupe=0'))

    def test_un_chemin_inconnu_ne_casse_rien(self):
        """Une page rafraîchie pendant qu'un dépliage était en vol."""
        self.assertEqual(self._nb_lignes(self._html('&_groupe=42-7')), 0)

    def test_un_groupe_qui_a_des_sous_groupes_ne_rend_pas_de_lignes(self):
        """Ses sous-groupes sont déjà dans la page : ce sont eux qui demanderont."""
        html = self._html('&group=type&_groupe=0')
        self.assertEqual(self._nb_lignes(html), 0)

    def test_deplier_un_groupe_parent_ne_balaie_pas_toute_la_selection(self):
        """Le garde-fou `not noeud['enfants']` protège le temps, pas le résultat.

        Sans lui, on demande les lignes d'un chemin partiel : aucune condition
        SQL ne sait l'exprimer, et on retombe sur le tri en Python — qui
        parcourt **toute** la sélection pour ne rien trouver, le chemin d'un
        parent ne pouvant jamais égaler celui d'une feuille. Le résultat reste
        juste, la page reste vide, et rien ne se voit : seul le compte de
        requêtes trahit le balayage.

        Si ce nombre change pour une raison étrangère, relancez la mesure
        plutôt que de l'ajuster à l'aveugle — c'est l'écart d'une requête qui
        compte, pas sa valeur absolue.

        Il est passé de 18 à 25 le jour où la liste des factures a reçu le
        filtre personnalisé : `champs_pour_navigateur` interroge chaque champ
        lié pour en proposer les valeurs. Ces requêtes-là sont les mêmes qu'on
        déplie un parent ou une feuille, elles ne disent donc rien du balayage
        que ce test surveille — seul l'écart compte, et il reste nul.
        """
        with self.assertNumQueries(25):
            self.client.get(self.url + '&group=type&_groupe=0')

    def test_un_sous_groupe_rend_bien_les_siennes(self):
        html = self._html('&group=type&_groupe=0-0')
        self.assertEqual(self._nb_lignes(html), 3)

    def test_tout_precharger_rend_les_lignes_de_tous_les_groupes(self):
        """`_groupe=*` : une seule requête pour les deux groupes.

        C'est ce qui rend le dépliage instantané. Demander groupe par groupe
        donnait 3 lignes puis 2 ; ici les 5 arrivent ensemble.
        """
        html = self._html('&_groupe=' + TOUS_LES_GROUPES)
        self.assertEqual(self._nb_lignes(html), 5)
        self.assertIn('data-parent="0"', html)
        self.assertIn('data-parent="1"', html,
                      'le second groupe est resté sans lignes')

    def test_un_groupe_reclame_ouvert_arrive_deja_deplie(self):
        """La page rendue est la bonne du premier coup.

        Rouvrir les groupes après l'affichage marchait, mais se voyait : la
        liste arrivait fermée puis sautait. Les filtres n'ont jamais ce défaut
        parce qu'ils sont appliqués au rendu — l'état déplié suit désormais le
        même chemin.
        """
        html = self._html('&ouverts=1:0')
        self.assertRegex(html, r'<tr class="lst-groupe[^"]*open"[^>]*data-chemin="0"',
                         "la bande n'est pas marquée ouverte")
        self.assertEqual(self._nb_lignes(html), 3,
                         'les lignes du groupe ouvert devraient être rendues')

    def test_les_lignes_d_un_groupe_ouvert_ne_sont_pas_masquees(self):
        """Rendre la bande ouverte sans montrer ses lignes donnerait un groupe
        béant : c'est le `display:none` des gabarits de ligne qui devait suivre."""
        html = self._html('&ouverts=1:0')
        lignes = re.findall(r'<tr data-parent="0"[^>]*>', html)
        self.assertEqual(len(lignes), 3)
        for ligne in lignes:
            self.assertNotIn('display:none', ligne)

    def test_la_bande_ouverte_se_declare_deja_chargee(self):
        """Sinon le préchargement y reverserait les mêmes lignes, en double."""
        self.assertRegex(self._html('&ouverts=1:0'),
                         r'data-chemin="0"[^>]*data-charge="1"|data-charge="1"[^>]*data-chemin="0"')

    def test_un_etat_pris_sur_une_autre_page_est_ignore(self):
        """Un chemin est positionnel : « 0 » est le premier groupe *de la page
        affichée*. Les liens de pagination recopiant les paramètres courants,
        sans le numéro en tête de la valeur, changer de page aurait déplié un
        groupe sans rapport — en silence."""
        html = self._html('&ouverts=2:0')
        self.assertNotRegex(html, r'<tr class="lst-groupe[^"]*open"')
        self.assertEqual(self._nb_lignes(html), 0)

    def test_un_chemin_ouvert_inconnu_ne_casse_rien(self):
        """Une sélection qui a changé depuis que l'état a été noté."""
        self.assertEqual(self._nb_lignes(self._html('&ouverts=1:99')), 0)

    def test_l_etat_deplie_est_retenu_comme_les_filtres(self):
        """C'est ce qui le ramène au retour d'une fiche : la vue redirige vers
        l'URL portant la sélection retenue, et `ouverts` en fait partie."""
        self.client.get(self.url + '&ouverts=1:0')
        reponse = self.client.get(reverse('facturation:list'))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('ouverts=1%3A0', reponse['Location'])

    def test_les_bandes_annoncent_leur_taille(self):
        """Le navigateur s'en sert pour renoncer au préchargement quand la page
        est énorme (MAX_LIGNES_PRECHARGEES). Sans cet attribut il précharge
        tout, et on retombe sur la page de plusieurs méga-octets."""
        html = self._html()
        self.assertIn('data-total="3"', html)
        self.assertIn('data-total="2"', html)

    def test_sans_regroupement_les_lignes_sont_toujours_la(self):
        """Le chargement différé ne concerne que le mode groupé."""
        reponse = self.client.get(reverse('facturation:list') + '?filter=')
        self.assertEqual(self._nb_lignes(reponse.content.decode()), 5)

    def test_deplier_ne_derange_pas_la_selection_retenue(self):
        """Le dépliage emporte la sélection courante : la mémoire la retient
        comme d'habitude et rend bien les lignes du groupe."""
        from core.memoire_listing import PREFIXE_CLE
        self.client.get(self.url)                      # mémorise le regroupement
        cle = PREFIXE_CLE + reverse('facturation:list')
        retenue = self.client.session[cle]

        reponse = self.client.get(self.url + '&_groupe=0')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self._nb_lignes(reponse.content.decode()), 3)
        self.assertEqual(self.client.session[cle], retenue)

    def test_un_depliage_en_ajax_n_efface_pas_la_selection_retenue(self):
        """Une requête AJAX sans paramètre est le signal d'« Effacer » : la
        mémoire oublie la sélection. Un dépliage n'est pas un effacement, et
        `core.memoire_listing` l'écarte sur la seule présence de `_groupe`.

        Le navigateur ne pose pas cet en-tête aujourd'hui — un `<tr>` hors d'un
        `<table>` serait jeté par l'analyseur HTML, voir listing_groupes.js. Le
        garde-fou tient pour le jour où ce choix changera : sans lui, ouvrir un
        groupe effacerait le filtre de la liste.
        """
        from core.memoire_listing import PREFIXE_CLE
        self.client.get(self.url)
        cle = PREFIXE_CLE + reverse('facturation:list')
        self.assertIn(cle, self.client.session)

        self.client.get(reverse('facturation:list') + '?_groupe=0',
                        headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertIn(cle, self.client.session,
                      'le dépliage a été pris pour un « Effacer »')



class TestUnGrosGroupeArriveParLots(TestCase):
    """Déplier un groupe énorme ne doit pas tout rendre d'un coup.

    Un groupe de trente mille lignes prenait plus d'une demi-minute et pesait
    près de quarante méga-octets : le plafond de pages groupées ne protège que
    le *nombre de groupes*, jamais la taille de l'un d'eux. Le serveur n'en rend
    donc qu'un lot, clos par une entrée « Charger plus » qui porte le rang du
    suivant (core.listing.TAILLE_LOT_GROUPE).
    """

    def setUp(self):
        from django.utils import timezone
        from core.listing import TAILLE_LOT_GROUPE
        from facturation.models import Facture
        from patients.models import Patient

        self.lot = TAILLE_LOT_GROUPE
        self.reste = 10

        User.objects.create_superuser('su_lots', password='x')
        self.client = Client()
        self.client.login(username='su_lots', password='x')

        patient = Patient.objects.create(
            nom='Lots', prenoms='Patient', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000')
        # Un groupe plus grand qu'un lot, et un second qui tient tout entier.
        for statut, combien in (('emise', self.lot + self.reste), ('payee', 2)):
            for _ in range(combien):
                Facture.objects.create(
                    patient=patient, type_facture='consultation', statut=statut,
                    montant_total=1000, date_emission=timezone.now())
        self.url = reverse('facturation:list') + '?filter=&group=statut'

    def _html(self, suffixe=''):
        reponse = self.client.get(self.url + suffixe)
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    @staticmethod
    def _nb_lignes(html):
        return html.count('<td data-col="1" class="td-num">')

    def test_un_gros_groupe_n_arrive_pas_d_un_bloc(self):
        self.assertEqual(self._nb_lignes(self._html('&_groupe=0')), self.lot)

    def test_l_entree_charger_plus_dit_ou_reprendre(self):
        """Le rang du lot suivant, sans quoi « Charger plus » renverrait le
        même lot — et les mêmes lignes, en double."""
        html = self._html('&_groupe=0')
        self.assertIn('class="lst-plus"', html)
        self.assertIn('data-suite="%d"' % self.lot, html)

    def test_l_entree_annonce_ce_qui_reste(self):
        self.assertIn('Charger %d de plus · %d restantes' % (self.reste, self.reste),
                      self._html('&_groupe=0'))

    def test_le_lot_suivant_part_du_decalage(self):
        html = self._html('&_groupe=0&_decalage=%d' % self.lot)
        self.assertEqual(self._nb_lignes(html), self.reste)

    def test_le_dernier_lot_ne_propose_plus_rien(self):
        """Sinon on cliquerait indéfiniment sur un groupe épuisé."""
        self.assertNotIn('class="lst-plus"',
                         self._html('&_groupe=0&_decalage=%d' % self.lot))

    def test_un_groupe_entier_n_a_pas_d_entree(self):
        """Le second groupe tient dans un lot : rien à proposer."""
        html = self._html('&_groupe=1')
        self.assertEqual(self._nb_lignes(html), 2)
        self.assertNotIn('class="lst-plus"', html)

    def test_un_decalage_illisible_repart_du_debut(self):
        """Il vient de l'URL, donc de n'importe où. Mieux vaut le premier lot
        qu'une erreur de serveur."""
        self.assertEqual(self._nb_lignes(self._html('&_groupe=0&_decalage=zzz')),
                         self.lot)

    def test_un_decalage_negatif_aussi(self):
        self.assertEqual(self._nb_lignes(self._html('&_groupe=0&_decalage=-5')),
                         self.lot)

    def test_un_groupe_restaure_ouvert_revient_sur_son_premier_lot(self):
        """On retient qu'il était ouvert, pas jusqu'où on l'avait déroulé."""
        html = self._html('&ouverts=1:0')
        self.assertEqual(self._nb_lignes(html), self.lot)
        self.assertIn('data-suite="%d"' % self.lot, html)


class TestLePrechargementSArreteALaPage(TestCase):
    """Précharger, ce n'est pas tout charger.

    `_groupe=*` rend les lignes de tous les groupes **de la page affichée**, et
    d'eux seuls. Sans cette borne, un regroupement à mille groupes ramènerait
    toute la sélection à chaque affichage : exactement la page de plusieurs
    méga-octets que le chargement différé avait supprimée.
    """

    def setUp(self):
        from django.utils import timezone
        from facturation.models import Facture
        from patients.models import Patient

        patient = Patient.objects.create(
            nom='Borne', prenoms='Page', date_naissance='1990-06-01',
            sexe='F', telephone='0700000000')
        # Un montant distinct par facture : trente groupes d'une ligne.
        for i in range(30):
            Facture.objects.create(
                patient=patient, type_facture='consultation', statut='emise',
                montant_total=1000 + i, date_emission=timezone.now())

    def _page(self, numero, chemin_demande):
        from facturation.models import Facture
        from core.listing import Dimension, paginer_groupes
        dimension = Dimension(
            cle='montant', libelle='Montant',
            valeur=lambda o: str(o.montant_total),
            values=('montant_total',),
            label=lambda ligne: str(ligne['montant_total']))
        return paginer_groupes(Facture.all_objects.all(), [dimension], numero,
                               groupes_par_page=25,
                               chemin_demande=chemin_demande)

    @staticmethod
    def _nb_lignes(arbre):
        return sum(len(n['lignes']) + sum(len(e['lignes']) for e in n['enfants'])
                   for n in arbre)

    def test_la_page_un_ne_precharge_que_ses_vingt_cinq_groupes(self):
        arbre, page, nombre = self._page(1, TOUS_LES_GROUPES)
        self.assertEqual(nombre, 30, 'les trente groupes doivent exister')
        self.assertEqual(len(arbre), 25)
        self.assertEqual(self._nb_lignes(arbre), 25,
                         'le préchargement a débordé sur la page suivante')

    def test_la_derniere_page_ne_precharge_que_son_reste(self):
        arbre, page, nombre = self._page(2, TOUS_LES_GROUPES)
        self.assertEqual(len(arbre), 5)
        self.assertEqual(self._nb_lignes(arbre), 5)

    def test_sans_demande_aucune_ligne_n_est_chargee(self):
        """Le témoin : c'est bien `_groupe=*` qui les amène, pas la page."""
        arbre, page, nombre = self._page(1, None)
        self.assertEqual(len(arbre), 25)
        self.assertEqual(self._nb_lignes(arbre), 0)


class TestLaListeRafraichieReprechargeSesGroupes(TestCase):
    """Un changement de filtre remplace la liste : ses groupes repartent sans
    lignes, et le préchargement doit repartir avec eux.

    Sans ce rappel, la première liste de la session serait instantanée et toutes
    les suivantes feraient attendre à chaque dépliage — le genre de différence
    qu'on met longtemps à relier à sa cause.
    """

    #: Les cinq endroits qui remplacent une liste par AJAX. Chacun rappelle
    #: `lstfInit` pour les filtres ; il doit rappeler le préchargement aussi.
    GABARITS = (
        'templates/includes/listing/page_js.html',
        'templates/includes/subheader.html',
        'templates/gynecologie/list.html',
        'templates/gynecologie/registre_naissance.html',
        'templates/patients/list.html',
    )

    def test_chaque_rafraichissement_relance_le_prechargement(self):
        from pathlib import Path
        from django.conf import settings
        for nom in self.GABARITS:
            texte = Path(settings.BASE_DIR, nom).read_text()
            self.assertIn('window.lstfInit()', texte,
                          f'{nom} ne rafraîchit plus les filtres')
            self.assertIn('window.lstPrecharger()', texte,
                          f'{nom} ne reprécharge pas ses groupes')


class TestLesAdressesStatiquesPortentLaDateDuFichier(TestCase):
    """Un script corrigé doit être réellement rechargé par le navigateur.

    `{% static %}` rendait toujours la même adresse quel que soit le contenu du
    fichier. Une copie gardée par le navigateur servait donc indéfiniment, et
    une correction livrée restait invisible chez qui avait déjà ouvert la page.

    Ce n'est pas théorique : le chargement différé des groupes a été livré avec
    un script qui va chercher les lignes au serveur, là où l'ancien se
    contentait de démasquer des lignes déjà présentes. Les deux se ressemblent
    assez pour que rien ne signale l'erreur — le groupe s'ouvrait et restait
    vide.
    """

    def _url(self, nom):
        from django.contrib.staticfiles.storage import staticfiles_storage
        return staticfiles_storage.url(nom)

    def test_une_adresse_porte_une_version(self):
        import re
        adresse = self._url('js/listing_groupes.js')
        self.assertRegex(adresse, r'^/static/js/listing_groupes\.js\?v=\d+$')

    def test_deux_fichiers_differents_ont_des_versions_differentes(self):
        """Une version constante ne vaudrait pas mieux que pas de version."""
        import os
        from django.contrib.staticfiles import finders
        a = self._url('js/listing_groupes.js')
        b = self._url('css/global.css')
        self.assertNotEqual(a.split('?v=')[1], b.split('?v=')[1],
                            'les deux fichiers ont la même date, le test ne '
                            'prouve rien — touchez-en un et relancez')
        # La version est bien celle du fichier, pas un nombre quelconque.
        attendue = str(int(os.path.getmtime(finders.find('css/global.css'))))
        self.assertEqual(b.split('?v=')[1], attendue)

    def test_un_fichier_introuvable_rend_une_adresse_nue(self):
        """Mieux vaut une adresse sans version qu'une page qui ne s'affiche
        pas : le cache n'est pas une raison de casser le rendu."""
        self.assertEqual(self._url('js/ce-fichier-n-existe-pas.js'),
                         '/static/js/ce-fichier-n-existe-pas.js')

    def test_les_pages_servent_des_adresses_versionnees(self):
        import re
        User.objects.create_superuser('su_statique', password='x')
        client = Client()
        client.login(username='su_statique', password='x')
        html = client.get(reverse('soins:list') + '?filter=').content.decode()
        adresses = re.findall(r'/static/[^"\' >]+', html)
        self.assertTrue(adresses)
        self.assertEqual([a for a in adresses if '?v=' not in a], [])


class TestLeCatalogueDesChampsNeTriePasLesTables(TestCase):
    """Savoir si une table est petite ne demande pas de la trier.

    Le constructeur de conditions propose les valeurs d'un champ de lien quand
    la table visée reste petite. Il en demandait 201 lignes — une de plus que
    la limite, pour savoir sans compter — mais à travers le tri par défaut du
    modèle. Or ces modèles en ont tous un : patients, factures, rendez-vous,
    hospitalisations. La base devait donc trier la table **entière** avant d'en
    rendre 201, à chaque affichage d'une liste, pour chacun des neuf à onze
    champs de lien.

    Invisible sur un millier de lignes, beaucoup moins sur cent mille. Et ce
    tri ne servait à rien : on ne cherche ici qu'à savoir si la table est
    petite et, si oui, ce qu'elle contient.
    """

    def test_aucun_sondage_ne_trie(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from core.listing import champs_filtrables, champs_pour_navigateur
        from soins.models import Soin

        with CaptureQueriesContext(connection) as requetes:
            champs_pour_navigateur(champs_filtrables(Soin))

        triees = [r['sql'] for r in requetes.captured_queries
                  if 'ORDER BY' in r['sql'].upper()]
        self.assertEqual(
            triees, [],
            'un sondage trie de nouveau la table avant de la plafonner')
        self.assertTrue(requetes.captured_queries,
                        'aucune requête : le test ne prouve rien')

    def test_les_valeurs_proposees_sont_rangees_par_libelle(self):
        """On vient y choisir une valeur : une liste alphabétique se parcourt
        mieux que l'ordre où la base les a rendues — qui, le tri retiré, n'est
        plus garanti du tout."""
        from medecins.models import Departement

        from core.listing import champs_filtrables, champs_pour_navigateur
        from soins.models import Soin

        for code, nom in (('ZZZ', 'Zone de test'), ('AAA', 'Ambulatoire'),
                          ('MMM', 'Médecine interne')):
            Departement.objects.get_or_create(code=code, defaults={'nom': nom})

        catalogue = champs_pour_navigateur(champs_filtrables(Soin))
        departement = next(c for c in catalogue['champs']
                           if c['chemin'] == 'departement')
        libelles = [libelle for _, libelle in departement['choix']]
        self.assertEqual(libelles, sorted(libelles))
        self.assertIn('Ambulatoire', libelles)

    def test_une_table_trop_grande_bascule_en_saisie_d_identifiant(self):
        """Le plafond est ce qui empêche le catalogue d'enfler : au-delà, on
        saisit l'identifiant au lieu de recevoir toute la table."""
        from medecins.models import Departement

        from core.listing import (MAX_CHOIX_LIEN, champs_filtrables,
                                  champs_pour_navigateur)
        from soins.models import Soin

        Departement.objects.bulk_create([
            Departement(code=f'D{i:04d}', nom=f'Service {i:04d}')
            for i in range(MAX_CHOIX_LIEN + 1)])

        catalogue = champs_pour_navigateur(champs_filtrables(Soin))
        departement = next(c for c in catalogue['champs']
                           if c['chemin'] == 'departement')
        self.assertEqual(departement['type'], 'nombre')
        self.assertEqual(departement['choix'], [])


class TestLaMemoireRetientLesFiltresPersonnalises(TestCase):
    """Revenir d'une fiche doit rendre la sélection **entière**.

    La mémoire des listes retenait `cond_…` et `mode_cond`, deux noms que rien
    n'a jamais écrits : le constructeur de conditions envoie `cf`, `co`, `cv`
    et `cm`. Les deux moitiés ne se sont donc jamais rencontrées. On posait un
    filtre personnalisé, on ouvrait une fiche, on revenait — et il avait
    disparu, sur les six listes qui offrent la fonction.
    """

    def setUp(self):
        User.objects.create_superuser('su_memo_perso', password='x')
        self.client = Client()
        self.client.login(username='su_memo_perso', password='x')
        self.url = reverse('soins:list')

    SELECTION = '?filter=&cf=motif&co=contient&cv=pansement'

    def test_la_condition_revient_avec_la_selection(self):
        self.client.get(self.url + self.SELECTION)
        retour = self.client.get(self.url)          # retour d'une fiche
        self.assertEqual(retour.status_code, 302)
        for morceau in ('cf=motif', 'co=contient', 'cv=pansement'):
            self.assertIn(morceau, retour['Location'])

    def test_le_mode_de_combinaison_revient_aussi(self):
        """Sans lui, deux conditions retrouvées en ET au lieu de OU ne rendent
        pas la même liste — et rien ne le dit."""
        self.client.get(self.url + self.SELECTION + '&cm=ou')
        retour = self.client.get(self.url)
        self.assertIn('cm=ou', retour['Location'])

    def test_plusieurs_conditions_reviennent_toutes(self):
        """Elles voyagent en listes parallèles : n'en retenir qu'une changerait
        le résultat sans prévenir."""
        self.client.get(
            self.url + '?filter='
            '&cf=motif&co=contient&cv=pansement'
            '&cf=nom&co=contient&cv=pied')
        cible = self.client.get(self.url)['Location']
        self.assertEqual(cible.count('cf='), 2)
        self.assertIn('cv=pied', cible)

    def test_effacer_oublie_bien_la_condition(self):
        """« Effacer » rafraîchit la liste en AJAX sans aucun paramètre : c'est
        ce qui le distingue d'un retour de fiche. Il doit tout oublier."""
        from core.memoire_listing import PREFIXE_CLE
        self.client.get(self.url + self.SELECTION)
        self.assertIn(PREFIXE_CLE + self.url, self.client.session)

        self.client.get(self.url,
                        headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertNotIn(PREFIXE_CLE + self.url, self.client.session)
