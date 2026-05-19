from django.urls import path
from . import views

urlpatterns = [
    path('',                    views.presence_registre,       name='presence_registre'),
    path('recap/',              views.presence_recap_mensuel,  name='presence_recap'),
    path('stats/',              views.presence_stats,          name='presence_stats'),
    path('employe/<int:pk>/',   views.presence_employe,        name='presence_employe'),
    path('rapport/',            views.presence_rapport,        name='presence_rapport'),
    # Kiosque
    path('pointage/',           views.presence_pointage,       name='presence_pointage'),
    path('pointage/chercher/',  views.presence_chercher,       name='presence_chercher'),
    path('pointage/pointer/',   views.presence_pointer,        name='presence_pointer'),
]
