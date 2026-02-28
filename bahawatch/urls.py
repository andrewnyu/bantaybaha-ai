from django.contrib import admin
from django.urls import include, path

from core.views import index

urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("api/", include("risk.urls")),
    path("api/", include("core.urls")),
    path("api/", include("routing.urls")),
    path("api/", include("chat.urls")),
]
