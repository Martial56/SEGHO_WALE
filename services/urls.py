from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services_list, name='list'),
    path('nouveau/', views.service_form, name='create'),
    path('<int:pk>/', views.service_form, name='detail'),
    path('<int:pk>/regles-prix/', views.regles_prix, name='regles_prix'),
    path('ajax/fournisseur-ligne/', views.ajax_add_fournisseur, name='ajax_fournisseur'),
    path('ajax/conditionn-ligne/', views.ajax_add_conditionnement, name='ajax_conditionnement'),
    path('ajax/variante-ligne/', views.ajax_add_variante, name='ajax_variante'),
    path('ajax/regle-prix-ligne/', views.ajax_add_regle_prix, name='ajax_regle_prix'),
    path('ajax/delete-ligne/<str:model>/<int:pk>/', views.ajax_delete_ligne, name='ajax_delete_ligne'),
]
