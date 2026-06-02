from django.core.management.base import BaseCommand
from modules_permissions.models import Module

class Command(BaseCommand):
    help = 'Populate the database with initial modules'

    def handle(self, *args, **kwargs):
        modules = [
            {'name': 'Module 1', 'description': 'Description for Module 1'},
            {'name': 'Module 2', 'description': 'Description for Module 2'},
            {'name': 'Module 3', 'description': 'Description for Module 3'},
        ]

        for module_data in modules:
            module, created = Module.objects.get_or_create(
                name=module_data['name'],
                defaults={'description': module_data['description']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created module: {module.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Module already exists: {module.name}'))