import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('soins', '0005_add_proceduresoin'),
    ]

    operations = [
        migrations.CreateModel(
            name='Maladie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=200, unique=True, verbose_name='Nom')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('code_cim', models.CharField(blank=True, max_length=20, verbose_name='Code CIM-10')),
            ],
            options={
                'verbose_name': 'Maladie',
                'verbose_name_plural': 'Maladies',
                'ordering': ['nom'],
            },
        ),
        migrations.RemoveField(
            model_name='proceduresoin',
            name='maladie',
        ),
        migrations.AddField(
            model_name='proceduresoin',
            name='maladie',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='soins.maladie', verbose_name='Maladie'),
        ),
    ]
