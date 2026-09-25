"""Renomme en français les permissions de `Caisse` déjà présentes en base.

La migration 0009 a créé le modèle avant qu'on lui donne des libellés français,
et `AlterModelOptions` (0012) ne touche pas les lignes déjà écrites dans
`auth_permission`. Elles s'appelaient donc encore « Can add Caisse » dans
l'écran d'attribution des droits aux groupes.

Même parti pris que hospitalisation/0040 : les libellés sont lus sur l'état
historique du modèle, jamais recopiés ici — une correction dans models.py ne
peut pas désynchroniser ce fichier.
"""

from django.db import migrations

ACTIONS = ('view', 'add', 'change', 'delete')


def _renommer(apps, anglais):
    Permission = apps.get_model('auth', 'Permission')
    modele = apps.get_model('facturation', 'caisse')
    libelles = dict(modele._meta.permissions)
    for action in ACTIONS:
        codename = '%s_caisse' % action
        if anglais:
            nom = 'Can %s %s' % (action, modele._meta.verbose_name_raw)
        else:
            nom = libelles.get(codename)
            if nom is None:
                continue
        # Sans effet sur une base neuve : les permissions y sont créées après
        # les migrations, et le modèle leur donne déjà le bon nom.
        Permission.objects.filter(
            content_type__app_label='facturation',
            content_type__model='caisse',
            codename=codename,
        ).update(name=nom)


def en_francais(apps, schema_editor):
    _renommer(apps, anglais=False)


def en_anglais(apps, schema_editor):
    _renommer(apps, anglais=True)


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0012_alter_caisse_options'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(en_francais, en_anglais),
    ]
