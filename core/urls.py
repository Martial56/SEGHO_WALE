from django.urls import path, include
from django.views.generic import RedirectView
from . import views
from facturation.views import (
    facturation_create, facture_detail, facture_edit,
    facture_valider, facture_annuler,
)

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # URLs des modules (patients et medecins sont gérés dans medisoft/urls.py)
    path('soins/', views.soins_list, name='soins_list'),

    path('laboratoire/', views.laboratoire_list, name='laboratoire_list'),
    path('hospitalisation/', views.hospitalisation_list, name='hospitalisation_list'),
    path('facturation/', views.facturation_list, name='facturation_list'),
    path('facturation/creer/', facturation_create, name='facturation_create'),
    path('facturation/<int:pk>/', facture_detail, name='facture_detail'),
    path('facturation/<int:pk>/modifier/', facture_edit, name='facture_edit'),
    path('facturation/<int:pk>/valider/', facture_valider, name='facture_valider'),
    path('facturation/<int:pk>/annuler/', facture_annuler, name='facture_annuler'),
    path('caisse/', views.caisse_list, name='caisse_list'),
    path('rapports/', views.rapports_list, name='rapports_list'),
    path('ressources-humaines/', RedirectView.as_view(pattern_name='employer:ressources_humaines_list', permanent=True)),

    # Gynécologie
    path('gynecologie/', views.gynecologie_list, name='gynecologie_list'),
    path('gynecologie/rdv/', views.gynecologie_rdv, name='gynecologie_rdv'),
    path('gynecologie/rdv/nouveau/', views.gynecologie_rdv_create, name='gynecologie_rdv_create'),
    path('gynecologie/rdv/bulk/', views.gynecologie_rdv_bulk, name='gynecologie_rdv_bulk'),
    path('gynecologie/rdv/calendrier/', views.gynecologie_rdv_calendrier, name='gynecologie_rdv_calendrier'),
    path('gynecologie/rdv/kanban/', views.gynecologie_rdv_kanban, name='gynecologie_rdv_kanban'),
    path('gynecologie/cpn/suivi/', views.gynecologie_cpn_suivi, name='gynecologie_cpn_suivi'),
    path('gynecologie/rdv/<int:pk>/', views.gynecologie_rdv_detail, name='gynecologie_rdv_detail'),
    path('gynecologie/rdv/<int:pk>/statut/', views.gynecologie_rdv_set_statut, name='gynecologie_rdv_set_statut'),
    path('gynecologie/naissances/', views.gynecologie_registre_naissance, name='gynecologie_naissances'),
    path('gynecologie/naissances/nouveau/', views.gynecologie_naissance_create, name='gynecologie_naissance_create'),
]
