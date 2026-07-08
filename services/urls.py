from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services_list, name='list'),
    path('nouveau/', views.service_form, name='create'),
    path('<int:pk>/', views.service_detail, name='detail'),
    path('<int:pk>/modifier/', views.service_form, name='edit'),
    path('<int:pk>/regles-prix/', views.regles_prix, name='regles_prix'),

    # Catégories de service
    path('categories/', views.categories_list, name='categories'),
    path('categories/nouveau/', views.categorie_create, name='categorie_create'),
    path('categories/<int:pk>/', views.categorie_detail, name='categorie_detail'),
    path('categories/<int:pk>/modifier/', views.categorie_edit, name='categorie_edit'),
    path('categories/<int:pk>/supprimer/', views.categorie_delete, name='categorie_delete'),

    # Unités de mesure — désactivé à la demande (menu réduit à Prestations/Catégories)
    # path('unites/', views.unites_list, name='unites'),
    # path('unites/nouveau/', views.unite_create, name='unite_create'),
    # path('unites/<int:pk>/', views.unite_detail, name='unite_detail'),
    # path('unites/<int:pk>/modifier/', views.unite_edit, name='unite_edit'),
    # path('unites/<int:pk>/supprimer/', views.unite_delete, name='unite_delete'),

    # Catégories d'unités de mesure — désactivé (idem)
    # path('unites/categories/', views.categories_unites_list, name='categories_unites'),
    # path('unites/categories/nouveau/', views.categorie_unite_create, name='categorie_unite_create'),
    # path('unites/categories/<int:pk>/', views.categorie_unite_detail, name='categorie_unite_detail'),
    # path('unites/categories/<int:pk>/modifier/', views.categorie_unite_edit, name='categorie_unite_edit'),
    # path('unites/categories/<int:pk>/supprimer/', views.categorie_unite_delete, name='categorie_unite_delete'),

    path('ajax/fournisseur-ligne/', views.ajax_add_fournisseur, name='ajax_fournisseur'),
    path('ajax/conditionn-ligne/', views.ajax_add_conditionnement, name='ajax_conditionnement'),
    path('ajax/variante-ligne/', views.ajax_add_variante, name='ajax_variante'),
    path('ajax/regle-prix-ligne/', views.ajax_add_regle_prix, name='ajax_regle_prix'),
    path('ajax/delete-ligne/<str:model>/<int:pk>/', views.ajax_delete_ligne, name='ajax_delete_ligne'),

    # ── Export ────────────────────────────────────────────────────────────────
    path('export/articles/',          views.export_articles,          name='export_articles'),
    path('export/categories/',        views.export_categories,        name='export_categories'),
    # path('export/unites/',            views.export_unites,            name='export_unites'),
    # path('export/categories-unites/', views.export_categories_unites, name='export_categories_unites'),

    # ── Import ────────────────────────────────────────────────────────────────
    path('importer/articles/',          views.import_articles,          name='import_articles'),
    path('importer/categories/',        views.import_categories,        name='import_categories'),
    # path('importer/unites/',            views.import_unites,            name='import_unites'),
    # path('importer/categories-unites/', views.import_categories_unites, name='import_categories_unites'),
]
