from django import forms
from django.core.exceptions import ValidationError

from core.validators import validar_documento_upload
from cadastros.models import Material
from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from .cadastros import ERPModelForm


class TituloPagarForm(ERPModelForm):
    """Formulário enxuto para solicitação avulsa e manutenção de contas."""

    tipo_pagamento = forms.ChoiceField(
        choices=(("OUTRO", "Outro pagamento"), ("MATERIAL", "Materiais")),
        initial="OUTRO",
        label="Tipo do pagamento",
    )
    materiais = forms.ModelMultipleChoiceField(
        queryset=Material.objects.all(),
        required=False,
        label="Materiais",
        widget=forms.SelectMultiple(attrs={"size": "8"}),
    )
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
            "materiais",
            "descricao",
            "especificacao_pagamento",
            "documento_numero",
            "arquivo_documento",
            "data_emissao",
            "vencimento",
            "valor_original",
            "desconto",
            "juros",
            "multa",
            "outros_acrescimos",
            "observacao",
        )
        widgets = {
            "data_emissao": forms.DateInput(attrs={"type": "date"}),
            "vencimento": forms.DateInput(attrs={"type": "date"}),
            "especificacao_pagamento": forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva o serviço, taxa ou outro pagamento."}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "fornecedor": "Fornecedor cadastrado",
            "beneficiario_nome": "Beneficiário / favorecido",
            "beneficiario_documento": "CPF / CNPJ do beneficiário",
            "plano_financeiro": "Apropriação financeira",
            "descricao": "Descrição do pagamento",
            "especificacao_pagamento": "O que está sendo pago",
            "documento_numero": "Documento / NF",
            "arquivo_documento": "Anexo",
            "valor_original": "Valor bruto",
            "desconto": "Desconto",
            "juros": "Juros",
            "multa": "Multa",
            "outros_acrescimos": "Outros acréscimos",
        }

    def __init__(self, *args, titulo_integrado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.titulo_integrado = titulo_integrado
        self.fields["fornecedor"].empty_label = "Selecione o beneficiário / fornecedor"
        self.fields["obra"].empty_label = "Selecione a obra"
        self.fields["plano_financeiro"].empty_label = "Selecione a apropriação"
        self.fields["plano_financeiro"].queryset = (
            self.fields["plano_financeiro"].queryset.filter(ativo=True, pai__isnull=False)
            .select_related("pai").order_by("pai__codigo", "codigo", "nome")
        )
        self.fields["obra"].required = True
        self.fields["vencimento"].required = True
        self.fields["plano_financeiro"].required = True
        self.fields["descricao"].required = False
        self.fields["especificacao_pagamento"].required = False
        self.fields["beneficiario_nome"].required = False

        if self.instance and self.instance.pk and self.instance.materiais.exists():
            self.fields["tipo_pagamento"].initial = "MATERIAL"
        else:
            self.fields["tipo_pagamento"].initial = "OUTRO"

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
            # Dados estruturais vindos da origem não podem ser trocados no Financeiro.
            # Vencimento e apropriação permanecem editáveis para completar a solicitação.
            for campo in ("fornecedor", "beneficiario_nome", "beneficiario_documento", "valor_original"):
                self.fields[campo].disabled = True
            self.fields["tipo_pagamento"].widget = forms.HiddenInput()
            self.fields["materiais"].widget = forms.HiddenInput()

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

        if not self.titulo_integrado or not self.titulo_integrado.integrada:
            tipo = cleaned.get("tipo_pagamento") or "OUTRO"
            materiais = cleaned.get("materiais")
            if tipo == "MATERIAL":
                if not materiais:
                    self.add_error("materiais", "Selecione ao menos um material.")
                else:
                    nomes = [str(material).strip() for material in materiais]
                    cleaned["descricao"] = "MATERIAIS"
                    cleaned["especificacao_pagamento"] = "\n".join(nomes)
            else:
                descricao = (cleaned.get("descricao") or "").strip()
                especificacao = (cleaned.get("especificacao_pagamento") or "").strip()
                if not descricao:
                    self.add_error("descricao", "Informe a descrição do pagamento.")
                else:
                    cleaned["descricao"] = descricao.upper()
                if not especificacao:
                    self.add_error("especificacao_pagamento", "Informe o que está sendo pago.")
                cleaned["materiais"] = Material.objects.none()

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
            "especificacao_pagamento": forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva o serviço, taxa ou outro pagamento."}),
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
            "especificacao_pagamento": forms.Textarea(attrs={"rows": 3, "placeholder": "Descreva o serviço, taxa ou outro pagamento."}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "referencia_bancaria": "Referência / autenticação",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comprovante"].required = True
        for field in self.fields.values():
            cls = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (cls + " fin-control").strip()

    def clean_comprovante(self):
        return validar_documento_upload(self.cleaned_data.get("comprovante"))
