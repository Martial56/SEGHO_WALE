from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0028_data_refere_to_decharge'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chambre',
            name='capacite',
        ),
    ]
