from django.urls import path
from . import views

app_name = 'facturation'

urlpatterns = [
    path('', views.facturation_list, name='list'),
    path('nouvelle/', views.facture_create, name='create'),
    path('<int:pk>/', views.facture_detail, name='detail'),
    path('<int:pk>/modifier/', views.facture_edit, name='edit'),
    path('<int:pk>/valider/', views.facture_valider, name='valider'),
    path('<int:pk>/payer/', views.facture_payer, name='payer'),
    path('<int:pk>/imprimer/', views.facture_print, name='print'),
    path('<int:pk>/apercu/', views.facture_apercu, name='apercu'),

    # Configuration
    path('configuration/caisses/', views.caisses_list, name='caisses_list'),
    path('configuration/caisses/nouvelle/', views.caisse_create, name='caisse_create'),
    path('configuration/caisses/<int:pk>/modifier/', views.caisse_edit, name='caisse_edit'),
    path('configuration/caisses/<int:pk>/supprimer/', views.caisse_delete, name='caisse_delete'),
]
