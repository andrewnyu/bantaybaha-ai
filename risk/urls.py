from django.urls import path

from .views import risk_api, risk_area_api

urlpatterns = [
    path("risk/", risk_api, name="risk-api"),
    path("risk-area/", risk_area_api, name="risk-area-api"),
]
