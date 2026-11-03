from django.contrib import admin

from orcamento.models import ArquivoOrcamentoObra, ImportacaoOrcamento, InsumoOrcamento


@admin.register(InsumoOrcamento)
class InsumoOrcamentoAdmin(admin.ModelAdmin):
    list_display = [
        "obra",
        "codigo",
        "tipo",
        "descricao",
        "unid",
        "quant",
        "custo",
        "total",
        "mao_de_obra",
    ]
    list_filter = ["obra", "tipo", "mao_de_obra"]
    search_fields = ["codigo", "codigo_ins", "descricao", "obra__nome"]
    ordering = ["obra", "codigo"]


@admin.register(ArquivoOrcamentoObra)
class ArquivoOrcamentoObraAdmin(admin.ModelAdmin):
    list_display = [
        "obra",
        "nome_arquivo",
        "estrutura_eap_detectada",
        "quantidade_itens",
        "atualizado_em",
    ]
    search_fields = ["obra__nome", "nome_arquivo"]


@admin.register(ImportacaoOrcamento)
class ImportacaoOrcamentoAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "obras_criadas",
        "obras_atualizadas",
        "obras_ignoradas",
        "total_itens_importados",
        "executado_por",
        "criado_em",
    ]
    list_filter = ["status"]
    ordering = ["-criado_em"]
