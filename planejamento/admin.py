from django.contrib import admin

from planejamento.models import (
    AtividadeCronograma,
    ChecklistCronograma,
    Disciplina,
    ImportacaoCronograma,
    Marco,
)


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = [
        "nome",
        "codigo",
        "estrutural",
        "ordem",
        "ativa",
    ]

    list_filter = [
        "estrutural",
        "ativa",
    ]

    search_fields = [
        "nome",
        "codigo",
    ]

    ordering = [
        "ordem",
        "nome",
    ]


@admin.register(ImportacaoCronograma)
class ImportacaoCronogramaAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "obra",
        "data_referencia",
        "semana_inicial",
        "semana_final",
        "total_atividades",
        "ativa",
        "criado_em",
    ]

    list_filter = [
        "ativa",
        "data_referencia",
        "obra",
    ]

    search_fields = [
        "obra__nome",
        "observacoes",
    ]

    ordering = [
        "-data_referencia",
        "-criado_em",
    ]


@admin.register(AtividadeCronograma)
class AtividadeCronogramaAdmin(admin.ModelAdmin):
    list_display = [
        "nome_tarefa",
        "obra",
        "semana",
        "disciplina",
        "local_tarefa",
        "percentual_previsto",
        "percentual_executado",
        "data_atualizacao",
    ]

    list_filter = [
        "obra",
        "disciplina",
        "semana",
        "data_atualizacao",
    ]

    search_fields = [
        "nome_tarefa",
        "local_tarefa",
        "responsavel",
        "nome_projeto_original",
    ]

    ordering = [
        "obra",
        "semana",
        "nome_tarefa",
    ]

    raw_id_fields = [
        "importacao_cronograma",
        "obra",
        "disciplina",
    ]


@admin.register(Marco)
class MarcoAdmin(admin.ModelAdmin):
    list_display = [
        "nome",
        "obra",
        "semana",
        "data_prevista",
        "data_realizada",
        "concluido",
    ]

    list_filter = [
        "obra",
        "concluido",
        "data_prevista",
    ]

    search_fields = [
        "nome",
        "obra__nome",
    ]

    raw_id_fields = [
        "importacao_cronograma",
        "atividade_origem",
    ]


@admin.register(ChecklistCronograma)
class ChecklistCronogramaAdmin(admin.ModelAdmin):
    list_display = [
        "nome",
        "obra",
        "tipo",
        "semana",
        "percentual_concluido",
        "concluido",
    ]

    list_filter = [
        "obra",
        "tipo",
        "concluido",
    ]

    search_fields = [
        "nome",
        "local",
        "valor_original",
        "obra__nome",
    ]

    raw_id_fields = [
        "importacao_cronograma",
        "atividade_origem",
    ]