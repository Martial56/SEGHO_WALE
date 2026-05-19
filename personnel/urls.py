from django.urls import path
from . import views

app_name = 'personnel'

urlpatterns = [
    # Personnel
    path('', views.employe_list, name='list'),
    path('<int:pk>/', views.employe_detail, name='detail'),
    path('<int:pk>/modifier/', views.employe_edit, name='edit'),
    path('supprimer-selection/', views.employe_bulk_delete, name='employe_bulk_delete'),

    # Personnel — listes liées
    path('<int:pk>/activite/<str:view_type>/', views.employe_related_list, name='employe_activite'),

    # Personnel — mise à jour éducation
    path('<int:pk>/education/', views.employe_update_education, name='employe_update_education'),
]
