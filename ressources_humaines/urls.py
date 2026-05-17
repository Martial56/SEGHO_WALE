from django.urls import path
from . import views

app_name = 'rh'

urlpatterns = [
    # Employés
    path('',                        views.employe_list,   name='list'),
    path('creer/',                  views.employe_create, name='create'),
    path('<int:pk>/modifier/',      views.employe_edit,   name='edit'),
    # Postes
    path('postes/',                 views.poste_list,     name='postes'),
    path('postes/creer/',           views.poste_create,   name='poste_create'),
    path('postes/<int:pk>/modifier/', views.poste_edit,   name='poste_edit'),
    # Congés
    path('conges/',                 views.conge_list,     name='conges'),
    path('conges/creer/',           views.conge_create,   name='conge_create'),
    path('conges/<int:pk>/modifier/', views.conge_edit,   name='conge_edit'),
]
