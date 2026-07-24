from django.urls import path
from . import views

app_name = 'rapports'

urlpatterns = [
    path('', views.rapports_hub, name='hub'),
    path('historique/', views.rapports_historique, name='historique'),
    path('historique/<int:pk>/telecharger/', views.rapports_retelecharger, name='retelecharger'),
    path('maternite/', views.rapports_maternite, name='maternite'),
    path('soins/', views.rapports_soins, name='soins'),
    path('gynecologie/', views.rapports_gynecologie, name='gynecologie'),
    path('<slug:slug>/', views.rapports_generer, name='generer'),
]
