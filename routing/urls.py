from django.urls import path

from .views import safe_route_api

urlpatterns = [
    path("safe-route/", safe_route_api, name="safe-route-api"),
]
