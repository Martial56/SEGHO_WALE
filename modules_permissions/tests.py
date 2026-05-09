from django.test import TestCase
from .models import Module, Permission, Group

class ModulePermissionsTests(TestCase):

    def setUp(self):
        # Create test data for modules, permissions, and groups
        self.module1 = Module.objects.create(name='Module 1', description='Description for Module 1')
        self.module2 = Module.objects.create(name='Module 2', description='Description for Module 2')
        
        self.permission1 = Permission.objects.create(name='Permission 1', module=self.module1)
        self.permission2 = Permission.objects.create(name='Permission 2', module=self.module2)
        
        self.group1 = Group.objects.create(name='Group 1')
        self.group1.permissions.add(self.permission1)
        
        self.group2 = Group.objects.create(name='Group 2')
        self.group2.permissions.add(self.permission2)

    def test_module_creation(self):
        self.assertEqual(Module.objects.count(), 2)
        self.assertEqual(self.module1.name, 'Module 1')
        self.assertEqual(self.module2.name, 'Module 2')

    def test_permission_assignment(self):
        self.assertIn(self.permission1, self.group1.permissions.all())
        self.assertIn(self.permission2, self.group2.permissions.all())

    def test_group_permissions(self):
        self.assertEqual(self.group1.permissions.count(), 1)
        self.assertEqual(self.group2.permissions.count(), 1)

    def test_access_control(self):
        # Check if group1 has access to module1
        self.assertTrue(self.group1.has_perm('module1'))
        # Check if group1 does not have access to module2
        self.assertFalse(self.group1.has_perm('module2'))