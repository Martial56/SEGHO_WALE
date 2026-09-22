from django.db import migrations


# Django écrit le libellé d'une permission en base au moment des migrations, et
# il l'écrit en anglais : « Can add Soin ». C'est pourtant ce libellé que lit la
# personne qui compose un groupe dans /admin/. Les modèles déclarent désormais
# des libellés français (voir Soin.Meta), mais cela ne vaut que pour les
# permissions encore à créer — celles d'une base déjà en service gardent leur
# nom d'origine. On les renomme donc ici.
FRANCAIS = {
    ('soin', 'view_soin'): "Peut consulter les soins",
    ('soin', 'add_soin'): "Peut créer un soin",
    ('soin', 'change_soin'): "Peut modifier un soin",
    ('soin', 'delete_soin'): "Peut supprimer un soin",
    ('proceduresoin', 'view_proceduresoin'): "Peut consulter les procédures de soin",
    ('proceduresoin', 'add_proceduresoin'): "Peut créer une procédure de soin",
    ('proceduresoin', 'change_proceduresoin'): "Peut modifier une procédure de soin",
    ('proceduresoin', 'delete_proceduresoin'): "Peut supprimer une procédure de soin",
}

ANGLAIS = {
    ('soin', 'view_soin'): "Can view Soin",
    ('soin', 'add_soin'): "Can add Soin",
    ('soin', 'change_soin'): "Can change Soin",
    ('soin', 'delete_soin'): "Can delete Soin",
    ('proceduresoin', 'view_proceduresoin'): "Can view Procédure de soin",
    ('proceduresoin', 'add_proceduresoin'): "Can add Procédure de soin",
    ('proceduresoin', 'change_proceduresoin'): "Can change Procédure de soin",
    ('proceduresoin', 'delete_proceduresoin'): "Can delete Procédure de soin",
}


def _renommer(apps, libelles):
    Permission = apps.get_model('auth', 'Permission')
    for (modele, codename), nom in libelles.items():
        # Rien à faire sur une base neuve : les permissions n'y sont créées
        # qu'après les migrations, et le modèle leur donne déjà le bon nom.
        Permission.objects.filter(
            content_type__app_label='soins',
            content_type__model=modele,
            codename=codename,
        ).update(name=nom)


def en_francais(apps, schema_editor):
    _renommer(apps, FRANCAIS)


def en_anglais(apps, schema_editor):
    _renommer(apps, ANGLAIS)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
        ('soins', '0012_alter_proceduresoin_options_alter_soin_options'),
    ]

    operations = [
        migrations.RunPython(en_francais, en_anglais),
    ]
