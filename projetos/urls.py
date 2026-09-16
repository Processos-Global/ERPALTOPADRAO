from django.urls import path

from .views import menu_projetos


app_name = "projetos"


urlpatterns = [
    path("", menu_projetos, name="menu"),
]
