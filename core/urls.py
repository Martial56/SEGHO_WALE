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
    path('pharmacie/', views.pharmacie_list, name='pharmacie_list'),
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
    path('ressources-humaines/', RedirectView.as_view(pattern_name='personnel:list', permanent=True)),
]
