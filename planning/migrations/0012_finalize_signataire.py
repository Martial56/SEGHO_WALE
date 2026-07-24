from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0011_migrate_signataire_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='planninghebdomadaire',
            name='signataire',
        ),
        migrations.RenameField(
            model_name='planninghebdomadaire',
            old_name='signataire_new',
            new_name='signataire',
        ),
        migrations.RemoveField(
            model_name='planningconfig',
            name='signataire_defaut',
        ),
    ]
