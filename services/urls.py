from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services_list, name='list'),
    path('nouveau/', views.service_form, name='create'),
    path('<int:pk>/', views.service_form, name='detail'),
    path('<int:pk>/regles-prix/', views.regles_prix, name='regles_prix'),
    path('supprimer-selection/', views.service_bulk_delete, name='service_bulk_delete'),

    # Catégories de service
    path('categories/', views.categories_list, name='categories'),
    path('categories/nouveau/', views.categorie_create, name='categorie_create'),
    path('categories/<int:pk>/modifier/', views.categorie_edit, name='categorie_edit'),
    path('categories/<int:pk>/supprimer/', views.categorie_delete, name='categorie_delete'),
    path('categories/supprimer-selection/', views.categorie_bulk_delete, name='categorie_bulk_delete'),

    # Unités de mesure
    path('unites/', views.unites_list, name='unites'),
    path('unites/nouveau/', views.unite_create, name='unite_create'),
    path('unites/<int:pk>/modifier/', views.unite_edit, name='unite_edit'),
    path('unites/<int:pk>/supprimer/', views.unite_delete, name='unite_delete'),
    path('unites/supprimer-selection/', views.unite_bulk_delete, name='unite_bulk_delete'),

    # Catégories d'unités de mesure
    path('unites/categories/', views.categories_unites_list, name='categories_unites'),
    path('unites/categories/nouveau/', views.categorie_unite_create, name='categorie_unite_create'),
    path('unites/categories/<int:pk>/modifier/', views.categorie_unite_edit, name='categorie_unite_edit'),
    path('unites/categories/<int:pk>/supprimer/', views.categorie_unite_delete, name='categorie_unite_delete'),
    path('unites/categories/supprimer-selection/', views.categorie_unite_bulk_delete, name='categorie_unite_bulk_delete'),

    # Consommables
    path('consommables/', views.consommables_list, name='consommables'),
    path('consommables/nouveau/', views.consommable_create, name='consommable_create'),
    path('consommables/<int:pk>/modifier/', views.consommable_edit, name='consommable_edit'),
    path('consommables/<int:pk>/supprimer/', views.consommable_delete, name='consommable_delete'),
    path('consommables/supprimer-selection/', views.consommable_bulk_delete, name='consommable_bulk_delete'),

    # Types de service
    path('types/', views.types_list, name='types'),
    path('types/nouveau/', views.type_create, name='type_create'),
    path('types/<int:pk>/modifier/', views.type_edit, name='type_edit'),
    path('types/<int:pk>/supprimer/', views.type_delete, name='type_delete'),
    path('types/supprimer-selection/', views.type_bulk_delete, name='type_bulk_delete'),

    path('ajax/fournisseur-ligne/', views.ajax_add_fournisseur, name='ajax_fournisseur'),
    path('ajax/conditionn-ligne/', views.ajax_add_conditionnement, name='ajax_conditionnement'),
    path('ajax/variante-ligne/', views.ajax_add_variante, name='ajax_variante'),
    path('ajax/regle-prix-ligne/', views.ajax_add_regle_prix, name='ajax_regle_prix'),
    path('ajax/delete-ligne/<str:model>/<int:pk>/', views.ajax_delete_ligne, name='ajax_delete_ligne'),
]
