from django.urls import path
from obras import views

app_name = "obras"
urlpatterns = [
    path("", views.menu, name="menu"),

    path("fvs/", views.fvs_lista, name="fvs_lista"),
    path("fvs/nova/", views.fvs_nova, name="fvs_nova"),
    path("fvs/ambientes/", views.fvs_ambientes, name="fvs_ambientes"),
    path("fvs/<int:pk>/", views.fvs_detalhe, name="fvs_detalhe"),
    path("fvs/<int:pk>/enviar-aprovacao/", views.fvs_enviar_aprovacao, name="fvs_enviar_aprovacao"),
    path("fvs/<int:pk>/decidir/", views.fvs_decidir, name="fvs_decidir"),

    path("fichas/", views.fichas_tecnicas, name="fichas_tecnicas"),
    path("fichas/<int:obra_id>/", views.ficha_tecnica, name="ficha_tecnica"),
    path("fichas/<int:obra_id>/acao/", views.ficha_tecnica_acao, name="ficha_tecnica_acao"),

    path("almoxarifado/", views.almoxarifado_dashboard, name="almoxarifado_dashboard"),
    path("almoxarifado/<int:obra_id>/", views.almoxarifado_obra, name="almoxarifado_obra"),
    path("almoxarifado/<int:obra_id>/saida/", views.saida_estoque, name="saida_estoque"),
    path("almoxarifado/<int:obra_id>/relatorio-transferencias/", views.relatorio_transferencias, name="relatorio_transferencias"),
    path("almoxarifado/<int:obra_id>/transferencia/", views.transferencia_estoque, name="transferencia_estoque"),

    path("diario/", views.diario_lista, name="diario_lista"),
    path("diario/novo/", views.diario_novo, name="diario_novo"),
    # Mantido para links antigos já salvos/favoritados.
    path("diario/<int:obra_id>/novo/", views.diario_novo, name="diario_novo_obra"),
    path("diario/registro/<int:diario_id>/editar/", views.diario_editar, name="diario_editar"),
]
