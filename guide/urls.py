from django.urls import path
from . import views

app_name = 'guide'

urlpatterns = [
    path('', views.guide_hub, name='hub'),
    path('<slug:code>/', views.guide_categorie, name='categorie'),
]
