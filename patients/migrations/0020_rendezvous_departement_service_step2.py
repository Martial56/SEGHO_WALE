from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0019_rendezvous_departement_service_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='rendezvous',
            name='departement_code_old',
        ),
    ]
