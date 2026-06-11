from django.urls import path
from . import views

app_name = 'pharmacie'

urlpatterns = [
    path('ordonnances/', views.ordonnance_list, name='ordonnance_list'),
    path('ordonnances/creer/', views.ordonnance_create, name='ordonnance_create'),
    path('ordonnances/<int:pk>/', views.ordonnance_detail, name='ordonnance_detail'),
]
