from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # URLs des modules
    path('patients/', include('patients.urls')),
    path('medecins/', views.medecins_list, name='medecins_list'),
    path('consultations/', views.consultations_list, name='consultations_list'),
    path('pharmacie/', views.pharmacie_list, name='pharmacie_list'),
    path('laboratoire/', views.laboratoire_list, name='laboratoire_list'),
    path('hospitalisation/', views.hospitalisation_list, name='hospitalisation_list'),
    path('facturation/', views.facturation_list, name='facturation_list'),
    path('facturation/nouvelle/', views.facture_create, name='facture_create'),
    path('caisse/', views.caisse_list, name='caisse_list'),
    path('ressources-humaines/', views.ressources_humaines_list, name='ressources_humaines_list'),
    path('rapports/', views.rapports_list, name='rapports_list'),
]
