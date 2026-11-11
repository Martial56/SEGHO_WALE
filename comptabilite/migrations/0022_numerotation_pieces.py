from django.conf import settings
from django.db import migrations, models

# « Numérotation des pièces » des journaux de l'expert-comptable
# (docs/CODE JOURNAUX.xlsx) : tous « Mensuelle », sauf ces trois en
# « Journal ». Les écritures déjà validées gardent leur numéro (suite de
# l'exercice) : seules les validations à venir suivent le nouveau mode.
EN_CONTINU = ['BQ EGP', 'SIBDEP', 'RAN.']


def poser(apps, schema_editor):
    Journal = apps.get_model('comptabilite', 'Journal')
    Journal.objects.update(numerotation='mensuelle')
    Journal.objects.filter(code__in=EN_CONTINU).update(numerotation='journal')


class Migration(migrations.Migration):

    dependencies = [
        ('centres', '0005_rattacher_facturation'),
        ('comptabilite', '0021_cloture_journaux'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='ecriture',
            name='numero_unique_par_journal_et_exercice',
        ),
        migrations.AddField(
            model_name='ecriture',
            name='numerotation',
            field=models.CharField(choices=[('mensuelle', 'Mensuelle'), ('journal', 'Journal')], default='journal', max_length=10),
        ),
        migrations.AddField(
            model_name='ecriture',
            name='periode',
            field=models.DateField(blank=True, help_text='Premier jour du mois, en numérotation mensuelle.', null=True),
        ),
        migrations.AddField(
            model_name='journal',
            name='numerotation',
            field=models.CharField(choices=[('mensuelle', 'Mensuelle'), ('journal', 'Journal')], default='mensuelle', max_length=10, verbose_name='Numérotation des pièces'),
        ),
        migrations.AddConstraint(
            model_name='ecriture',
            constraint=models.UniqueConstraint(condition=models.Q(('numerotation', 'journal')), fields=('journal', 'exercice', 'numero'), name='numero_unique_par_journal_et_exercice'),
        ),
        migrations.AddConstraint(
            model_name='ecriture',
            constraint=models.UniqueConstraint(condition=models.Q(('numerotation', 'mensuelle')), fields=('journal', 'periode', 'numero'), name='numero_unique_par_journal_et_mois'),
        ),
        migrations.RunPython(poser, migrations.RunPython.noop),
    ]
