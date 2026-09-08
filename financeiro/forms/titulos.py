from django import forms

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from .cadastros import ERPModelForm


class TituloPagarForm(ERPModelForm):
    class Meta:
        model = TituloPagar
        fields = (
            "origem", "fornecedor", "obra", "plano_financeiro", "descricao",
            "documento_numero", "arquivo_documento", "data_emissao", "competencia",
            "vencimento", "valor_original", "desconto", "juros", "multa",
            "outros_acrescimos", "observacao",
        )
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "competencia": forms.DateInput(attrs={"type": "date"}),
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, titulo_integrado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.titulo_integrado = titulo_integrado
        self.fields["fornecedor"].empty_label = "Selecione o fornecedor"
        self.fields["obra"].empty_label = "Selecione a obra"
        self.fields["plano_financeiro"].empty_label = "Selecione a classificação"
        if titulo_integrado and titulo_integrado.pedido_id:
            for campo in ("origem", "fornecedor", "obra"):
                self.fields[campo].disabled = True


class PrevisaoFinanceiraForm(ERPModelForm):
    """Previsão manual: o usuário informa somente o necessário.

    Origem e nível de certeza são definidos pelo sistema para evitar uma tela
    confusa com conceitos internos do Financeiro.
    """

    class Meta:
        model = PrevisaoFinanceira
        fields = (
            "descricao", "obra", "fornecedor", "plano_financeiro",
            "data_prevista", "valor_previsto", "observacao",
        )
        widgets = {
            "data_prevista": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }


class PagamentoForm(ERPModelForm):
    class Meta:
        model = Pagamento
        fields = (
            "data_pagamento", "forma", "referencia_bancaria",
            "comprovante", "observacao",
        )
        widgets = {
            "data_pagamento": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
