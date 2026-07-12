import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0005_historiqueemploye'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentemploye',
            name='date_expiration',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='AlerteDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('echeance', models.CharField(choices=[('2_mois', '2 mois'), ('1_mois', '1 mois')], max_length=10)),
                ('date_expiration', models.DateField()),
                ('lue', models.BooleanField(default=False)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='alertes',
                    to='employer.documentemploye',
                )),
            ],
            options={
                'verbose_name': 'Alerte document',
                'verbose_name_plural': 'Alertes documents',
                'ordering': ['date_expiration'],
                'unique_together': {('document', 'echeance')},
            },
        ),
    ]
