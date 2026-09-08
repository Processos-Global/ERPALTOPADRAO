from django.contrib import admin

from financeiro.models import (
    DespesaRecorrente,
    Pagamento,
    PlanoFinanceiro,
    PrevisaoFinanceira,
    TituloPagar,
)


@admin.register(TituloPagar)
class TituloPagarAdmin(admin.ModelAdmin):
    list_display = ("numero", "fornecedor", "obra", "vencimento", "valor_original", "status", "conferencia")
    list_filter = ("status", "origem", "conferencia", "obra")
    search_fields = ("numero", "documento_numero", "descricao", "fornecedor__nome")


admin.site.register(PlanoFinanceiro)
admin.site.register(PrevisaoFinanceira)
admin.site.register(DespesaRecorrente)
admin.site.register(Pagamento)
