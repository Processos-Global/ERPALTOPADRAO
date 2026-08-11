from django.urls import path

from planejamento.views import (
    adicionar_suprimento_atividade,
    atualizar_cronograma,
    atualizar_cronograma_suprimentos,
    cadastrar_insumo_planejamento,
    desativar_insumo_planejamento,
    editar_insumo_planejamento,
    editar_suprimento_atividade,
    excluir_suprimento_atividade,
    historico_importacoes_cronograma,
    historico_importacoes_cronograma_suprimentos,
    kanban_cronograma_suprimentos,
    painel_cronograma,
    painel_cronograma_suprimentos,
    salvar_datas_item_cronograma_suprimentos,
)


app_name = "planejamento"


urlpatterns = [
    # Cronograma físico
    path(
        "cronograma/",
        painel_cronograma,
        name="painel_cronograma",
    ),
    path(
        "cronograma/atualizar/",
        atualizar_cronograma,
        name="atualizar_cronograma",
    ),
    path(
        "cronograma/importacoes/",
        historico_importacoes_cronograma,
        name="historico_importacoes_cronograma",
    ),

    # Cronograma real de suprimentos
    path(
        "suprimentos/",
        painel_cronograma_suprimentos,
        name="painel_cronograma_suprimentos",
    ),
    path(
        "suprimentos/kanban/",
        kanban_cronograma_suprimentos,
        name="kanban_cronograma_suprimentos",
    ),
    path(
        "suprimentos/atualizar/",
        atualizar_cronograma_suprimentos,
        name="atualizar_cronograma_suprimentos",
    ),
    path(
        "suprimentos/importacoes/",
        historico_importacoes_cronograma_suprimentos,
        name="historico_importacoes_cronograma_suprimentos",
    ),
    path(
        "suprimentos/itens/<int:item_id>/datas/salvar/",
        salvar_datas_item_cronograma_suprimentos,
        name="salvar_datas_item_cronograma_suprimentos",
    ),

    # Catálogo de insumos
    path(
        "cronograma/insumos/cadastrar/",
        cadastrar_insumo_planejamento,
        name="cadastrar_insumo_planejamento",
    ),
    path(
        "cronograma/insumos/<int:insumo_id>/editar/",
        editar_insumo_planejamento,
        name="editar_insumo_planejamento",
    ),
    path(
        "cronograma/insumos/<int:insumo_id>/desativar/",
        desativar_insumo_planejamento,
        name="desativar_insumo_planejamento",
    ),

    # Orçamento de suprimentos por atividade
    path(
        "cronograma/atividades/<int:atividade_id>/suprimentos/adicionar/",
        adicionar_suprimento_atividade,
        name="adicionar_suprimento_atividade",
    ),
    path(
        "cronograma/suprimentos/<int:suprimento_id>/editar/",
        editar_suprimento_atividade,
        name="editar_suprimento_atividade",
    ),
    path(
        "cronograma/suprimentos/<int:suprimento_id>/excluir/",
        excluir_suprimento_atividade,
        name="excluir_suprimento_atividade",
    ),
]
