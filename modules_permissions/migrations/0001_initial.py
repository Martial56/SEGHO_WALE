from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Module',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(help_text="Identifiant technique du module (ex: patients, pharmacie…)", unique=True)),
                ('name', models.CharField(max_length=255, verbose_name='Nom')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('icon', models.CharField(default='📦', help_text='Emoji du module', max_length=10)),
                ('url_name', models.CharField(blank=True, help_text="Nom de l'URL Django (ex: patients_list). Vide = pas de lien.", max_length=100)),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': 'Module',
                'verbose_name_plural': 'Modules',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='GroupModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_modules', to='auth.group', verbose_name='Groupe')),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_modules', to='modules_permissions.module', verbose_name='Module')),
            ],
            options={
                'verbose_name': 'Module par groupe',
                'verbose_name_plural': 'Modules par groupe',
                'unique_together': {('group', 'module')},
            },
        ),
        migrations.CreateModel(
            name='UserModuleOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('override_type', models.CharField(choices=[('grant', 'Accorder (en plus du groupe)'), ('revoke', 'Retirer (même si dans le groupe)')], default='grant', max_length=10, verbose_name='Type')),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_overrides', to='modules_permissions.module', verbose_name='Module')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='module_overrides', to='auth.user', verbose_name='Utilisateur')),
            ],
            options={
                'verbose_name': 'Override module utilisateur',
                'verbose_name_plural': 'Overrides modules utilisateurs',
                'unique_together': {('user', 'module')},
            },
        ),
    ]
