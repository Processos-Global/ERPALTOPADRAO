from django.contrib import admin

from planejamento.models import (
    ImportacaoCronograma,
    RegistroCronograma,
)


@admin.register(ImportacaoCronograma)
class ImportacaoCronogramaAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "nome_arquivo",
        "status",
        "ativa",
        "linhas_importadas",
        "projetos_identificados",
        "semanas_identificadas",
        "data_modificacao_drive",
        "iniciou_em",
        "finalizou_em",
    ]

    list_filter = [
        "status",
        "ativa",
        "data_modificacao_drive",
        "criado_em",
    ]

    search_fields = [
        "nome_arquivo",
        "arquivo_drive_id",
        "hash_arquivo",
        "mensagem",
        "erro_detalhado",
        "executado_por__username",
        "executado_por__email",
    ]

    readonly_fields = [
        "status",
        "ativa",
        "nome_arquivo",
        "arquivo_drive_id",
        "data_modificacao_drive",
        "hash_arquivo",
        "tamanho_arquivo_bytes",
        "total_linhas_arquivo",
        "linhas_importadas",
        "projetos_identificados",
        "semanas_identificadas",
        "mensagem",
        "erro_detalhado",
        "executado_por",
        "iniciou_em",
        "finalizou_em",
        "criado_em",
        "atualizado_em",
    ]

    ordering = ["-criado_em"]
    date_hierarchy = "criado_em"
    list_per_page = 50

    def has_add_permission(self, request):
        return False


@admin.register(RegistroCronograma)
class RegistroCronogramaAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "projeto",
        "semana",
        "disciplina",
        "nome_tarefa_resumida",
        "inicio_base",
        "termino_base",
        "inicio_real",
        "termino_real",
        "reprogramada",
        "responsavel",
        "data_atualizacao",
        "importacao",
    ]

    list_filter = [
        "importacao",
        "projeto",
        "semana",
        "disciplina",
        "reprogramada",
        "responsavel",
        "data_atualizacao",
    ]

    search_fields = [
        "projeto",
        "local_tarefa",
        "nome_tarefa",
        "disciplina",
        "responsavel",
        "chave_atividade",
        "checklist_habitese",
        "checklist_cef",
    ]

    readonly_fields = [
        "importacao",
        "projeto",
        "tipo",
        "quantidade_unidades",
        "semana",
        "data_atualizacao",
        "local_tarefa",
        "nome_tarefa",
        "inicio_real",
        "duracao_real",
        "termino_real",
        "inicio_base",
        "duracao_base",
        "termino_base",
        "inicio_base_anterior",
        "termino_base_anterior",
        "reprogramada",
        "reprogramada_em",
        "chave_atividade",
        "percentual_concluida",
        "percentual_previsto_tarefa",
        "disciplina",
        "checklist_habitese",
        "checklist_cef",
        "responsavel",
        "peso",
        "percentual_executado",
        "percentual_previsto",
        "inicio_semana",
        "semana_anterior",
        "semana_seguinte",
        "inicio_semana_base",
        "criado_em",
    ]

    ordering = ["projeto", "-semana", "id"]
    list_select_related = ["importacao"]
    list_per_page = 100
    date_hierarchy = "data_atualizacao"

    fieldsets = [
        (
            "Identificação",
            {
                "fields": [
                    "importacao",
                    "projeto",
                    "tipo",
                    "quantidade_unidades",
                    "semana",
                    "data_atualizacao",
                    "chave_atividade",
                ]
            },
        ),
        (
            "Atividade",
            {
                "fields": [
                    "local_tarefa",
                    "nome_tarefa",
                    "disciplina",
                    "responsavel",
                ]
            },
        ),
        (
            "Datas vigentes",
            {
                "fields": [
                    "inicio_base",
                    "termino_base",
                    "inicio_real",
                    "termino_real",
                ]
            },
        ),
        (
            "Reprogramação",
            {
                "fields": [
                    "reprogramada",
                    "inicio_base_anterior",
                    "termino_base_anterior",
                    "reprogramada_em",
                ]
            },
        ),
        (
            "Percentuais",
            {
                "fields": [
                    "peso",
                    "percentual_concluida",
                    "percentual_previsto_tarefa",
                    "percentual_executado",
                    "percentual_previsto",
                ]
            },
        ),
        (
            "Checklists",
            {
                "fields": [
                    "checklist_habitese",
                    "checklist_cef",
                ]
            },
        ),
        (
            "Controle",
            {
                "fields": [
                    "inicio_semana",
                    "semana_anterior",
                    "semana_seguinte",
                    "inicio_semana_base",
                    "criado_em",
                ]
            },
        ),
    ]

    @admin.display(description="Tarefa", ordering="nome_tarefa")
    def nome_tarefa_resumida(self, obj):
        texto = obj.nome_tarefa or "-"
        return texto if len(texto) <= 70 else f"{texto[:70]}..."

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD", "OPTIONS")

    def has_delete_permission(self, request, obj=None):
        return False
