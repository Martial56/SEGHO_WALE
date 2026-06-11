from django.urls import path, include
from . import views
import medecins.views as medecins_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('tableau-de-bord/', views.kpi_dashboard, name='kpi_dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('activite/note/', views.post_note, name='post_note'),

    # URLs des modules
    path('patients/', include('patients.urls')),
    path('medecins/',                   views.medecins_list,  name='medecins_list'),
    path('medecins/nouveau/',           views.medecin_create, name='medecin_create'),
    path('medecins/<int:pk>/modifier/', views.medecin_edit,   name='medecin_edit'),

    # Spécialités
    path('medecins/specialites/',                   medecins_views.specialites_list,       name='medecins_specialites'),
    path('medecins/specialites/nouveau/',           medecins_views.specialite_create,      name='medecins_specialite_create'),
    path('medecins/specialites/bulk-delete/',       medecins_views.specialite_bulk_delete, name='medecins_specialite_bulk_delete'),
    path('medecins/specialites/<int:pk>/',          medecins_views.specialite_detail,      name='medecins_specialite_detail'),
    path('medecins/specialites/<int:pk>/modifier/', medecins_views.specialite_edit,        name='medecins_specialite_edit'),

    # Départements (Services)
    path('medecins/departements/',                   medecins_views.services_list,       name='medecins_departements'),
    path('medecins/departements/nouveau/',           medecins_views.service_create,      name='medecins_departement_create'),
    path('medecins/departements/bulk-delete/',       medecins_views.service_bulk_delete, name='medecins_departement_bulk_delete'),
    path('medecins/departements/<int:pk>/',          medecins_views.service_detail,      name='medecins_departement_detail'),
    path('medecins/departements/<int:pk>/modifier/', medecins_views.service_edit,        name='medecins_departement_edit'),
    path('consultations/', views.consultations_list, name='consultations_list'),
    path('soins/', include('soins.urls')),
    path('services/', include('services.urls')),
    path('pharmacie/', views.pharmacie_list, name='pharmacie_list'),
    path('ordonnances/', views.ordonnances_list, name='ordonnances_list'),
    path('laboratoire/', views.laboratoire_list, name='laboratoire_list'),
    path('hospitalisation/', include('hospitalisation.urls')),
    path('facturation/', include('facturation.urls')),
    path('laboratoire/nouvelle/', views.laboratoire_create, name='laboratoire_create'),
    path('caisse/', views.caisse_list, name='caisse_list'),
    path('employes/', include('employer.urls')),
    path('stock/', include('stock.urls')),
    path('planning/', include('planning.urls')),
    path('presence/', include('presence.urls')),
    path('rapports/', views.rapports_list, name='rapports_list'),
    path('gynecologie/', views.gynecologie_list, name='gynecologie_list'),
    path('gynecologie/rdv/', views.gynecologie_rdv, name='gynecologie_rdv'),
    path('gynecologie/rdv/nouveau/', views.gynecologie_rdv_create, name='gynecologie_rdv_create'),
    path('gynecologie/rdv/<int:pk>/', views.gynecologie_rdv_detail, name='gynecologie_rdv_detail'),
    path('gynecologie/naissances/', views.gynecologie_registre_naissance, name='gynecologie_naissances'),
    path('gynecologie/naissances/nouveau/', views.gynecologie_naissance_create, name='gynecologie_naissance_create'),
]
