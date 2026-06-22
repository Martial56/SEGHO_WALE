from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_list, name='list'),
    path('gynecologie/', views.gynecologie_patient_list, name='gynecologie_patients'),
    path('gynecologie/rendez-vous/', views.gynecologie_rdv_list, name='gynecologie_rdv'),
    path('rendez-vous/', views.rdv_global_list, name='rdv_global'),
    path('rendez-vous/nouveau/', views.rdv_create, name='rdv_create'),
    path('rendez-vous/<int:pk>/modifier/', views.rdv_edit, name='rdv_edit'),
    path('<int:pk>/info/', views.patient_info_json, name='patient_info'),
    path('recherche/', views.patient_search_json, name='patient_search'),
    path('nouveau/', views.patient_create, name='create'),
    path('<int:pk>/', views.patient_detail, name='detail'),
    path('<int:pk>/modifier/', views.patient_edit, name='edit'),
    path('<int:pk>/rendez-vous/', views.patient_rdv_list, name='rdv_list'),
    path('<int:pk>/consultations/', views.patient_consultation_list, name='consultation_list'),
    path('<int:pk>/soins/', views.patient_soin_list, name='soin_list'),
    path('<int:pk>/ordonnances/', views.patient_ordonnance_list, name='ordonnance_list'),
    path('<int:pk>/ordonnances/creer/', views.ordonnance_create, name='ordonnance_create'),
    path('<int:pk>/hospitalisations/', views.patient_hospitalisation_list, name='hospitalisation_list'),
    path('<int:pk>/examens-demandes/', views.patient_demande_examens_list, name='demande_examens_list'),
    path('<int:pk>/examens-resultats/', views.patient_resultat_examens_list, name='resultat_examens_list'),
    path('pathologies/', views.pathologie_list, name='pathologie_list'),
    path('pathologies/nouveau/', views.pathologie_create, name='pathologie_create'),
    path('pathologies/<int:pk>/modifier/', views.pathologie_edit, name='pathologie_edit'),
    path('pathologies/<int:pk>/supprimer/', views.pathologie_delete, name='pathologie_delete'),
    path('types-visite/', views.typevisite_list, name='typevisite_list'),
    path('types-visite/nouveau/', views.typevisite_create, name='typevisite_create'),
    path('types-visite/<int:pk>/modifier/', views.typevisite_edit, name='typevisite_edit'),
    path('types-visite/<int:pk>/supprimer/', views.typevisite_delete, name='typevisite_delete'),
]
