from django.urls import path
from . import views

app_name = 'journal'

urlpatterns = [
    path('', views.journal_list, name='list'),
    path('supprimer-selection/', views.journal_supprimer_selection, name='supprimer_selection'),
    path('vider/', views.journal_vider, name='vider'),
]
