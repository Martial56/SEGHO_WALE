# Generated migration — validation service, HistoriqueConge, NotificationConge

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0010_typecontrat_droit_au_conge'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Champs de validation service sur Conge ────────────────────────
        migrations.AddField(
            model_name='conge',
            name='valide_par_service',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conges_valides_service',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='conge',
            name='date_validation_service',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='conge',
            name='chef_service_commentaire',
            field=models.TextField(blank=True),
        ),
        # ── 2. Mise à jour du champ statut (ajout de valide_service) ────────
        migrations.AlterField(
            model_name='conge',
            name='statut',
            field=models.CharField(
                choices=[
                    ('demande',        'Demandé'),
                    ('valide_service', 'Validé par le service'),
                    ('approuve',       'Approuvé'),
                    ('refuse',         'Refusé'),
                    ('en_cours',       'En cours'),
                    ('termine',        'Terminé'),
                ],
                default='demande',
                max_length=20,
            ),
        ),
        # ── 3. Mise à jour FK approuve_par (ajout related_name) ─────────────
        migrations.AlterField(
            model_name='conge',
            name='approuve_par',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conges_approuves',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # ── 4. Nouveau modèle HistoriqueConge ────────────────────────────────
        migrations.CreateModel(
            name='HistoriqueConge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[
                        ('soumis',        'Demande soumise'),
                        ('valide_service','Validé par le service'),
                        ('approuve',      'Approuvé'),
                        ('refuse',        'Refusé'),
                        ('annule',        'Annulé'),
                        ('mis_en_cours',  'Mis en cours'),
                        ('termine',       'Terminé'),
                    ],
                    max_length=20,
                )),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('commentaire', models.TextField(blank=True)),
                ('conge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='historique',
                    to='employer.conge',
                )),
                ('fait_par', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Historique congé',
                'verbose_name_plural': 'Historique congés',
                'db_table': 'ressources_humaines_historiqueconge',
                'ordering': ['-date'],
            },
        ),
        # ── 5. Nouveau modèle NotificationConge ─────────────────────────────
        migrations.CreateModel(
            name='NotificationConge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_notif', models.CharField(
                    choices=[
                        ('nouvelle_demande', 'Nouvelle demande'),
                        ('approuve',         'Approuvé'),
                        ('refuse',           'Refusé'),
                        ('valide_service',   'Validé service'),
                        ('annule',           'Annulé'),
                    ],
                    max_length=20,
                )),
                ('message', models.TextField()),
                ('lue', models.BooleanField(default=False)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('conge', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to='employer.conge',
                )),
                ('destinataire', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifs_conge',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Notification congé',
                'verbose_name_plural': 'Notifications congés',
                'db_table': 'ressources_humaines_notificationconge',
                'ordering': ['-cree_le'],
            },
        ),
    ]
