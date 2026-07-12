from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import Caisse, SessionCaisse, TransactionCaisse


# ─── Helpers de création ───────────────────────────────────────────────────────

def _caisse(suffix='', actif=True):
    return Caisse.objects.create(
        nom=f'Caisse {suffix}',
        code=f'CSS{suffix}{Caisse.objects.count():03d}',
        actif=actif,
    )


def _session(caisse=None, caissier=None, statut='ouverte'):
    return SessionCaisse.objects.create(
        caisse=caisse or _caisse('S'),
        caissier=caissier,
        statut=statut,
    )


def _transaction(session=None, type_transaction='encaissement', montant=Decimal('1000')):
    return TransactionCaisse.objects.create(
        session=session or _session(),
        type_transaction=type_transaction,
        montant=montant,
    )


# ─── Tests modèle Caisse ────────────────────────────────────────────────────────

class TestCaisseModel(TestCase):

    def test_str(self):
        caisse = _caisse('A')
        self.assertEqual(str(caisse), f"Caisse {caisse.nom}")

    def test_actif_par_defaut(self):
        caisse = Caisse.objects.create(nom='Principale', code='CSSDEF001')
        self.assertTrue(caisse.actif, "Une caisse doit être active par défaut")

    def test_code_unique(self):
        Caisse.objects.create(nom='Caisse 1', code='CSSDUP')
        with self.assertRaises(IntegrityError,
                                msg="Le code d'une caisse doit être unique"):
            with transaction.atomic():
                Caisse.objects.create(nom='Caisse 2', code='CSSDUP')

    def test_filtre_actif_exclut_les_caisses_inactives(self):
        _caisse('B1', actif=True)
        _caisse('B2', actif=True)
        _caisse('B3', actif=False)
        caisses_actives = Caisse.objects.filter(actif=True)
        self.assertEqual(caisses_actives.count(), 2,
                          "Seules les caisses actives doivent être retournées")

    def test_responsable_mis_a_null_si_utilisateur_supprime(self):
        user = User.objects.create_user('resp_caisse', password='x')
        caisse = Caisse.objects.create(nom='Caisse C', code='CSSRESP', responsable=user)
        user.delete()
        caisse.refresh_from_db()
        self.assertIsNone(caisse.responsable,
                           "Le responsable doit être mis à null quand l'utilisateur est supprimé")


# ─── Tests modèle SessionCaisse ─────────────────────────────────────────────────

class TestSessionCaisseModel(TestCase):

    def test_str_contient_la_caisse_et_la_date(self):
        session = _session()
        self.assertIn(str(session.caisse), str(session))
        self.assertIn(session.date_ouverture.strftime('%d/%m/%Y'), str(session))

    def test_statut_par_defaut_ouverte(self):
        session = _session()
        self.assertEqual(session.statut, 'ouverte')

    def test_solde_ouverture_par_defaut_zero(self):
        session = SessionCaisse.objects.create(caisse=_caisse('D'))
        self.assertEqual(session.solde_ouverture, Decimal('0'))

    def test_ordering_par_date_ouverture_decroissante(self):
        s1 = _session()
        s2 = _session()
        # Force un écart temporel net pour un tri déterministe (auto_now_add
        # ignore toute valeur passée à la création).
        SessionCaisse.objects.filter(pk=s1.pk).update(
            date_ouverture=timezone.now() - timedelta(hours=1)
        )
        sessions = list(SessionCaisse.objects.all())
        self.assertEqual(sessions[0].pk, s2.pk,
                          "La session la plus récente doit apparaître en premier")

    def test_related_name_sessions_depuis_caisse(self):
        caisse = _caisse('E')
        session = _session(caisse=caisse)
        self.assertIn(session, caisse.sessions.all())

    def test_caissier_mis_a_null_si_utilisateur_supprime(self):
        user = User.objects.create_user('caissier_1', password='x')
        session = _session(caissier=user)
        user.delete()
        session.refresh_from_db()
        self.assertIsNone(session.caissier,
                           "Le caissier doit être mis à null quand l'utilisateur est supprimé")

    def test_fermeture_session(self):
        session = _session(statut='ouverte')
        session.statut = 'fermee'
        session.date_fermeture = timezone.now()
        session.solde_fermeture = Decimal('25000')
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.statut, 'fermee')
        self.assertIsNotNone(session.date_fermeture)
        self.assertEqual(session.solde_fermeture, Decimal('25000'))


# ─── Tests modèle TransactionCaisse (génération de numéros) ────────────────────

class TestTransactionCaisseNumeros(TestCase):

    def test_numero_genere_automatiquement(self):
        transaction_caisse = _transaction()
        self.assertTrue(transaction_caisse.numero,
                         "Le numéro doit être généré automatiquement à la création")

    def test_format_numero_transaction(self):
        transaction_caisse = _transaction()
        annee = timezone.now().year
        prefix = f'TRS{annee}'
        self.assertTrue(transaction_caisse.numero.startswith(prefix),
                         f"Attendu préfixe '{prefix}', obtenu '{transaction_caisse.numero}'")
        suffixe = transaction_caisse.numero[len(prefix):]
        self.assertEqual(len(suffixe), 7, "Le suffixe doit être sur 7 chiffres")
        self.assertTrue(suffixe.isdigit(), "Le suffixe doit être numérique")

    def test_deux_transactions_numeros_distincts(self):
        session = _session()
        t1 = _transaction(session=session)
        t2 = _transaction(session=session)
        self.assertNotEqual(t1.numero, t2.numero)

    def test_numero_conserve_lors_dune_resauvegarde(self):
        transaction_caisse = _transaction()
        premier_numero = transaction_caisse.numero
        transaction_caisse.description = 'Mise à jour'
        transaction_caisse.save()
        transaction_caisse.refresh_from_db()
        self.assertEqual(transaction_caisse.numero, premier_numero,
                          "Le numéro ne doit pas changer lors d'une resauvegarde")


# ─── Tests modèle TransactionCaisse (relations et contenu) ─────────────────────

class TestTransactionCaisseModel(TestCase):

    def test_str_contient_numero_et_montant(self):
        transaction_caisse = _transaction(montant=Decimal('1500'))
        texte = str(transaction_caisse)
        self.assertIn(transaction_caisse.numero, texte)
        self.assertIn('1500', texte)

    def test_related_name_transactions_depuis_session(self):
        session = _session()
        transaction_caisse = _transaction(session=session)
        self.assertIn(transaction_caisse, session.transactions.all())

    def test_facture_optionnelle(self):
        transaction_caisse = _transaction()
        self.assertIsNone(transaction_caisse.facture)

    def test_mode_paiement_par_defaut_especes(self):
        session = _session()
        transaction_caisse = TransactionCaisse.objects.create(
            session=session, type_transaction='encaissement', montant=Decimal('500'),
        )
        self.assertEqual(transaction_caisse.mode_paiement, 'especes')

    def test_cree_par_mis_a_null_si_utilisateur_supprime(self):
        user = User.objects.create_user('caissier_createur', password='x')
        session = _session()
        transaction_caisse = TransactionCaisse.objects.create(
            session=session, type_transaction='decaissement', montant=Decimal('750'),
            cree_par=user,
        )
        user.delete()
        transaction_caisse.refresh_from_db()
        self.assertIsNone(transaction_caisse.cree_par,
                           "cree_par doit être mis à null quand l'utilisateur est supprimé")
