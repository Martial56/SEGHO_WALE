from django.urls import path
from . import views

app_name = 'medicament'

urlpatterns = [
    path('',                           views.medicament_list,   name='list'),
    path('nouveau/',                   views.medicament_create, name='create'),
    path('<int:pk>/',                  views.medicament_detail, name='detail'),
    path('<int:pk>/modifier/',         views.medicament_edit,   name='edit'),
    path('<int:pk>/mouvement/',        views.mouvement_add,     name='mouvement_add'),

    path('groupes/',                   views.groupe_list,   name='groupe_list'),
    path('groupes/nouveau/',           views.groupe_create, name='groupe_create'),
    path('groupes/<int:pk>/',          views.groupe_detail, name='groupe_detail'),
    path('groupes/<int:pk>/modifier/', views.groupe_edit,   name='groupe_edit'),

    path('config/compagnie/',              views.config_compagnie, name='config_compagnie'),
    path('config/compagnie/<int:pk>/',     views.config_compagnie, name='config_compagnie_edit'),
    path('config/effet/',                  views.config_effet,     name='config_effet'),
    path('config/effet/<int:pk>/',         views.config_effet,     name='config_effet_edit'),
    path('config/dosage/',                 views.config_dosage,    name='config_dosage'),
    path('config/dosage/<int:pk>/',        views.config_dosage,    name='config_dosage_edit'),
    path('config/route/',                  views.config_route,     name='config_route'),
    path('config/route/<int:pk>/',         views.config_route,     name='config_route_edit'),
    path('config/formulaire/',             views.config_formulaire,   name='config_formulaire'),
    path('config/formulaire/<int:pk>/',    views.config_formulaire,   name='config_formulaire_edit'),
]
