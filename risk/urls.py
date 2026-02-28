from django.urls import path

from .views import risk_api

urlpatterns = [
    path("risk/", risk_api, name="risk-api"),
]
