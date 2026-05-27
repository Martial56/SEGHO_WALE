from django.urls import path
from . import views

app_name = 'parametres'

urlpatterns = [
    path('', views.parametres_dashboard, name='dashboard'),
    path('groupes/', views.groupes_list, name='groupes'),
    path('groupes/creer/', views.groupe_create, name='groupe_create'),
    path('groupes/<int:group_id>/modifier/', views.groupe_edit, name='groupe_edit'),
    path('groupes/<int:group_id>/supprimer/', views.groupe_delete, name='groupe_delete'),
    path('comptes/', views.comptes_list, name='comptes'),
    path('comptes/creer/', views.compte_create, name='compte_create'),
    path('comptes/<int:user_id>/modifier/', views.compte_edit, name='compte_edit'),
    path('comptes/<int:user_id>/toggle-actif/', views.compte_toggle_active, name='compte_toggle_active'),
]
