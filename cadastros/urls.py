from django.urls import path

from cadastros import views

app_name = "cadastros"

urlpatterns = [
    path("", views.index, name="index"),
    path("materiais/", views.materiais_lista, name="materiais_lista"),
    path("materiais/novo/", views.material_novo, name="material_novo"),
    path("materiais/<int:pk>/editar/", views.material_editar, name="material_editar"),
    path("materiais/<int:pk>/excluir/", views.material_excluir, name="material_excluir"),
    path("fornecedores/", views.fornecedores_lista, name="fornecedores_lista"),
    path("fornecedores/novo/", views.fornecedor_novo, name="fornecedor_novo"),
    path("fornecedores/<int:pk>/editar/", views.fornecedor_editar, name="fornecedor_editar"),
    path("fornecedores/<int:pk>/excluir/", views.fornecedor_excluir, name="fornecedor_excluir"),
    path("mao-de-obra/", views.mao_obra_lista, name="mao_obra_lista"),
    path("mao-de-obra/nova/", views.mao_obra_nova, name="mao_obra_nova"),
    path("mao-de-obra/<int:pk>/editar/", views.mao_obra_editar, name="mao_obra_editar"),
    path("mao-de-obra/<int:pk>/excluir/", views.mao_obra_excluir, name="mao_obra_excluir"),
]
