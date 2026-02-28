from django.urls import path

from .views import testing_page


urlpatterns = [
    path("", testing_page, name="testing-page"),
]
