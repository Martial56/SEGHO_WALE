from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from facturation.models import Facture
from patients.models import Patient

from .models import ProcedureSoin, Soin
from .regles import cloturer_si_procedures_terminees, demarrer_soin_de_facture
from .views import (_has_at_least_one_ligne, _parse_prix,
                    _save_procedures_from_lignes, _statut_apres_enregistrement,
                    _sync_procedures)


# ─── Helpers de création ───────────────────────────────────────────────────────

def _patient(suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance='1990-06-01', sexe='M',
        telephone='0700000000',
    )


def _soin(patient=None, statut='brouillon', facture=None, creator=None):
    return Soin.objects.create(
        patient=patient or _patient(),
        motif='Motif de test',
        statut=statut,
        facture=facture,
        cree_par=creator,
    )


def _facture(patient, statut='emise', montant_total=Decimal('5000')):
    return Facture.objects.create(
        patient=patient,
        type_facture='soins',
        statut=statut,
        montant_total=montant_total,
    )


def _procedure(soin=None, patient=None, statut='brouillon', prix=Decimal('1000')):
    return ProcedureSoin.objects.create(
        soin=soin,
        patient=patient or (soin.patient if soin else _patient()),
        prix=prix,
        statut=statut,
    )


def _service(nom='Pansement', prix=Decimal('1000')):
    from services.models import Articleservice
    return Articleservice.objects.create(nom=nom, prix_vente=prix)


def _employe(nom='Kone', prenoms='Awa'):
    from employer.models import Employe
    return Employe.objects.create(nom=nom, prenoms=prenoms, date_embauche='2020-01-01')


def _soins_user(username, perms=()):
    user = User.objects.create_user(username, password='x')
    for codename in perms:
        # Plusieurs apps définissent des permissions du même nom (ex. can_creer_facture
        # existe aussi sur hospitalisation.Hospitalisation) : on précise l'app.
        perm = Permission.objects.get(codename=codename, content_type__app_label='soins')
        user.user_permissions.add(perm)
    return user


# ─── Tests génération de numéros uniques ───────────────────────────────────────

class TestNumerosUniques(TestCase):

    def setUp(self):
        self.patient = _patient('A')

    def test_deux_soins_numeros_distincts(self):
        s1 = _soin(self.patient)
        s2 = _soin(self.patient)
        self.assertNotEqual(s1.numero, s2.numero)

    def test_format_numero_soin(self):
        s = _soin(self.patient)
        annee_courte = str(timezone.now().year)[2:]
        prefix = f'SN{annee_courte}'
        self.assertTrue(s.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{s.numero}'")
        suffixe = s.numero[len(prefix):]
        self.assertEqual(len(suffixe), 5, "Le suffixe doit être sur 5 chiffres")
        self.assertTrue(suffixe.isdigit())

    def test_deux_procedures_numeros_distincts(self):
        p1 = _procedure(patient=self.patient)
        p2 = _procedure(patient=self.patient)
        self.assertNotEqual(p1.numero, p2.numero)

    def test_format_numero_procedure(self):
        p = _procedure(patient=self.patient)
        annee_courte = str(timezone.now().year)[2:]
        prefix = f'DP{annee_courte}'
        self.assertTrue(p.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{p.numero}'")
        suffixe = p.numero[len(prefix):]
        self.assertEqual(len(suffixe), 5, "Le suffixe doit être sur 5 chiffres")
        self.assertTrue(suffixe.isdigit())


# ─── Tests des fonctions utilitaires de views.py ───────────────────────────────

class TestHasAtLeastOneLigne(TestCase):

    def test_vrai_si_une_ligne_a_un_service(self):
        post_data = {'lignes[0][service]': '3', 'lignes[0][patient]': '1'}
        self.assertTrue(_has_at_least_one_ligne(post_data))

    def test_faux_si_service_vide(self):
        post_data = {'lignes[0][service]': '', 'lignes[0][patient]': '1'}
        self.assertFalse(_has_at_least_one_ligne(post_data))

    def test_faux_si_aucune_ligne(self):
        self.assertFalse(_has_at_least_one_ligne({}))

    def test_vrai_si_une_parmi_plusieurs_lignes_valide(self):
        post_data = {
            'lignes[0][service]': '',
            'lignes[1][service]': '7',
        }
        self.assertTrue(_has_at_least_one_ligne(post_data))


class TestParsePrix(TestCase):

    def test_valeur_vide_retourne_zero(self):
        self.assertEqual(_parse_prix(''), 0)
        self.assertEqual(_parse_prix(None), 0)

    def test_valeur_numerique_simple(self):
        self.assertEqual(_parse_prix('1500'), 1500)

    def test_ignore_les_caracteres_non_numeriques(self):
        self.assertEqual(_parse_prix('1 500 FCFA'), 1500)

    def test_uniquement_texte_retourne_zero(self):
        self.assertEqual(_parse_prix('FCFA'), 0)


class TestSyncProcedures(TestCase):

    def test_met_a_jour_toutes_les_procedures_du_soin(self):
        soin = _soin(statut='en_cours')
        p1 = _procedure(soin=soin, statut='en_cours')
        p2 = _procedure(soin=soin, statut='en_cours')
        autre_soin = _soin(statut='en_cours')
        p3 = _procedure(soin=autre_soin, statut='en_cours')

        _sync_procedures(soin, 'termine')

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        self.assertEqual(p1.statut, 'termine')
        self.assertEqual(p2.statut, 'termine')
        self.assertEqual(p3.statut, 'en_cours',
                         "Les procédures d'un autre soin ne doivent pas être affectées")


# ─── Tests de la vue soins_administrer ─────────────────────────────────────────

class TestSoinsAdministrerView(TestCase):

    def setUp(self):
        self.patient = _patient('B')
        self.superuser = User.objects.create_superuser('su_sa', password='x')

    def _client_avec_perm(self, username='u_sa_ok'):
        user = _soins_user(username, perms=['can_administrer_soin'])
        client = Client()
        client.login(username=username, password='x')
        return client

    def test_refuse_sans_permission(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='payee'))
        user = _soins_user('u_sa_noperm')
        client = Client()
        client.login(username='u_sa_noperm', password='x')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours',
                         "Le statut ne doit pas changer sans la permission can_administrer_soin")

    def test_refuse_si_statut_pas_en_cours(self):
        soin = _soin(self.patient, statut='brouillon', facture=_facture(self.patient, statut='payee'))
        client = self._client_avec_perm()
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'brouillon')

    def test_refuse_si_facture_non_payee(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='emise'))
        client = self._client_avec_perm('u_sa_impaye')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')

    def test_refuse_sans_facture(self):
        soin = _soin(self.patient, statut='en_cours', facture=None)
        client = self._client_avec_perm('u_sa_sansfacture')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')

    def test_autorise_avec_facture_payee_et_permission(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='payee'))
        procedure = _procedure(soin=soin, statut='en_cours')
        client = self._client_avec_perm('u_sa_ok2')
        # Administrer consigne désormais qui a réalisé la ligne.
        resp = client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}),
                           {'infirmier_%s' % procedure.pk: _employe().pk})
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        procedure.refresh_from_db()
        self.assertEqual(soin.statut, 'termine')
        self.assertIsNotNone(soin.date_termine)
        self.assertEqual(procedure.statut, 'termine',
                         "Les procédures du soin doivent être synchronisées à 'termine'")


# ─── Tests de la vue soins_creer_facture ───────────────────────────────────────

class TestSoinsCreerFactureView(TestCase):

    def setUp(self):
        self.patient = _patient('C')

    def _client_avec_perm(self, username='u_scf_ok'):
        _soins_user(username, perms=['can_creer_facture'])
        client = Client()
        client.login(username=username, password='x')
        return client

    def test_refuse_sans_permission(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        _procedure(soin=soin, prix=Decimal('2000'))
        user = _soins_user('u_scf_noperm')
        client = Client()
        client.login(username='u_scf_noperm', password='x')
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_refuse_si_statut_incorrect(self):
        soin = _soin(self.patient, statut='brouillon')
        _procedure(soin=soin, prix=Decimal('2000'))
        client = self._client_avec_perm()
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_refuse_sans_procedures(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        client = self._client_avec_perm('u_scf_sansligne')
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_cree_facture_avec_permission_et_procedures(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        _procedure(soin=soin, prix=Decimal('2000'))
        _procedure(soin=soin, prix=Decimal('3000'))
        client = self._client_avec_perm('u_scf_ok2')
        resp = client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        self.assertIsNotNone(soin.facture_id)
        self.assertEqual(soin.facture.montant_total, Decimal('5000'))

    def test_redirige_vers_facture_existante_sans_recreer(self):
        facture = _facture(self.patient)
        soin = _soin(self.patient, statut='en_attente_de_paiement', facture=facture)
        client = self._client_avec_perm('u_scf_deja')
        resp = client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        self.assertEqual(soin.facture_id, facture.pk)


# ─── Tests du verrouillage de la vue soins_edit ────────────────────────────────

class TestSoinsEditLocking(TestCase):

    def setUp(self):
        self.patient = _patient('D')
        self.superuser = User.objects.create_superuser('su_se', password='x')
        # Ce verrou-ci porte sur le statut, pas sur les droits : l'utilisateur a
        # bien la permission de modifier, c'est l'état du dossier qui l'arrête.
        self.user = _soins_user('u_se', perms=('change_soin',))

    def test_edit_bloque_si_hospitalisation_liee_pour_non_superuser(self):
        from hospitalisation.models import Hospitalisation
        from medecins.models import Medecin, Specialite
        from employer.models import Employe
        specialite, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
        employe = Employe.objects.create(
            nom='Doc', prenoms='Test', telephone='0700000001', date_embauche='2020-01-01',
        )
        medecin = Medecin.objects.create(employe=employe, specialite=specialite)
        hosp = Hospitalisation.objects.create(
            patient=self.patient, medecin_traitant=medecin,
            date_admission=timezone.now(), statut='hospitalise',
        )
        soin = _soin(self.patient, statut='brouillon')
        soin.hospitalisation = hosp
        soin.save(update_fields=['hospitalisation'])

        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('soins:detail', kwargs={'pk': soin.pk}))

    def test_edit_autorise_pour_superuser_malgre_hospitalisation(self):
        from hospitalisation.models import Hospitalisation
        from medecins.models import Medecin, Specialite
        from employer.models import Employe
        specialite, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
        employe = Employe.objects.create(
            nom='Doc', prenoms='Test2', telephone='0700000001', date_embauche='2020-01-01',
        )
        medecin = Medecin.objects.create(employe=employe, specialite=specialite)
        hosp = Hospitalisation.objects.create(
            patient=self.patient, medecin_traitant=medecin,
            date_admission=timezone.now(), statut='hospitalise',
        )
        soin = _soin(self.patient, statut='brouillon')
        soin.hospitalisation = hosp
        soin.save(update_fields=['hospitalisation'])

        client = Client()
        client.login(username='su_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_edit_bloque_si_statut_non_brouillon_pour_non_superuser(self):
        soin = _soin(self.patient, statut='en_cours')
        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('soins:detail', kwargs={'pk': soin.pk}))

    def test_edit_autorise_si_statut_brouillon(self):
        soin = _soin(self.patient, statut='brouillon')
        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 200)


# ─── Le paiement démarre le soin ET ses procédures ─────────────────────────────

class TestPaiementDemarreLesProcedures(TestCase):
    """Une facture réglée doit sortir le soin et ses lignes de l'attente.

    Avant, seul le soin passait « en cours » et seulement par l'encaissement de
    la caisse : les procédures restaient en brouillon jusqu'à sauter d'un coup à
    « terminé » à l'administration, sans jamais passer par « en cours ».
    """

    def setUp(self):
        self.patient = _patient('Pay')
        self.caissier = User.objects.create_superuser('su_pay', password='x')
        self.client = Client()
        self.client.login(username='su_pay', password='x')

    def _soin_facture(self, montant=Decimal('3000'), nb_lignes=2):
        facture = _facture(self.patient, statut='emise', montant_total=montant)
        soin = _soin(self.patient, statut='en_attente_de_paiement', facture=facture)
        procedures = [_procedure(soin=soin, statut='brouillon') for _ in range(nb_lignes)]
        return soin, facture, procedures

    def _statuts(self, soin):
        soin.refresh_from_db()
        return soin.statut, sorted(
            ProcedureSoin.objects.filter(soin=soin).values_list('statut', flat=True))

    def test_encaissement_met_le_soin_et_ses_procedures_en_cours(self):
        soin, facture, _ = self._soin_facture()
        self.client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                         {'pay_montant': '3000', 'pay_mode': 'especes'})
        self.assertEqual(self._statuts(soin), ('en_cours', ['en_cours', 'en_cours']))

    def test_paiement_partiel_ne_demarre_rien(self):
        soin, facture, _ = self._soin_facture()
        self.client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                         {'pay_montant': '1000', 'pay_mode': 'especes'})
        self.assertEqual(self._statuts(soin),
                         ('en_attente_de_paiement', ['brouillon', 'brouillon']))

    def test_bouton_marquer_payee_demarre_aussi(self):
        """Le second chemin : la fiche facture, sans encaissement saisi."""
        soin, facture, _ = self._soin_facture()
        self.client.post(reverse('facturation:edit', kwargs={'pk': facture.pk}),
                         {'action_payer': '1'})
        self.assertEqual(self._statuts(soin), ('en_cours', ['en_cours', 'en_cours']))

    def test_une_procedure_annulee_ne_revit_pas(self):
        soin, facture, procedures = self._soin_facture(nb_lignes=2)
        procedures[0].statut = 'annule'
        procedures[0].save(update_fields=['statut'])
        self.client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                         {'pay_montant': '3000', 'pay_mode': 'especes'})
        self.assertEqual(self._statuts(soin), ('en_cours', ['annule', 'en_cours']))

    def test_un_soin_deja_termine_nest_pas_rouvert(self):
        facture = _facture(self.patient, statut='payee')
        soin = _soin(self.patient, statut='termine', facture=facture)
        self.assertIsNone(demarrer_soin_de_facture(facture))

    def test_facture_sans_soin_ne_casse_rien(self):
        facture = _facture(self.patient, statut='payee')
        self.assertIsNone(demarrer_soin_de_facture(facture))

    def test_parcours_complet_jusqua_ladministration(self):
        soin, facture, procedures = self._soin_facture()
        self.client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                         {'pay_montant': '3000', 'pay_mode': 'especes'})
        self.assertEqual(self._statuts(soin), ('en_cours', ['en_cours', 'en_cours']))
        infirmier = _employe()
        self.client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}),
                         {'infirmier_%s' % p.pk: infirmier.pk for p in procedures})
        self.assertEqual(self._statuts(soin), ('termine', ['termine', 'termine']))


# ─── Toutes les lignes terminées ferment le soin ──────────────────────────────

class TestClotureAutomatiqueDuSoin(TestCase):
    """Le miroir de l'administration : « terminé » remonte des lignes au soin.

    Descendre existait déjà — administrer un soin termine ses procédures. Rien
    ne remontait : un dossier de dix lignes toutes terminées restait « en
    cours » indéfiniment.
    """

    def setUp(self):
        self.patient = _patient('Clo')
        self.user = _soins_user('u_clo', perms=('can_administrer_soin', 'change_proceduresoin'))
        self.infirmier = _employe()
        self.client = Client()
        self.client.login(username='u_clo', password='x')

    def _dossier(self, statuts, statut_soin='en_cours', hospitalisation=None):
        soin = _soin(self.patient, statut=statut_soin)
        if hospitalisation is not None:
            soin.hospitalisation = hospitalisation
            soin.save(update_fields=['hospitalisation'])
        procedures = [_procedure(soin=soin, statut=s) for s in statuts]
        return soin, procedures

    def _terminer(self, proc, infirmier=None):
        return self.client.post(
            reverse('soins:procedure_terminer', kwargs={'pk': proc.pk}),
            {'infirmier': (infirmier or self.infirmier).pk})

    def _statut(self, soin):
        soin.refresh_from_db()
        return soin.statut

    def test_derniere_ligne_terminee_ferme_le_soin(self):
        soin, procs = self._dossier(['termine', 'termine', 'en_cours'])
        self._terminer(procs[2])
        self.assertEqual(self._statut(soin), 'termine')

    def test_soin_reste_en_cours_tant_quune_ligne_attend(self):
        soin, procs = self._dossier(['en_cours', 'en_cours', 'en_cours'])
        self._terminer(procs[0])
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_une_ligne_en_brouillon_bloque_aussi(self):
        soin, procs = self._dossier(['brouillon', 'en_cours'])
        self._terminer(procs[1])
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_les_lignes_annulees_ne_bloquent_pas(self):
        soin, procs = self._dossier(['annule', 'en_cours'])
        self._terminer(procs[1])
        self.assertEqual(self._statut(soin), 'termine')

    def test_annuler_la_derniere_ligne_en_attente_ferme_le_soin(self):
        """Sans cet appel le dossier restait coincé exactement comme avant."""
        soin, procs = self._dossier(['termine', 'en_cours'])
        self.client.post(reverse('soins:procedure_annuler', kwargs={'pk': procs[1].pk}))
        self.assertEqual(self._statut(soin), 'termine')

    def test_un_dossier_tout_annule_ne_se_ferme_pas(self):
        soin, procs = self._dossier(['annule', 'en_cours'])
        self.client.post(reverse('soins:procedure_annuler', kwargs={'pk': procs[1].pk}))
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_un_soin_sans_ligne_ne_se_ferme_pas(self):
        soin, _ = self._dossier([])
        self.assertIsNone(cloturer_si_procedures_terminees(soin, self.user))
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_un_soin_pas_encore_paye_ne_se_ferme_pas(self):
        soin, procs = self._dossier(['termine'], statut_soin='en_attente_de_paiement')
        self.assertIsNone(cloturer_si_procedures_terminees(soin, self.user))
        self.assertEqual(self._statut(soin), 'en_attente_de_paiement')

    def test_un_dossier_dhospitalisation_reste_ouvert(self):
        """Il reçoit ses procédures visite après visite : le fermer le gèlerait."""
        from hospitalisation.models import Hospitalisation
        hosp = Hospitalisation.objects.create(
            patient=self.patient, date_admission=timezone.now())
        soin, procs = self._dossier(['termine', 'en_cours'], hospitalisation=hosp)
        self._terminer(procs[1])
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_qui_a_termine_et_quand(self):
        soin, procs = self._dossier(['termine', 'en_cours'])
        self._terminer(procs[1])
        soin.refresh_from_db()
        self.assertEqual(soin.termine_par, self.user)
        self.assertIsNotNone(soin.date_termine)

    def test_les_lignes_deja_terminees_ne_sont_pas_retouchees(self):
        """La clôture remonte, elle ne redescend pas : une ligne annulée reste annulée."""
        soin, procs = self._dossier(['annule', 'en_cours'])
        self._terminer(procs[1])
        self.assertEqual(self._statut(soin), 'termine')
        procs[0].refresh_from_db()
        self.assertEqual(procs[0].statut, 'annule')


# ─── Le formulaire ne fait plus redescendre un dossier ────────────────────────

class TestStatutNeRedescendPas(TestCase):
    """Rouvrir « Modifier » ramenait un soin payé en « en attente de paiement ».

    La facture existant déjà, aucune autre ne pouvait être créée et le bouton
    « Administrer » avait disparu : le dossier restait bloqué sans issue.
    """

    def test_depuis_brouillon_enregistrer_envoie_a_la_caisse(self):
        self.assertEqual(_statut_apres_enregistrement('brouillon', 'enregistrer'),
                         'en_attente_de_paiement')

    def test_depuis_brouillon_une_sauvegarde_simple_ny_touche_pas(self):
        self.assertEqual(_statut_apres_enregistrement('brouillon', 'save'), 'brouillon')

    def test_un_soin_paye_reste_en_cours(self):
        self.assertEqual(_statut_apres_enregistrement('en_cours', 'enregistrer'), 'en_cours')

    def test_un_soin_termine_reste_termine(self):
        self.assertEqual(_statut_apres_enregistrement('termine', 'save'), 'termine')

    def test_un_soin_deja_en_caisse_ne_repart_pas_en_brouillon(self):
        self.assertEqual(_statut_apres_enregistrement('en_attente_de_paiement', 'save'),
                         'en_attente_de_paiement')

    def test_bout_en_bout_modifier_un_soin_paye(self):
        patient = _patient('Reg')
        service = _service()
        facture = _facture(patient, statut='payee')
        soin = _soin(patient, statut='en_cours', facture=facture)
        proc = _procedure(soin=soin, statut='en_cours')
        proc.soin_type = service
        proc.save()
        User.objects.create_superuser('su_reg', password='x')
        client = Client()
        client.login(username='su_reg', password='x')
        client.post(reverse('soins:edit', kwargs={'pk': soin.pk}), {
            'patient': patient.pk,
            'statut': 'en_cours',
            'action': 'enregistrer',
            'lignes[0][pk]': proc.pk,
            'lignes[0][patient]': patient.pk,
            'lignes[0][service]': service.pk,
            'lignes[0][prix]': '1 000 CFA',
        })
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')
        self.assertEqual(soin.facture_id, facture.pk)


# ─── Les lignes sont modifiées, pas recréées ──────────────────────────────────

class TestLignesMisesAJourEnPlace(TestCase):
    """Tout effacer pour tout recréer ramenait chaque ligne en brouillon,
    coupait le lien vers la facture réglée et brûlait une série de numéros."""

    def setUp(self):
        self.patient = _patient('Lig')
        self.service = _service()
        self.soin = _soin(self.patient, statut='en_cours')

    def _poster(self, lignes):
        post = {}
        for i, ligne in enumerate(lignes):
            for cle, valeur in ligne.items():
                post['lignes[%s][%s]' % (i, cle)] = valeur
        _save_procedures_from_lignes(self.soin, post)

    def _ligne(self, proc, prix='1000'):
        return {'pk': proc.pk, 'patient': self.patient.pk,
                'service': self.service.pk, 'prix': prix}

    def _avec_service(self, **kwargs):
        proc = _procedure(soin=self.soin, **kwargs)
        proc.soin_type = self.service
        proc.save()
        return proc

    def test_une_ligne_existante_garde_son_identite(self):
        proc = self._avec_service(statut='en_cours')
        self._poster([self._ligne(proc, prix='2000')])
        self.assertEqual(ProcedureSoin.objects.filter(soin=self.soin).count(), 1)
        apres = ProcedureSoin.objects.get(pk=proc.pk)
        self.assertEqual(apres.numero, proc.numero)
        self.assertEqual(apres.statut, 'en_cours')
        self.assertEqual(apres.prix, Decimal('2000'))

    def test_la_facture_de_la_ligne_est_conservee(self):
        facture = _facture(self.patient, statut='payee')
        proc = self._avec_service(statut='en_cours')
        proc.facture = facture
        proc.save()
        self._poster([self._ligne(proc)])
        proc.refresh_from_db()
        self.assertEqual(proc.facture_id, facture.pk)

    def test_linfirmier_de_la_ligne_est_bien_enregistre(self):
        proc = self._avec_service(statut='en_cours')
        infirmier = _employe()
        ligne = self._ligne(proc)
        ligne['infirmier'] = infirmier.pk
        self._poster([ligne])
        proc.refresh_from_db()
        self.assertEqual(proc.infirmier_id, infirmier.pk)

    def test_une_ligne_sans_pk_est_creee(self):
        self._poster([{'patient': self.patient.pk, 'service': self.service.pk, 'prix': '500'}])
        self.assertEqual(ProcedureSoin.objects.filter(soin=self.soin).count(), 1)

    def test_une_ligne_en_brouillon_retiree_disparait(self):
        proc = _procedure(soin=self.soin, statut='brouillon')
        self._poster([])
        self.assertFalse(ProcedureSoin.objects.filter(pk=proc.pk).exists())

    def test_une_ligne_facturee_retiree_est_conservee(self):
        """Elle a une contrepartie sur la facture que le formulaire n'efface pas."""
        facture = _facture(self.patient, statut='payee')
        proc = _procedure(soin=self.soin, statut='brouillon')
        proc.facture = facture
        proc.save()
        self._poster([])
        self.assertTrue(ProcedureSoin.objects.filter(pk=proc.pk).exists())

    def test_une_ligne_engagee_retiree_est_conservee(self):
        proc = _procedure(soin=self.soin, statut='en_cours')
        self._poster([])
        self.assertTrue(ProcedureSoin.objects.filter(pk=proc.pk).exists())

    def test_trois_enregistrements_ne_creent_pas_trois_lignes(self):
        proc = self._avec_service(statut='brouillon')
        for _ in range(3):
            self._poster([self._ligne(proc)])
        self.assertEqual(ProcedureSoin.objects.filter(soin=self.soin).count(), 1)
        proc.refresh_from_db()
        self.assertEqual(proc.numero, ProcedureSoin.objects.get(soin=self.soin).numero)


# ─── L'infirmier se désigne au moment d'administrer ───────────────────────────

class TestAdministrerConsigneLInfirmier(TestCase):
    """Le geste qui termine le soin est aussi celui qui trace qui l'a réalisé."""

    def setUp(self):
        self.patient = _patient('Adm')
        self.infirmier = _employe()
        self.facture = _facture(self.patient, statut='payee')
        self.soin = _soin(self.patient, statut='en_cours', facture=self.facture)
        self.p1 = _procedure(soin=self.soin, statut='en_cours')
        self.p2 = _procedure(soin=self.soin, statut='en_cours')
        _soins_user('u_adm', perms=('can_administrer_soin',))
        self.client = Client()
        self.client.login(username='u_adm', password='x')

    def _administrer(self, donnees, client=None):
        return (client or self.client).post(
            reverse('soins:administrer', kwargs={'pk': self.soin.pk}), donnees)

    def _statut(self):
        self.soin.refresh_from_db()
        return self.soin.statut

    def test_sans_infirmier_le_soin_nest_pas_termine(self):
        self._administrer({})
        self.assertEqual(self._statut(), 'en_cours')

    def test_un_infirmier_different_par_ligne(self):
        autre = _employe('Traore', 'Ali')
        self._administrer({'infirmier_%s' % self.p1.pk: self.infirmier.pk,
                           'infirmier_%s' % self.p2.pk: autre.pk})
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.infirmier_id, self.infirmier.pk)
        self.assertEqual(self.p2.infirmier_id, autre.pk)
        self.assertEqual(self._statut(), 'termine')

    def test_linfirmier_responsable_du_dossier_est_renseigne(self):
        self._administrer({'infirmier_%s' % self.p1.pk: self.infirmier.pk,
                           'infirmier_%s' % self.p2.pk: self.infirmier.pk})
        self.soin.refresh_from_db()
        self.assertEqual(self.soin.infirmier_id, self.infirmier.pk)

    def test_un_infirmier_inconnu_est_refuse(self):
        self._administrer({'infirmier_%s' % self.p1.pk: 999999,
                           'infirmier_%s' % self.p2.pk: self.infirmier.pk})
        self.assertEqual(self._statut(), 'en_cours')

    def test_une_ligne_deja_annulee_nest_pas_reclamee_ni_terminee(self):
        self.p2.statut = 'annule'
        self.p2.save(update_fields=['statut'])
        self._administrer({'infirmier_%s' % self.p1.pk: self.infirmier.pk})
        self.p2.refresh_from_db()
        self.assertEqual(self._statut(), 'termine')
        self.assertEqual(self.p2.statut, 'annule')

    def test_sans_la_permission_rien_ne_bouge(self):
        _soins_user('u_sans')
        sans = Client()
        sans.login(username='u_sans', password='x')
        self._administrer({'infirmier_%s' % self.p1.pk: self.infirmier.pk,
                           'infirmier_%s' % self.p2.pk: self.infirmier.pk}, client=sans)
        self.assertEqual(self._statut(), 'en_cours')

    def test_la_fiche_affiche_un_selecteur_par_ligne(self):
        """Le panneau ne se rendait dans aucun test : toutes les fiches y étaient
        en brouillon, donc `peut_administrer` faux et le bloc jamais atteint."""
        _soins_user('u_vue', perms=('can_administrer_soin', 'view_soin'))
        vue = Client()
        vue.login(username='u_vue', password='x')
        page = vue.get(reverse('soins:detail', kwargs={'pk': self.soin.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="btn-administrer"')
        self.assertContains(page, 'name="infirmier_%s"' % self.p1.pk)
        self.assertContains(page, 'name="infirmier_%s"' % self.p2.pk)
        self.assertContains(page, str(self.infirmier.nom))

    def test_la_fiche_dune_procedure_affiche_le_selecteur(self):
        _soins_user('u_vue_p', perms=('can_administrer_soin', 'view_proceduresoin'))
        vue = Client()
        vue.login(username='u_vue_p', password='x')
        page = vue.get(reverse('soins:procedure_detail', kwargs={'pk': self.p1.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="btn-terminer"')
        self.assertContains(page, 'id="form-terminer"')
        self.assertContains(page, 'name="infirmier"')


# ─── Annuler un soin ──────────────────────────────────────────────────────────

class TestAnnulerUnSoin(TestCase):
    """Le statut « Annulé » existait dans le modèle sans qu'aucun écran ne l'écrive."""

    def setUp(self):
        self.patient = _patient('Ann')
        _soins_user('u_ann', perms=('change_soin',))
        self.client = Client()
        self.client.login(username='u_ann', password='x')

    def _annuler(self, soin, client=None):
        return (client or self.client).post(
            reverse('soins:annuler', kwargs={'pk': soin.pk}))

    def _statut(self, soin):
        soin.refresh_from_db()
        return soin.statut

    def test_un_brouillon_sannule(self):
        soin = _soin(self.patient, statut='brouillon')
        self._annuler(soin)
        self.assertEqual(self._statut(soin), 'annule')

    def test_un_soin_en_caisse_sannule(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        self._annuler(soin)
        self.assertEqual(self._statut(soin), 'annule')

    def test_les_lignes_ouvertes_suivent(self):
        soin = _soin(self.patient, statut='brouillon')
        p1 = _procedure(soin=soin, statut='brouillon')
        p2 = _procedure(soin=soin, statut='termine')
        self._annuler(soin)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.statut, 'annule')
        self.assertEqual(p2.statut, 'termine', "Une ligne terminée reste terminée")

    def test_un_soin_paye_resiste_au_personnel(self):
        """Il y a un encaissement en face que ce bouton ne rembourse pas."""
        soin = _soin(self.patient, statut='en_cours')
        self._annuler(soin)
        self.assertEqual(self._statut(soin), 'en_cours')

    def test_un_soin_paye_cede_a_ladministration(self):
        soin = _soin(self.patient, statut='en_cours')
        User.objects.create_superuser('su_ann', password='x')
        admin = Client()
        admin.login(username='su_ann', password='x')
        self._annuler(soin, client=admin)
        self.assertEqual(self._statut(soin), 'annule')

    def test_un_soin_termine_ne_sannule_pas(self):
        soin = _soin(self.patient, statut='termine')
        self._annuler(soin)
        self.assertEqual(self._statut(soin), 'termine')

    def test_sans_la_permission_rien_ne_bouge(self):
        soin = _soin(self.patient, statut='brouillon')
        _soins_user('u_ann_sans')
        sans = Client()
        sans.login(username='u_ann_sans', password='x')
        self._annuler(soin, client=sans)
        self.assertEqual(self._statut(soin), 'brouillon')


# ─── Les permissions verrouillent enfin les écrans ────────────────────────────

class TestPermissionsDuModule(TestCase):
    """Les vues n'avaient que @login_required.

    Les permissions existaient bien en base, mais aucune n'était lue : tout
    compte connecté pouvait créer, modifier et parcourir le module.
    """

    def setUp(self):
        self.patient = _patient('Perm')
        self.soin = _soin(self.patient, statut='brouillon')
        self.proc = _procedure(soin=self.soin)

    def _ecrans(self):
        return [
            ('soins.view_soin', reverse('soins:list')),
            ('soins.view_soin', reverse('soins:detail', kwargs={'pk': self.soin.pk})),
            ('soins.add_soin', reverse('soins:create')),
            ('soins.change_soin', reverse('soins:edit', kwargs={'pk': self.soin.pk})),
            ('soins.view_proceduresoin', reverse('soins:procedure_list')),
            ('soins.view_proceduresoin', reverse('soins:procedure_detail', kwargs={'pk': self.proc.pk})),
            ('soins.add_proceduresoin', reverse('soins:procedure_create')),
            ('soins.change_proceduresoin', reverse('soins:procedure_edit', kwargs={'pk': self.proc.pk})),
        ]

    def test_sans_permission_tout_repond_403(self):
        _soins_user('u_nu')
        nu = Client()
        nu.login(username='u_nu', password='x')
        for perm, url in self._ecrans():
            with self.subTest(url=url):
                self.assertEqual(nu.get(url).status_code, 403)

    def test_avec_la_permission_la_page_souvre(self):
        for i, (perm, url) in enumerate(self._ecrans()):
            with self.subTest(url=url):
                nom = 'u_perm%s' % i
                _soins_user(nom, perms=(perm.split('.')[1],))
                client = Client()
                client.login(username=nom, password='x')
                self.assertEqual(client.get(url).status_code, 200)

    def test_le_bouton_creer_suit_la_permission(self):
        _soins_user('u_lect', perms=('view_soin',))
        lecteur = Client()
        lecteur.login(username='u_lect', password='x')
        self.assertNotContains(lecteur.get(reverse('soins:list')), 'Nouveau soin')

        _soins_user('u_red', perms=('view_soin', 'add_soin'))
        redacteur = Client()
        redacteur.login(username='u_red', password='x')
        self.assertContains(redacteur.get(reverse('soins:list')), 'Nouveau soin')
