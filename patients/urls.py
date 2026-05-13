from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_list, name='list'),
    path('rendez-vous/', views.rdv_global_list, name='rdv_global'),
    path('rendez-vous/nouveau/', views.rdv_create, name='rdv_create'),
    path('<int:pk>/info/', views.patient_info_json, name='patient_info'),
    path('nouveau/', views.patient_create, name='create'),
    path('<int:pk>/', views.patient_detail, name='detail'),
    path('<int:pk>/modifier/', views.patient_edit, name='edit'),
    path('<int:pk>/rendez-vous/', views.patient_rdv_list, name='rdv_list'),
    path('<int:pk>/consultations/', views.patient_consultation_list, name='consultation_list'),
    path('<int:pk>/ordonnances/', views.patient_ordonnance_list, name='ordonnance_list'),
    path('<int:pk>/hospitalisations/', views.patient_hospitalisation_list, name='hospitalisation_list'),
    path('<int:pk>/examens-demandes/', views.patient_demande_examens_list, name='demande_examens_list'),
    path('<int:pk>/examens-resultats/', views.patient_resultat_examens_list, name='resultat_examens_list'),
]
