from django.urls import path
from . import views

app_name = 'medecins'

urlpatterns = [
    # Médecins
    path('', views.medecin_list, name='list'),
    path('nouveau/', views.medecin_create, name='create'),
    path('<int:pk>/', views.medecin_detail, name='detail'),
    path('<int:pk>/modifier/', views.medecin_edit, name='edit'),
    path('supprimer-selection/', views.medecin_bulk_delete, name='medecin_bulk_delete'),

    # Configuration — Spécialités
    path('configuration/specialites/', views.specialite_list, name='specialites'),
    path('configuration/specialites/nouveau/', views.specialite_create, name='specialite_create'),
    path('configuration/specialites/<int:pk>/modifier/', views.specialite_edit, name='specialite_edit'),
    path('configuration/specialites/supprimer-selection/', views.specialite_bulk_delete, name='specialite_bulk_delete'),

    # Configuration — Départements
    path('configuration/departements/', views.departement_list, name='departements'),
    path('configuration/departements/nouveau/', views.departement_create, name='departement_create'),
    path('configuration/departements/<int:pk>/modifier/', views.departement_edit, name='departement_edit'),
    path('configuration/departements/supprimer-selection/', views.departement_bulk_delete, name='departement_bulk_delete'),

    # Configuration — Diplômes
    path('configuration/diplomes/', views.diplome_list, name='diplomes'),
    path('configuration/diplomes/nouveau/', views.diplome_create, name='diplome_create'),
    path('configuration/diplomes/<int:pk>/modifier/', views.diplome_edit, name='diplome_edit'),
    path('configuration/diplomes/supprimer-selection/', views.diplome_bulk_delete, name='diplome_bulk_delete'),

    # Médecin — listes liées (rdv, consultation, ordonnance, hospitalisation, examens, referents)
    path('<int:pk>/activite/<str:view_type>/', views.medecin_related_list, name='medecin_activite'),

    # Docteurs Référents
    path('referents/', views.referent_list, name='referent_list'),
    path('referents/nouveau/', views.referent_create, name='referent_create'),
    path('referents/<int:pk>/', views.referent_detail, name='referent_detail'),
    path('referents/<int:pk>/modifier/', views.referent_edit, name='referent_edit'),
    path('referents/supprimer-selection/', views.referent_bulk_delete, name='referent_bulk_delete'),

    # Référent — listes liées (patients, contacts)
    path('referents/<int:pk>/activite/<str:view_type>/', views.referent_related_list, name='referent_activite'),
]
