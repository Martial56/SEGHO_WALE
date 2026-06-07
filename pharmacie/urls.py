from django.urls import path
from . import views

app_name = 'pharmacie'

urlpatterns = [
    path('', views.ordonnance_list, name='ordonnance_list'),
    path('creer/', views.ordonnance_create, name='ordonnance_create'),
    path('<int:pk>/', views.ordonnance_detail, name='ordonnance_detail'),
]
