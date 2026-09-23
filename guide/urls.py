from django.urls import path
from . import views

app_name = 'guide'

urlpatterns = [
    path('', views.guide_couverture, name='couverture'),
    path('sommaire/', views.guide_hub, name='hub'),
    path('sommaire/<int:page>/', views.guide_hub, name='hub'),
    path('page/<int:numero>/', views.guide_page, name='page'),
    path('dos/', views.guide_dos, name='dos'),
    path('<slug:code>/', views.guide_categorie, name='categorie'),
]
