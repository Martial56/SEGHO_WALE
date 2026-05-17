from django.urls import path
from . import views

app_name = 'employe'

urlpatterns = [
    # Employés
    path('', views.employe_list, name='list'),
    path('nouveau/', views.employe_create, name='create'),
    path('<int:pk>/', views.employe_detail, name='detail'),
    path('<int:pk>/modifier/', views.employe_edit, name='edit'),
    path('supprimer-selection/', views.employe_bulk_delete, name='employe_bulk_delete'),

    # Configuration — Spécialités
    path('configuration/specialites/', views.specialite_list, name='specialites'),
    path('configuration/specialites/nouveau/', views.specialite_create, name='specialite_create'),
    path('configuration/specialites/<int:pk>/', views.specialite_detail, name='specialite_detail'),
    path('configuration/specialites/<int:pk>/modifier/', views.specialite_edit, name='specialite_edit'),
    path('configuration/specialites/supprimer-selection/', views.specialite_bulk_delete, name='specialite_bulk_delete'),

    # Configuration — Départements
    path('configuration/departements/', views.departement_list, name='departements'),
    path('configuration/departements/nouveau/', views.departement_create, name='departement_create'),
    path('configuration/departements/<int:pk>/', views.departement_detail, name='departement_detail'),
    path('configuration/departements/<int:pk>/modifier/', views.departement_edit, name='departement_edit'),
    path('configuration/departements/supprimer-selection/', views.departement_bulk_delete, name='departement_bulk_delete'),

    # Configuration — Diplômes
    path('configuration/diplomes/', views.diplome_list, name='diplomes'),
    path('configuration/diplomes/nouveau/', views.diplome_create, name='diplome_create'),
    path('configuration/diplomes/<int:pk>/', views.diplome_detail, name='diplome_detail'),
    path('configuration/diplomes/<int:pk>/modifier/', views.diplome_edit, name='diplome_edit'),
    path('configuration/diplomes/supprimer-selection/', views.diplome_bulk_delete, name='diplome_bulk_delete'),

    # Employé — listes liées
    path('<int:pk>/activite/<str:view_type>/', views.employe_related_list, name='employe_activite'),

    # Employé — mise à jour éducation
    path('<int:pk>/education/', views.employe_update_education, name='employe_update_education'),
]
