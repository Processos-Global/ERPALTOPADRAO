from django.urls import path

from orcamento import views

app_name = "orcamento"

urlpatterns = [
    path("", views.menu_orcamento, name="menu"),
    path("obras/", views.lista_obras, name="obras"),
    path("obras/<int:obra_id>/", views.detalhe_orcamento, name="detalhe_orcamento"),
    path("obras/<int:obra_id>/insumos/", views.lista_insumos, name="insumos"),
    path(
        "insumos/<int:insumo_id>/alternar-mao-de-obra/",
        views.alternar_mao_de_obra_view,
        name="alternar_mao_de_obra",
    ),
    path("atualizar/", views.painel_orcamento, name="atualizar"),
    path("atualizar/executar/", views.atualizar_orcamento_view, name="atualizar_executar"),
]
