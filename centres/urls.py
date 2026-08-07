from django.urls import path

from . import views

urlpatterns = [
    path('changer/<int:centre_id>/', views.changer_centre, name='changer_centre'),
]
