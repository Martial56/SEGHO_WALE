from django.db import migrations


def backfill(apps, schema_editor):
    Conge = apps.get_model('employer', 'Conge')
    TypeConge = apps.get_model('conges', 'TypeConge')
    types_non_deductibles = set(
        TypeConge.objects.filter(deductible=False).values_list('code', flat=True)
    )
    if types_non_deductibles:
        Conge.objects.filter(type_conge__in=types_non_deductibles).update(deduit_du_solde=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0031_conge_deduit_du_solde'),
        ('conges', '0002_seed_types_conge'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
