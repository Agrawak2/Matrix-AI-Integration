from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path('', views.index, name='gateway-index'),
    path('api/', views.api, name='gateway-api'),
    path('health/', views.health, name='gateway-health'),
]
