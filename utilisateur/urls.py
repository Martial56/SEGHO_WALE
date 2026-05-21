from django.urls import path
from . import views

app_name = 'utilisateur'

urlpatterns = [
    # Employés
    path('', views.employe_list, name='list'),
    path('nouveau/', views.employe_create, name='create'),
    path('<int:pk>/', views.employe_detail, name='detail'),
    path('<int:pk>/modifier/', views.employe_edit, name='edit'),
    path('supprimer-selection/', views.employe_bulk_delete, name='utilisateur_bulk_delete'),

    # Configuration — Mes diplômes personnels (non-admin)
    path('configuration/mes-diplomes/', views.mes_diplomes_list, name='mes_diplomes'),
    path('configuration/mes-diplomes/ajouter/', views.mes_diplome_create, name='mes_diplome_create'),
    path('configuration/mes-diplomes/<int:pk>/supprimer/', views.mes_diplome_delete, name='mes_diplome_delete'),

    # Utilisateur — listes liées
    path('<int:pk>/activite/<str:view_type>/', views.employe_related_list, name='utilisateur_activite'),

    # Utilisateur — mise à jour éducation (admin)
    path('<int:pk>/education/', views.employe_update_education, name='utilisateur_update_education'),
    # Utilisateur — sauvegarde diplômes personnels inline
    path('<int:pk>/diplomes-perso/', views.employe_save_diplomes, name='utilisateur_save_diplomes'),

    # Documents
    path('<int:pk>/documents/upload/', views.employe_upload_document, name='document_upload'),
    path('<int:pk>/documents/<int:doc_pk>/supprimer/', views.employe_delete_document, name='document_delete'),
]
