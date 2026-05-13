from django.urls import path
from . import views

urlpatterns = [
    path('', views.ordonnance_list, name='ordonnances_list'),
    path('nouveau/', views.ordonnance_create, name='ordonnance_create'),
    path('<int:pk>/', views.ordonnance_detail, name='ordonnance_detail'),
    path('<int:pk>/modifier/', views.ordonnance_edit, name='ordonnance_edit'),
    path('<int:pk>/prescrire/', views.ordonnance_prescrire, name='ordonnance_prescrire'),

    # Configuration — Groupes de médicaments
    path('groupes/', views.groupe_medicaments_list, name='groupe_medicaments_list'),
    path('groupes/nouveau/', views.groupe_medicaments_create, name='groupe_medicaments_create'),
    path('groupes/<int:pk>/modifier/', views.groupe_medicaments_edit, name='groupe_medicaments_edit'),
    path('groupes/<int:pk>/supprimer/', views.groupe_medicaments_delete, name='groupe_medicaments_delete'),

    # Configuration — Maladies
    path('maladies/', views.maladie_list, name='maladie_list'),
    path('maladies/nouveau/', views.maladie_create, name='maladie_create'),
    path('maladies/<int:pk>/modifier/', views.maladie_edit, name='maladie_edit'),
    path('maladies/<int:pk>/supprimer/', views.maladie_delete, name='maladie_delete'),
]
