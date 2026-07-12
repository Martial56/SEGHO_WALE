from django.db import migrations, models
import django.db.models.deletion


def restore_rendez_vous_column(apps, schema_editor):
    """Ajoute rendez_vous_id si la colonne a été supprimée par erreur."""
    from django.db import connection
    with connection.cursor() as cursor:
        table_desc = connection.introspection.get_table_description(cursor, 'facturation_facture')
        columns = [col.name for col in table_desc]
        if 'rendez_vous_id' not in columns:
            cursor.execute(
                "ALTER TABLE facturation_facture "
                "ADD COLUMN rendez_vous_id integer "
                "REFERENCES patients_rendezvous (id)"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0005_merge_20260708_1940'),
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(restore_rendez_vous_column, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='facture',
            name='rendez_vous',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='factures',
                to='patients.rendezvous',
                verbose_name='Rendez-vous',
            ),
        ),
    ]
