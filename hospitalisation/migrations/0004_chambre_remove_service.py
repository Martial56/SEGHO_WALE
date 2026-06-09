from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0003_chambre_update_types_remove_batiment'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chambre',
            name='service',
        ),
    ]
