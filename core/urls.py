from django.urls import path

from .views import nearest_evac_centers_api

urlpatterns = [
    path("evac-centers/", nearest_evac_centers_api, name="evac-centers-api"),
]
