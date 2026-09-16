from django import forms
from django.core.exceptions import ValidationError

from core.validators import validar_documento_upload
from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from .cadastros import ERPModelForm


class TituloPagarForm(ERPModelForm):
    """Formulário curto e operacional para Conta a Pagar."""

    quantidade_parcelas = forms.IntegerField(
        min_value=1,
        max_value=60,
        initial=1,
        required=False,
        label="Quantidade de parcelas",
        help_text="Use 1 para pagamento único. Em lançamento manual, o valor será dividido igualmente.",
    )
    intervalo_dias = forms.IntegerField(
        min_value=1,
        max_value=365,
        initial=30,
        required=False,
        label="Intervalo entre parcelas (dias)",
        help_text="Aplicado a partir do primeiro vencimento.",
    )

    class Meta:
        model = TituloPagar
        fields = (
            "obra",
            "fornecedor",
            "beneficiario_nome",
            "beneficiario_documento",
            "plano_financeiro",
            "descricao",
            "documento_numero",
            "arquivo_documento",
            "data_emissao",
            "vencimento",
            "valor_original",
            "observacao",
        )
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "fornecedor": "Fornecedor cadastrado",
            "beneficiario_nome": "Beneficiário / favorecido",
            "beneficiario_documento": "CPF / CNPJ do beneficiário",
            "plano_financeiro": "Classificação financeira",
            "descricao": "Descrição do pagamento",
            "documento_numero": "Documento / NF",
            "arquivo_documento": "Anexo",
            "valor_original": "Valor",
        }

    def __init__(self, *args, titulo_integrado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.titulo_integrado = titulo_integrado
        self.fields["fornecedor"].empty_label = "Selecione o beneficiário / fornecedor"
        self.fields["obra"].empty_label = "Selecione a obra"
        self.fields["plano_financeiro"].empty_label = "Selecione a classificação"
        self.fields["obra"].required = True
        self.fields["vencimento"].required = True
        self.fields["beneficiario_nome"].required = False

        if not (titulo_integrado and titulo_integrado.integrada):
            self.fields["fornecedor"].required = True
            self.fields["beneficiario_nome"].widget = forms.HiddenInput()
            self.fields["beneficiario_documento"].widget = forms.HiddenInput()

        if self.instance and self.instance.pk:
            self.fields["quantidade_parcelas"].widget = forms.HiddenInput()
            self.fields["intervalo_dias"].widget = forms.HiddenInput()

        for field in self.fields.values():
            cls = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (cls + " fin-control").strip()

        if titulo_integrado and titulo_integrado.integrada:
            for campo in ("fornecedor", "beneficiario_nome", "beneficiario_documento", "valor_original"):
                self.fields[campo].disabled = True

    def clean_arquivo_documento(self):
        return validar_documento_upload(self.cleaned_data.get("arquivo_documento"))

    def clean(self):
        cleaned = super().clean()
        fornecedor = cleaned.get("fornecedor")
        beneficiario = (cleaned.get("beneficiario_nome") or "").strip()
        if not self.titulo_integrado or not self.titulo_integrado.integrada:
            if not fornecedor:
                raise ValidationError("Selecione um beneficiário / fornecedor cadastrado.")
        elif not fornecedor and not beneficiario:
            raise ValidationError("A conta integrada precisa possuir um beneficiário identificado na origem.")
        if fornecedor and not beneficiario:
            cleaned["beneficiario_nome"] = getattr(fornecedor, "nome_exibicao", None) or str(fornecedor)
        quantidade = cleaned.get("quantidade_parcelas") or 1
        if quantidade > 1 and not cleaned.get("intervalo_dias"):
            raise ValidationError("Informe o intervalo entre as parcelas.")
        return cleaned


class PrevisaoFinanceiraForm(ERPModelForm):
    class Meta:
        model = PrevisaoFinanceira
        fields = (
            "descricao",
            "obra",
            "fornecedor",
            "plano_financeiro",
            "data_prevista",
            "valor_previsto",
            "observacao",
        )
        widgets = {
            "data_prevista": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["obra"].required = True
        self.fields["data_prevista"].required = True
        for field in self.fields.values():
            cls = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (cls + " fin-control").strip()


class PagamentoForm(ERPModelForm):
    class Meta:
        model = Pagamento
        fields = (
            "data_pagamento",
            "forma",
            "referencia_bancaria",
            "comprovante",
            "observacao",
        )
        widgets = {
            "data_pagamento": forms.DateInput(attrs={"type": "date"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "referencia_bancaria": "Referência / autenticação",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            cls = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (cls + " fin-control").strip()

    def clean_comprovante(self):
        return validar_documento_upload(self.cleaned_data.get("comprovante"))
