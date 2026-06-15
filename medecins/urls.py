from django.urls import path
from . import views

urlpatterns = [
    # ─── CRUD Médecins ──────────────────────────────────────────────────────
    path('',                                       views.medecins_list,          name='medecins_list'),
    path('export/csv/',                            views.medecins_export_csv,    name='medecins_export_csv'),
    path('nouveau/',                               views.medecin_create,         name='medecin_create'),
    path('dashboard/',                             views.medecin_dashboard,      name='medecin_dashboard'),
    path('<int:pk>/',                              views.medecin_detail,         name='medecin_detail'),
    path('<int:pk>/modifier/',                     views.medecin_edit,           name='medecin_edit'),
    path('<int:pk>/supprimer/',                    views.medecin_supprimer,      name='medecin_supprimer'),

    # ─── Config : Spécialités ────────────────────────────────────────────────
    path('config/specialites/',                    views.specialites_list,       name='medecins_specialites'),
    path('config/specialites/nouveau/',            views.specialite_create,      name='medecins_specialite_create'),
    path('config/specialites/bulk-delete/',        views.specialite_bulk_delete, name='medecins_specialite_bulk_delete'),
    path('config/specialites/<int:pk>/',           views.specialite_detail,      name='medecins_specialite_detail'),
    path('config/specialites/<int:pk>/modifier/',  views.specialite_edit,        name='medecins_specialite_edit'),

    # ─── Config : Départements ───────────────────────────────────────────────
    path('config/departements/',                   views.services_list,          name='medecins_departements'),
    path('config/departements/nouveau/',           views.service_create,         name='medecins_departement_create'),
    path('config/departements/bulk-delete/',       views.service_bulk_delete,    name='medecins_departement_bulk_delete'),
    path('config/departements/<int:pk>/',          views.service_detail,         name='medecins_departement_detail'),
    path('config/departements/<int:pk>/modifier/', views.service_edit,           name='medecins_departement_edit'),
]
