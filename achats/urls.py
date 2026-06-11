from django.urls import path
from . import views

app_name = 'achats'

urlpatterns = [
    path('', views.achats_dashboard, name='dashboard'),

    # Fournisseurs
    path('fournisseurs/', views.fournisseurs_list, name='fournisseurs_list'),
    path('fournisseurs/nouveau/', views.fournisseur_create, name='fournisseur_create'),
    path('fournisseurs/<int:pk>/', views.fournisseur_detail, name='fournisseur_detail'),
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_edit, name='fournisseur_edit'),

    # Besoins d'achat
    path('besoins/', views.besoins_list, name='besoins_list'),
    path('besoins/nouveau/', views.besoin_create, name='besoin_create'),
    path('besoins/<int:pk>/', views.besoin_detail, name='besoin_detail'),
    path('besoins/<int:pk>/modifier/', views.besoin_edit, name='besoin_edit'),
    path('besoins/<int:pk>/statut/', views.besoin_changer_statut, name='besoin_statut'),

    # Proformas
    path('proformas/', views.proformas_list, name='proformas_list'),
    path('proformas/besoin/<int:besoin_pk>/nouveau/', views.proforma_create, name='proforma_create'),
    path('proformas/<int:pk>/', views.proforma_detail, name='proforma_detail'),
    path('proformas/<int:pk>/modifier/', views.proforma_edit, name='proforma_edit'),
    path('proformas/<int:pk>/valider/', views.proforma_valider, name='proforma_valider'),
    path('proformas/<int:pk>/rejeter/', views.proforma_rejeter, name='proforma_rejeter'),

    # Commandes d'achat
    path('commandes/', views.commandes_list, name='commandes_list'),
    path('commandes/creer/<int:proforma_pk>/', views.commande_create, name='commande_create'),
    path('commandes/<int:pk>/', views.commande_detail, name='commande_detail'),
    path('commandes/<int:pk>/statut/', views.commande_changer_statut, name='commande_statut'),
    path('commandes/<int:pk>/imprimer/', views.commande_imprimer, name='commande_imprimer'),

    # Réceptions
    path('commandes/<int:commande_pk>/reception/', views.reception_create, name='reception_create'),
    path('receptions/<int:pk>/', views.reception_detail, name='reception_detail'),

    # API
    path('api/produits/', views.api_produits, name='api_produits'),
]
