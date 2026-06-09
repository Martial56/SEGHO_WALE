from django.urls import path
from . import views

app_name = 'facturation'

urlpatterns = [
    path('', views.facturation_list, name='list'),
    path('nouvelle/', views.facture_create, name='create'),
    path('<int:pk>/modifier/', views.facture_edit, name='edit'),
]
