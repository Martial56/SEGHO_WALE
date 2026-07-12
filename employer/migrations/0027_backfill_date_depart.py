from django.db import migrations


def backfill_date_depart(apps, schema_editor):
    Employe = apps.get_model('employer', 'Employe')
    for emp in Employe.objects.filter(statut='quitte', date_depart__isnull=True):
        Employe.objects.filter(pk=emp.pk).update(date_depart=emp.modifie_le.date())


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0026_employe_date_depart'),
    ]

    operations = [
        migrations.RunPython(backfill_date_depart, noop),
    ]
