from django.contrib import admin

from integracoes.models import (
    ArquivoImportado,
    ErroImportacao,
    Importacao,
)


class ArquivoImportadoInline(admin.TabularInline):
    model = ArquivoImportado
    extra = 0
    fields = [
        "nome",
        "tipo_arquivo",
        "aba",
        "total_linhas",
        "processado",
    ]
    readonly_fields = fields
    show_change_link = True


class ErroImportacaoInline(admin.TabularInline):
    model = ErroImportacao
    extra = 0
    fields = [
        "nivel",
        "linha",
        "coluna",
        "mensagem",
        "criado_em",
    ]
    readonly_fields = fields
    show_change_link = True


@admin.register(Importacao)
class ImportacaoAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "tipo",
        "origem",
        "status",
        "total_processadas",
        "total_inseridas",
        "total_atualizadas",
        "total_erros",
        "criado_em",
    ]

    list_filter = [
        "tipo",
        "origem",
        "status",
        "criado_em",
    ]

    search_fields = [
        "id",
        "mensagem",
    ]

    readonly_fields = [
        "criado_em",
        "atualizado_em",
    ]

    ordering = [
        "-criado_em",
    ]

    inlines = [
        ArquivoImportadoInline,
        ErroImportacaoInline,
    ]


@admin.register(ArquivoImportado)
class ArquivoImportadoAdmin(admin.ModelAdmin):
    list_display = [
        "nome",
        "tipo_arquivo",
        "aba",
        "importacao",
        "total_linhas",
        "processado",
        "criado_em",
    ]

    list_filter = [
        "tipo_arquivo",
        "processado",
        "criado_em",
    ]

    search_fields = [
        "nome",
        "google_drive_file_id",
        "hash_arquivo",
        "aba",
    ]

    readonly_fields = [
        "criado_em",
        "atualizado_em",
    ]

    ordering = [
        "-criado_em",
    ]


@admin.register(ErroImportacao)
class ErroImportacaoAdmin(admin.ModelAdmin):
    list_display = [
        "nivel",
        "importacao",
        "arquivo",
        "linha",
        "coluna",
        "mensagem_resumida",
        "criado_em",
    ]

    list_filter = [
        "nivel",
        "criado_em",
    ]

    search_fields = [
        "mensagem",
        "codigo",
        "coluna",
        "valor_original",
    ]

    readonly_fields = [
        "criado_em",
    ]

    ordering = [
        "-criado_em",
    ]

    @admin.display(
        description="Mensagem",
    )
    def mensagem_resumida(self, obj):
        return obj.mensagem[:100]