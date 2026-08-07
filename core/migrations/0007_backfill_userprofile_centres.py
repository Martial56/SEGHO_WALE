# Generated manually to complete the "centres" rollout.

from django.db import migrations


def rattacher_a_wale(apps, schema_editor):
    UserProfile = apps.get_model('core', 'UserProfile')
    Centre = apps.get_model('centres', 'Centre')
    wale = Centre.objects.filter(code='WALE').first()
    if wale is None:
        return
    for profile in UserProfile.objects.filter(centre_actif__isnull=True):
        profile.centres.add(wale)
        profile.centre_actif = wale
        profile.save(update_fields=['centre_actif'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_userprofile_centre_actif_userprofile_centres'),
        ('centres', '0002_creer_centres_initiaux'),
    ]

    operations = [
        migrations.RunPython(rattacher_a_wale, noop),
    ]
