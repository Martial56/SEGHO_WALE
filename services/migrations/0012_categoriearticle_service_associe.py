import django.db.models.deletion
from django.db import migrations, models


CODE_MAP = {
    'CS': 'MED-GEN',
    'CSG': 'GYNECO',
}


def assigner_services(apps, schema_editor):
    CategorieArticle = apps.get_model('services', 'CategorieArticle')
    Service = apps.get_model('medecins', 'Service')
    for cat_code, service_code in CODE_MAP.items():
        service = Service.objects.filter(code=service_code).first()
        if service:
            CategorieArticle.objects.filter(code=cat_code).update(service_associe=service)


def reverse_assigner_services(apps, schema_editor):
    CategorieArticle = apps.get_model('services', 'CategorieArticle')
    CategorieArticle.objects.filter(code__in=CODE_MAP.keys()).update(service_associe=None)


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0010_service_medecine_generale_gynecologie'),
        ('services', '0011_alter_articleservice_reference_interne'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriearticle',
            name='service_associe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='medecins.service', verbose_name='Service associé'),
        ),
        migrations.RunPython(assigner_services, reverse_assigner_services),
    ]
