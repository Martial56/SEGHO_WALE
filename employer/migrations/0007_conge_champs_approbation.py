from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0006_documentemploye_date_expiration_alertedocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='conge',
            name='date_approbation',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='conge',
            name='commentaire_rh',
            field=models.TextField(blank=True),
        ),
        migrations.AlterModelOptions(
            name='conge',
            options={
                'verbose_name': 'Congé',
                'verbose_name_plural': 'Congés',
                'ordering': ['-date_demande'],
            },
        ),
    ]
