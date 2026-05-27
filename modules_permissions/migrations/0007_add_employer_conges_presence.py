from django.db import migrations


def apply(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')

    modules = [
        {
            'code': 'employer',
            'name': 'Employés',
            'icon': '👔',
            'url_name': '',
            'order': 21,
        },
        {
            'code': 'conges',
            'name': 'Congés',
            'icon': '🏖️',
            'url_name': '',
            'order': 22,
        },
        {
            'code': 'presence',
            'name': 'Présence',
            'icon': '📊',
            'url_name': '',
            'order': 23,
        },
    ]

    for data in modules:
        Module.objects.get_or_create(code=data['code'], defaults=data)


def revert(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code__in=['employer', 'conges', 'presence']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0006_rename_personnel_to_utilisateur'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
