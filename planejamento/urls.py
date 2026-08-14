from django.urls import path

from planejamento.views import (
    atualizar_cronograma,
    atualizar_cronograma_suprimentos,
    historico_importacoes_cronograma,
    historico_importacoes_cronograma_suprimentos,
    kanban_cronograma_suprimentos,
    painel_cronograma,
    painel_cronograma_suprimentos,
    salvar_datas_item_cronograma_suprimentos,
)

app_name = "planejamento"

urlpatterns = [
    path("cronograma/", painel_cronograma, name="painel_cronograma"),
    path("cronograma/atualizar/", atualizar_cronograma, name="atualizar_cronograma"),
    path("cronograma/importacoes/", historico_importacoes_cronograma, name="historico_importacoes_cronograma"),
    path("suprimentos/", painel_cronograma_suprimentos, name="painel_cronograma_suprimentos"),
    path("suprimentos/kanban/", kanban_cronograma_suprimentos, name="kanban_cronograma_suprimentos"),
    path("suprimentos/atualizar/", atualizar_cronograma_suprimentos, name="atualizar_cronograma_suprimentos"),
    path("suprimentos/importacoes/", historico_importacoes_cronograma_suprimentos, name="historico_importacoes_cronograma_suprimentos"),
    path(
        "suprimentos/itens/<int:item_id>/datas/salvar/",
        salvar_datas_item_cronograma_suprimentos,
        name="salvar_datas_item_cronograma_suprimentos",
    ),
]
