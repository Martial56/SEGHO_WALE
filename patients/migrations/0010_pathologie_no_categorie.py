from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0009_pathologie'),
    ]

    operations = [
        migrations.RemoveField(model_name='Pathologie', name='categorie'),
        migrations.AlterModelOptions(
            name='pathologie',
            options={'verbose_name': 'Pathologie', 'ordering': ['nom']},
        ),
    ]
