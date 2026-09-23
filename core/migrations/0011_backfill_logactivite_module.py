# Reconstitue le champ `module` des entrées de journal déjà existantes à
# partir de leur content_type, pour que le filtre par module du journal
# continue de fonctionner sur l'historique déjà enregistré.

from django.db import migrations


def backfill_module(apps, schema_editor):
    LogActivite = apps.get_model('core', 'LogActivite')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    for ct in ContentType.objects.all():
        LogActivite.objects.filter(content_type=ct, module='').update(module=ct.app_label)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_logactivite_module_alter_logactivite_type'),
    ]

    operations = [
        migrations.RunPython(backfill_module, noop),
    ]
