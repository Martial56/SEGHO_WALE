"""Pose le code sur les traces de doublons déjà écrites.

Elles ont été enregistrées avant que `LogActivite.code` existe : seul leur
texte les distingue. On le lit donc **une fois**, ici — c'est précisément
parce que ce repère n'est pas fiable qu'on le remplace par un code.
"""

from django.db import migrations

FORCAGE = 'doublon.forcage'
CONFIRMATION = 'doublon.confirmation'


def coder(apps, schema_editor):
    LogActivite = apps.get_model('core', 'LogActivite')
    anciennes = LogActivite.objects.filter(type='alerte', code='')
    forcages = anciennes.filter(
        message__startswith='Dossier créé malgré un doublon signalé').update(code=FORCAGE)
    confirmations = anciennes.filter(
        message__startswith='Saisie poursuivie malgré la ressemblance').update(code=CONFIRMATION)
    if forcages or confirmations:
        print(f'\nTraces de doublons codées : {forcages} forçage(s), '
              f'{confirmations} confirmation(s).')


def decoder(apps, schema_editor):
    LogActivite = apps.get_model('core', 'LogActivite')
    LogActivite.objects.filter(code__in=(FORCAGE, CONFIRMATION)).update(code='')


class Migration(migrations.Migration):

    dependencies = [('core', '0016_logactivite_code')]

    operations = [migrations.RunPython(coder, decoder)]
