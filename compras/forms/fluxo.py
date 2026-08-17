from django import forms

from compras.models import (
    AdjudicacaoCompra,
    AprovacaoCompra,
    CompatibilizacaoItem,
    ContratacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    FornecedorCompra,
    NecessidadeCompra,
)
from planejamento.models import AtividadePlanejamento
from compras.services.comercial import queryset_itens_tecnicamente_aprovados


class NecessidadeCompraForm(forms.Form):
    """
    Inclusão de item durante a etapa de cotação.

    As atividades já estão vinculadas ao processo; por isso não são
    solicitadas novamente em cada necessidade.
    """

    descricao = forms.CharField(max_length=500, label="Item")
    especificacao = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    unidade = forms.ChoiceField(choices=NecessidadeCompra.UnidadeMedida.choices)
    quantidade = forms.DecimalField(
        min_value=0.0001,
        decimal_places=4,
        max_digits=18,
    )
    observacao = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.processo = processo
        for field in self.fields.values():
            field.widget.attrs["class"] = "cp-input"


class FornecedorCompraForm(forms.ModelForm):
    class Meta:
        model = FornecedorCompra
        fields = ["nome", "documento", "email", "telefone"]
        widgets = {f: forms.TextInput(attrs={"class": "cp-input"}) for f in fields}


class CotacaoFornecedorForm(forms.Form):
    fornecedor = forms.ModelChoiceField(queryset=FornecedorCompra.objects.filter(ativo=True).order_by("nome"))
    data_proposta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    prazo_entrega_dias = forms.IntegerField(required=False, min_value=0)
    condicao_pagamento = forms.CharField(required=False, max_length=255)
    frete = forms.DecimalField(required=False, min_value=0, decimal_places=2, initial=0)
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    documento = forms.FileField(required=False)

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["fornecedor"].queryset = self.fields["fornecedor"].queryset.exclude(cotacoes__processo=processo)
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class CotacaoItemForm(forms.Form):
    cotacao = forms.ModelChoiceField(queryset=CotacaoFornecedor.objects.none())
    necessidade = forms.ModelChoiceField(queryset=NecessidadeCompra.objects.none())
    descricao_comercial = forms.CharField(required=False, max_length=500)
    marca = forms.CharField(required=False, max_length=120)
    modelo = forms.CharField(required=False, max_length=120)
    especificacao_ofertada = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    quantidade = forms.DecimalField(min_value=0.0001, decimal_places=4, max_digits=18)
    valor_unitario_cotado = forms.DecimalField(min_value=0, decimal_places=4, max_digits=18)
    desconto_cotado = forms.DecimalField(required=False, min_value=0, decimal_places=2, initial=0)
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cotacao"].queryset = CotacaoFornecedor.objects.filter(processo=processo).select_related("fornecedor") if processo else CotacaoFornecedor.objects.none()
        self.fields["necessidade"].queryset = NecessidadeCompra.objects.filter(processo=processo, situacao="ATIVA") if processo else NecessidadeCompra.objects.none()
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class CompatibilizacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    resultado = forms.ChoiceField(choices=CompatibilizacaoItem.Resultado.choices)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    ressalva_motivo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = CotacaoFornecedorItem.objects.filter(cotacao__processo=processo).select_related("cotacao__fornecedor", "necessidade")
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class NegociacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    valor_unitario_negociado = forms.DecimalField(required=False, min_value=0, decimal_places=4)
    frete_negociado = forms.DecimalField(required=False, min_value=0, decimal_places=2)
    prazo_entrega_dias_negociado = forms.IntegerField(required=False, min_value=0)
    condicao_pagamento_negociada = forms.CharField(required=False, max_length=255)
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = queryset_itens_tecnicamente_aprovados(
                CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            ).select_related("cotacao__fornecedor", "necessidade")
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class AdjudicacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    quantidade = forms.DecimalField(min_value=0.0001, decimal_places=4)

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = queryset_itens_tecnicamente_aprovados(
                CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            ).select_related("cotacao__fornecedor", "necessidade")
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class AprovacaoForm(forms.Form):
    decisao = forms.ChoiceField(choices=AprovacaoCompra.Decisao.choices)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"


class ContratacaoForm(forms.Form):
    fornecedor = forms.ModelChoiceField(queryset=FornecedorCompra.objects.none())
    tipo_formalizacao = forms.ChoiceField(choices=ContratacaoCompra.TipoFormalizacao.choices)
    condicao_pagamento = forms.CharField(required=False, max_length=255)
    prazo_entrega_dias = forms.IntegerField(required=False, min_value=0)
    previsao_entrega = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    local_entrega = forms.CharField(required=False, max_length=500)
    referencia_contrato = forms.CharField(required=False, max_length=120)
    documento = forms.FileField(required=False)
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            fornecedor_ids = processo.adjudicacoes.filter(cancelada=False).values_list("cotacao__fornecedor_id", flat=True)
            existentes = processo.contratacoes.filter(cancelada=False).values_list("fornecedor_id", flat=True)
            self.fields["fornecedor"].queryset = FornecedorCompra.objects.filter(id__in=fornecedor_ids).exclude(id__in=existentes).distinct().order_by("nome")
        for f in self.fields.values():
            f.widget.attrs["class"] = "cp-input"
