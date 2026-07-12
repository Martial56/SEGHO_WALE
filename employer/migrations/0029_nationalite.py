from django.db import migrations, models
import django.db.models.deletion


def migrer_nationalites(apps, schema_editor):
    Employe = apps.get_model('employer', 'Employe')
    Nationalite = apps.get_model('employer', 'Nationalite')
    cache = {}
    for emp in Employe.objects.all():
        val = (emp.nationalite_old or '').strip()
        if not val:
            continue
        if val not in cache:
            nat, _ = Nationalite.objects.get_or_create(nom=val)
            cache[val] = nat
        emp.nationalite_fk_id = cache[val].id
        emp.save(update_fields=['nationalite_fk'])


def inverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0028_typecontrat_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='Nationalite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
            ],
            options={
                'verbose_name': 'Nationalité',
                'verbose_name_plural': 'Nationalités',
                'db_table': 'ressources_humaines_nationalite',
                'ordering': ['nom'],
            },
        ),
        migrations.RenameField(
            model_name='employe',
            old_name='nationalite',
            new_name='nationalite_old',
        ),
        migrations.AddField(
            model_name='employe',
            name='nationalite_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='employes', to='employer.nationalite',
            ),
        ),
        migrations.RunPython(migrer_nationalites, inverse_noop),
        migrations.RemoveField(
            model_name='employe',
            name='nationalite_old',
        ),
        migrations.RenameField(
            model_name='employe',
            old_name='nationalite_fk',
            new_name='nationalite',
        ),
    ]
