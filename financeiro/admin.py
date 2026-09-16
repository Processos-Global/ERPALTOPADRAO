from django.contrib import admin

from financeiro.models import DespesaRecorrente, Pagamento, PlanoFinanceiro, PrevisaoFinanceira, TituloPagar


@admin.register(TituloPagar)
class TituloPagarAdmin(admin.ModelAdmin):
    list_display = ("numero", "beneficiario_nome", "origem", "obra", "vencimento", "valor_original", "status")
    list_filter = ("status", "origem", "obra")
    search_fields = ("numero", "documento_numero", "descricao", "beneficiario_nome", "referencia_externa", "fornecedor__nome")
    readonly_fields = ("referencia_externa", "origem_detalhe")


admin.site.register(PlanoFinanceiro)
admin.site.register(PrevisaoFinanceira)
admin.site.register(DespesaRecorrente)
admin.site.register(Pagamento)
