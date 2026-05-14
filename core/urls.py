from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # URLs des modules
    path('patients/', views.patients_list, name='patients_list'),
    path('medecins/', views.medecins_list, name='medecins_list'),
    path('consultations/', views.consultations_list, name='consultations_list'),
    path('pharmacie/', views.pharmacie_list, name='pharmacie_list'),
    path('laboratoire/', views.laboratoire_list, name='laboratoire_list'),
    path('hospitalisation/', views.hospitalisation_list, name='hospitalisation_list'),
    path('facturation/', views.facturation_list, name='facturation_list'),
    path('caisse/', views.caisse_list, name='caisse_list'),
    path('ressources-humaines/', views.ressources_humaines_list, name='ressources_humaines_list'),
    path('rapports/', views.rapports_list, name='rapports_list'),
    path('gynecologie/', views.gynecologie_list, name='gynecologie_list'),
    path('gynecologie/rdv/', views.gynecologie_rdv, name='gynecologie_rdv'),
    path('gynecologie/rdv/nouveau/', views.gynecologie_rdv_create, name='gynecologie_rdv_create'),
    path('gynecologie/rdv/<int:pk>/', views.gynecologie_rdv_detail, name='gynecologie_rdv_detail'),
    path('gynecologie/naissances/', views.gynecologie_registre_naissance, name='gynecologie_naissances'),
    path('gynecologie/naissances/nouveau/', views.gynecologie_naissance_create, name='gynecologie_naissance_create'),
]
