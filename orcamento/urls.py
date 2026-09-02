from django.urls import path

from orcamento import views

app_name = "orcamento"

urlpatterns = [
    path("", views.menu_orcamento, name="menu"),
    path("obras/", views.lista_obras, name="obras"),
    path("inserir/", views.inserir_orcamento, name="inserir"),
]
