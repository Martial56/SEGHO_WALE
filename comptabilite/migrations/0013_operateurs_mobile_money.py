from django.db import migrations

# Un compte de trésorerie par opérateur Mobile Money, chacun sur son
# sous-compte de 552 : à la clôture d'une session, on sait ce qui est arrivé
# sur chaque compte marchand, et chacun se rapproche de son propre relevé.
# D'autres opérateurs s'ajoutent à l'écran (Trésorerie → Comptes de trésorerie).
OPERATEURS = [
    ('Wave', '5521', 'Wave'),
    ('Orange Money', '5522', 'Orange Money'),
    ('MoMo', '5523', 'MTN MoMo'),
]

# Le compte « Mobile Money » d'origine (552) garde les paiements antérieurs,
# faits sans préciser l'opérateur ; il ne se propose plus à l'encaissement.
ANCIEN, ANCIEN_RENOMME = 'Mobile Money', 'Mobile Money (opérateur non précisé)'


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    for libelle, numero, etablissement in OPERATEURS:
        compte, _ = Compte.objects.get_or_create(numero=numero, defaults={'intitule': f'Mobile Money — {libelle}'})
        if not CompteTresorerie.objects.filter(compte=compte).exists() and \
                not CompteTresorerie.objects.filter(libelle=libelle).exists():
            CompteTresorerie.objects.create(libelle=libelle, type='mobile_money', compte=compte,
                                            etablissement=etablissement)
    CompteTresorerie.objects.filter(libelle=ANCIEN, compte__numero='552').update(libelle=ANCIEN_RENOMME, actif=False)


def retirer(apps, schema_editor):
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    CompteTresorerie.objects.filter(libelle=ANCIEN_RENOMME).update(libelle=ANCIEN, actif=True)
    CompteTresorerie.objects.filter(libelle__in=[l for l, _, _ in OPERATEURS], paiements__isnull=True,
                                    releve__isnull=True).delete()
    apps.get_model('comptabilite', 'Compte').objects.filter(
        numero__in=[n for _, n, _ in OPERATEURS], lignes__isnull=True, compte_tresorerie__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0012_comptes_lot8'),
        ('facturation', '0032_paiement_operateur'),
    ]

    operations = [
        migrations.RunPython(poser, retirer),
    ]
