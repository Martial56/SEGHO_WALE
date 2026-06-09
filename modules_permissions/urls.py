from django.urls import path
from . import views

urlpatterns = [
    path('', views.module_list, name='module_list'),
    path('module/<int:module_id>/', views.module_detail, name='module_detail'),
    path('group/<int:group_id>/permissions/', views.group_permissions, name='group_permissions'),
    path('permissions/matrix/', views.permission_matrix, name='permission_matrix'),
]