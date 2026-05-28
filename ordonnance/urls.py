from django.urls import path
from . import views

urlpatterns = [
    path('',                                  views.ordonnance_list,           name='ordonnance_list'),
    path('consultations/',                    views.consultation_search,       name='consultation_search'),
    path('medicaments/',                      views.medicament_search,         name='medicament_search'),
    path('nouvelle/<int:consultation_pk>/',   views.ordonnance_create,         name='ordonnance_create'),
    path('<int:pk>/',                         views.ordonnance_detail,         name='ordonnance_detail'),
    path('<int:pk>/imprimer/',                views.ordonnance_print,          name='ordonnance_print'),
    path('<int:pk>/statut/',                  views.ordonnance_changer_statut, name='ordonnance_statut'),
]
