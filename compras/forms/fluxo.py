from collections import defaultdict
from decimal import Decimal

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
from compras.services.comercial import queryset_itens_tecnicamente_aprovados


INPUT_CLASS = "cp-input"


PRAZOS_ENTREGA_CHOICES = [
    ("", "Selecione o prazo"),
    (5, "5 dias"),
    (10, "10 dias"),
    (15, "15 dias"),
    (20, "20 dias"),
    (25, "25 dias"),
    (30, "30 dias"),
    (45, "45 dias"),
    (60, "60 dias"),
    (90, "90 dias"),
]

CONDICOES_PAGAMENTO_CHOICES = [
    ("", "Selecione a condição"),
    ("À vista", "À vista"),
    ("7 dias", "7 dias"),
    ("14 dias", "14 dias"),
    ("21 dias", "21 dias"),
    ("28 dias", "28 dias"),
    ("30 dias", "30 dias"),
    ("30/60 dias", "30/60 dias"),
    ("30/60/90 dias", "30/60/90 dias"),
    ("45 dias", "45 dias"),
    ("60 dias", "60 dias"),
    ("90 dias", "90 dias"),
    ("A combinar", "A combinar"),
]


def _numero_para_input(valor):
    """Formata Decimal sem zeros decimais desnecessários para inputs HTML."""
    if valor in (None, ""):
        return None
    texto = format(Decimal(str(valor)), "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


def _choices_com_valor_atual(choices, valor, sufixo=""):
    """Preserva dados legados que não façam parte das opções padronizadas."""
    resultado = list(choices)
    if valor in (None, ""):
        return resultado
    chaves = {str(v) for v, _ in resultado}
    chave = str(valor)
    if chave not in chaves:
        rotulo = f"{chave}{sufixo}" if sufixo else chave
        resultado.append((valor, rotulo))
    return resultado


def _aplicar_classe_campos(form):
    for field in form.fields.values():
        classes = field.widget.attrs.get("class", "").split()
        if INPUT_CLASS not in classes:
            classes.append(INPUT_CLASS)
        field.widget.attrs["class"] = " ".join(filter(None, classes))


class NecessidadeCompraForm(forms.Form):
    """Inclusão eventual de item durante a etapa de cotação."""

    descricao = forms.CharField(max_length=500, label="Item")
    especificacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    unidade = forms.ChoiceField(choices=NecessidadeCompra.UnidadeMedida.choices)
    quantidade = forms.DecimalField(min_value=0.0001, decimal_places=4, max_digits=18)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.processo = processo
        _aplicar_classe_campos(self)


class FornecedorCompraForm(forms.ModelForm):
    class Meta:
        model = FornecedorCompra
        fields = ["nome", "documento", "email", "telefone"]
        widgets = {f: forms.TextInput(attrs={"class": INPUT_CLASS}) for f in fields}


class CotacaoFornecedorForm(forms.Form):
    fornecedor = forms.ModelChoiceField(
        queryset=FornecedorCompra.objects.filter(ativo=True).order_by("nome")
    )
    data_proposta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    prazo_entrega_dias = forms.TypedChoiceField(
        required=False,
        choices=PRAZOS_ENTREGA_CHOICES,
        coerce=int,
        empty_value=None,
        label="Prazo de entrega",
    )
    condicao_pagamento = forms.ChoiceField(
        required=False,
        choices=CONDICOES_PAGAMENTO_CHOICES,
        label="Condição de pagamento",
    )
    frete = forms.DecimalField(required=False, min_value=0, decimal_places=2, initial=0)
    validade = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    documento = forms.FileField(required=False)

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["fornecedor"].queryset = self.fields["fornecedor"].queryset.exclude(
                cotacoes__processo=processo
            )
        _aplicar_classe_campos(self)


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
        self.fields["cotacao"].queryset = (
            CotacaoFornecedor.objects.filter(processo=processo).select_related("fornecedor")
            if processo
            else CotacaoFornecedor.objects.none()
        )
        self.fields["necessidade"].queryset = (
            NecessidadeCompra.objects.filter(processo=processo, situacao="ATIVA")
            if processo
            else NecessidadeCompra.objects.none()
        )
        _aplicar_classe_campos(self)


class PropostaCompletaForm(forms.Form):
    """
    Formulário orientado à tarefa do comprador: cabeçalho da proposta +
    todos os itens da necessidade em uma única submissão.

    Não cria regra comercial nova. A view usa os dados limpos deste form e
    delega a persistência aos services incluir_cotacao/incluir_item_cotacao.
    """

    fornecedor = forms.ModelChoiceField(
        queryset=FornecedorCompra.objects.none(),
        label="Fornecedor",
    )
    data_proposta = forms.DateField(
        required=False,
        label="Data da proposta",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    prazo_entrega_dias = forms.TypedChoiceField(
        required=False,
        choices=PRAZOS_ENTREGA_CHOICES,
        coerce=int,
        empty_value=None,
        label="Prazo de entrega",
    )
    condicao_pagamento = forms.ChoiceField(
        required=False,
        choices=CONDICOES_PAGAMENTO_CHOICES,
        label="Condição de pagamento",
    )
    frete = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        initial=0,
        label="Frete",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    validade = forms.DateField(
        required=False,
        label="Validade",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    documento = forms.FileField(required=False, label="Proposta / anexo")
    observacoes = forms.CharField(
        required=False,
        label="Observações comerciais",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Informações gerais da proposta"}),
    )

    def __init__(self, *args, processo, cotacao=None, **kwargs):
        self.processo = processo
        self.cotacao = cotacao
        super().__init__(*args, **kwargs)

        fornecedores = FornecedorCompra.objects.filter(ativo=True).order_by("nome")
        if cotacao:
            fornecedores = FornecedorCompra.objects.filter(pk=cotacao.fornecedor_id)
            self.fields["fornecedor"].initial = cotacao.fornecedor
            self.fields["fornecedor"].disabled = True
            self.fields["prazo_entrega_dias"].choices = _choices_com_valor_atual(
                PRAZOS_ENTREGA_CHOICES, cotacao.prazo_entrega_dias, " dias"
            )
            self.fields["condicao_pagamento"].choices = _choices_com_valor_atual(
                CONDICOES_PAGAMENTO_CHOICES, cotacao.condicao_pagamento
            )
            self.initial.update(
                {
                    "data_proposta": cotacao.data_proposta,
                    "prazo_entrega_dias": cotacao.prazo_entrega_dias,
                    "condicao_pagamento": cotacao.condicao_pagamento,
                    "frete": _numero_para_input(cotacao.frete),
                    "validade": cotacao.validade,
                    "observacoes": cotacao.observacoes,
                }
            )
        else:
            usados = processo.cotacoes.values_list("fornecedor_id", flat=True)
            fornecedores = fornecedores.exclude(pk__in=usados)

        self.fields["fornecedor"].queryset = fornecedores

        itens_existentes = {}
        if cotacao:
            itens_existentes = {
                item.necessidade_id: item
                for item in cotacao.itens.select_related("necessidade").all()
            }

        self.linhas = []
        necessidades = list(
            processo.necessidades.filter(situacao="ATIVA").order_by("descricao", "id")
        )
        for necessidade in necessidades:
            item = itens_existentes.get(necessidade.pk)
            sufixo = str(necessidade.pk)

            self.fields[f"quantidade_{sufixo}"] = forms.DecimalField(
                required=False,
                min_value=Decimal("0.0001"),
                max_digits=18,
                decimal_places=4,
                label="Quantidade",
                initial=_numero_para_input(item.quantidade if item else necessidade.quantidade_incluida),
                widget=forms.NumberInput(
                    attrs={
                        "step": "0.0001",
                        "min": "0.0001",
                        "max": _numero_para_input(necessidade.quantidade_incluida),
                        "data-proposta-quantidade": "1",
                    }
                ),
            )
            self.fields[f"valor_{sufixo}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=18,
                decimal_places=4,
                label="Preço unitário",
                initial=_numero_para_input(item.valor_unitario_cotado) if item else None,
                widget=forms.NumberInput(
                    attrs={"step": "0.0001", "min": "0", "data-proposta-valor": "1"}
                ),
            )
            self.fields[f"marca_{sufixo}"] = forms.CharField(
                required=False,
                max_length=120,
                label="Marca",
                initial=item.marca if item else "",
            )
            self.fields[f"modelo_{sufixo}"] = forms.CharField(
                required=False,
                max_length=120,
                label="Modelo",
                initial=item.modelo if item else "",
            )
            self.fields[f"desconto_{sufixo}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=18,
                decimal_places=2,
                initial=_numero_para_input(item.desconto_cotado if item else Decimal("0")),
                label="Desconto total do item",
                widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "data-proposta-desconto": "1"}),
            )
            self.fields[f"descricao_{sufixo}"] = forms.CharField(
                required=False,
                max_length=500,
                label="Descrição comercial",
                initial=item.descricao_comercial if item else "",
            )
            self.fields[f"especificacao_{sufixo}"] = forms.CharField(
                required=False,
                label="Especificação ofertada",
                initial=item.especificacao_ofertada if item else "",
                widget=forms.Textarea(attrs={"rows": 2}),
            )
            self.fields[f"observacoes_item_{sufixo}"] = forms.CharField(
                required=False,
                label="Observações do item",
                initial=item.observacoes if item else "",
                widget=forms.Textarea(attrs={"rows": 2}),
            )

        _aplicar_classe_campos(self)

        for necessidade in necessidades:
            sufixo = str(necessidade.pk)
            self.linhas.append(
                {
                    "necessidade": necessidade,
                    "item_existente": itens_existentes.get(necessidade.pk),
                    "quantidade": self[f"quantidade_{sufixo}"],
                    "valor": self[f"valor_{sufixo}"],
                    "marca": self[f"marca_{sufixo}"],
                    "modelo": self[f"modelo_{sufixo}"],
                    "desconto": self[f"desconto_{sufixo}"],
                    "descricao": self[f"descricao_{sufixo}"],
                    "especificacao": self[f"especificacao_{sufixo}"],
                    "observacoes": self[f"observacoes_item_{sufixo}"],
                }
            )

    def clean(self):
        cleaned = super().clean()
        if not self.processo.necessidades.filter(situacao="ATIVA").exists():
            raise forms.ValidationError("Inclua ao menos um item na compra antes de registrar propostas.")

        for linha in self.linhas:
            necessidade = linha["necessidade"]
            sufixo = str(necessidade.pk)
            valor = cleaned.get(f"valor_{sufixo}")
            quantidade = cleaned.get(f"quantidade_{sufixo}")
            item_existente = linha["item_existente"]

            if valor is None:
                # Em edição, limpar preço não remove silenciosamente a oferta existente.
                # Ela permanece intacta; para alterar, informe o novo valor.
                continue
            if quantidade is None:
                self.add_error(f"quantidade_{sufixo}", "Informe a quantidade cotada.")
                continue
            if quantidade > necessidade.quantidade_incluida:
                self.add_error(
                    f"quantidade_{sufixo}",
                    f"Máximo: {necessidade.quantidade_incluida} {necessidade.unidade}.",
                )
            if item_existente is None and valor is None:
                continue
        return cleaned

    def itens_para_salvar(self):
        for linha in self.linhas:
            necessidade = linha["necessidade"]
            sufixo = str(necessidade.pk)
            valor = self.cleaned_data.get(f"valor_{sufixo}")
            if valor is None:
                continue
            yield {
                "necessidade": necessidade,
                "quantidade": self.cleaned_data[f"quantidade_{sufixo}"],
                "valor_unitario": valor,
                "descricao_comercial": self.cleaned_data.get(f"descricao_{sufixo}", ""),
                "marca": self.cleaned_data.get(f"marca_{sufixo}", ""),
                "modelo": self.cleaned_data.get(f"modelo_{sufixo}", ""),
                "especificacao_ofertada": self.cleaned_data.get(f"especificacao_{sufixo}", ""),
                "desconto_cotado": self.cleaned_data.get(f"desconto_{sufixo}") or Decimal("0"),
                "observacoes": self.cleaned_data.get(f"observacoes_item_{sufixo}", ""),
            }


class CompatibilizacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    resultado = forms.ChoiceField(choices=CompatibilizacaoItem.Resultado.choices)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    ressalva_motivo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = CotacaoFornecedorItem.objects.filter(
                cotacao__processo=processo
            ).select_related("cotacao__fornecedor", "necessidade")
        _aplicar_classe_campos(self)


class AnaliseTecnicaLoteForm(forms.Form):
    """Decisões técnicas inline, agrupadas por necessidade."""

    def __init__(self, *args, processo, **kwargs):
        self.processo = processo
        super().__init__(*args, **kwargs)
        itens = list(
            CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            .select_related("cotacao__fornecedor", "necessidade")
            .prefetch_related("compatibilizacoes")
            .order_by("necessidade__descricao", "cotacao__fornecedor__nome")
        )
        grupos = defaultdict(list)
        self.linhas = []
        for item in itens:
            atual = item.compatibilizacoes.first()
            sid = str(item.pk)
            self.fields[f"resultado_{sid}"] = forms.ChoiceField(
                required=False,
                choices=[("", "Pendente"), *CompatibilizacaoItem.Resultado.choices],
                label="Análise",
                initial=atual.resultado if atual else "",
            )
            self.fields[f"observacao_{sid}"] = forms.CharField(
                required=False,
                label="Observação",
                initial=atual.observacao if atual else "",
                widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Observação opcional"}),
            )
            self.fields[f"ressalva_{sid}"] = forms.CharField(
                required=False,
                label="Motivo da ressalva",
                initial=atual.ressalva_motivo if atual else "",
                widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Obrigatório para aprovação com ressalva"}),
            )
        _aplicar_classe_campos(self)

        for item in itens:
            sid = str(item.pk)
            atual = item.compatibilizacoes.first()
            linha = {
                "item": item,
                "atual": atual,
                "resultado": self[f"resultado_{sid}"],
                "observacao": self[f"observacao_{sid}"],
                "ressalva": self[f"ressalva_{sid}"],
            }
            self.linhas.append(linha)
            grupos[item.necessidade].append(linha)
        self.grupos = [{"necessidade": n, "linhas": linhas} for n, linhas in grupos.items()]

    def clean(self):
        cleaned = super().clean()
        for linha in self.linhas:
            item = linha["item"]
            sid = str(item.pk)
            resultado = cleaned.get(f"resultado_{sid}")
            ressalva = (cleaned.get(f"ressalva_{sid}") or "").strip()
            if resultado == CompatibilizacaoItem.Resultado.APROVADO_COM_RESSALVA and not ressalva:
                self.add_error(f"ressalva_{sid}", "Informe o motivo da ressalva.")
        return cleaned

    def decisoes(self):
        for linha in self.linhas:
            item = linha["item"]
            sid = str(item.pk)
            resultado = self.cleaned_data.get(f"resultado_{sid}")
            if not resultado:
                continue
            yield {
                "item": item,
                "resultado": resultado,
                "observacao": self.cleaned_data.get(f"observacao_{sid}", ""),
                "ressalva_motivo": self.cleaned_data.get(f"ressalva_{sid}", ""),
            }


class NegociacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    valor_unitario_negociado = forms.DecimalField(required=False, min_value=0, decimal_places=4)
    frete_negociado = forms.DecimalField(required=False, min_value=0, decimal_places=2)
    prazo_entrega_dias_negociado = forms.TypedChoiceField(
        required=False, choices=PRAZOS_ENTREGA_CHOICES, coerce=int, empty_value=None
    )
    condicao_pagamento_negociada = forms.ChoiceField(
        required=False, choices=CONDICOES_PAGAMENTO_CHOICES
    )
    observacoes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = queryset_itens_tecnicamente_aprovados(
                CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            ).select_related("cotacao__fornecedor", "necessidade")
        _aplicar_classe_campos(self)


class AdjudicacaoForm(forms.Form):
    item_cotado = forms.ModelChoiceField(queryset=CotacaoFornecedorItem.objects.none())
    quantidade = forms.DecimalField(min_value=0.0001, decimal_places=4)

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            self.fields["item_cotado"].queryset = queryset_itens_tecnicamente_aprovados(
                CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            ).select_related("cotacao__fornecedor", "necessidade")
        _aplicar_classe_campos(self)


class DecisaoComercialLoteForm(forms.Form):
    """
    Une na mesma superfície de trabalho a condição negociada e a quantidade
    escolhida por fornecedor. A view continua usando registrar_negociacao e
    adjudicar/cancelar_adjudicacao para persistir.
    """

    def __init__(self, *args, processo, **kwargs):
        self.processo = processo
        super().__init__(*args, **kwargs)
        itens = list(
            queryset_itens_tecnicamente_aprovados(
                CotacaoFornecedorItem.objects.filter(cotacao__processo=processo)
            )
            .select_related("cotacao__fornecedor", "necessidade")
            .order_by("necessidade__descricao", "cotacao__fornecedor__nome")
        )
        ativos = list(
            processo.adjudicacoes.filter(cancelada=False).select_related("item_cotado")
        )
        quantidade_por_item = defaultdict(lambda: Decimal("0"))
        for adj in ativos:
            quantidade_por_item[adj.item_cotado_id] += adj.quantidade

        grupos = defaultdict(list)
        self.linhas = []
        for item in itens:
            sid = str(item.pk)
            try:
                negociacao = item.negociacao
            except Exception:
                negociacao = None

            self.fields[f"valor_{sid}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=18,
                decimal_places=4,
                label="Preço negociado",
                initial=_numero_para_input(negociacao.valor_unitario_negociado) if negociacao else None,
                widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0", "data-decisao-valor": "1"}),
            )
            self.fields[f"quantidade_{sid}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=18,
                decimal_places=4,
                label="Comprar",
                initial=_numero_para_input(quantidade_por_item[item.pk]),
                widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0", "data-decisao-quantidade": "1"}),
            )
            self.fields[f"frete_{sid}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=18,
                decimal_places=2,
                label="Frete negociado",
                initial=_numero_para_input(negociacao.frete_negociado) if negociacao else None,
                widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            )
            prazo_atual = negociacao.prazo_entrega_dias_negociado if negociacao else item.cotacao.prazo_entrega_dias
            pagamento_atual = (
                negociacao.condicao_pagamento_negociada
                if negociacao and negociacao.condicao_pagamento_negociada
                else item.cotacao.condicao_pagamento
            )
            self.fields[f"prazo_{sid}"] = forms.TypedChoiceField(
                required=False,
                choices=_choices_com_valor_atual(PRAZOS_ENTREGA_CHOICES, prazo_atual, " dias"),
                coerce=int,
                empty_value=None,
                label="Prazo negociado",
                initial=prazo_atual,
            )
            self.fields[f"pagamento_{sid}"] = forms.ChoiceField(
                required=False,
                choices=_choices_com_valor_atual(CONDICOES_PAGAMENTO_CHOICES, pagamento_atual),
                label="Pagamento negociado",
                initial=pagamento_atual,
            )
            self.fields[f"observacoes_{sid}"] = forms.CharField(
                required=False,
                label="Observações",
                initial=(negociacao.observacoes if negociacao else ""),
                widget=forms.Textarea(attrs={"rows": 2}),
            )

        _aplicar_classe_campos(self)

        for item in itens:
            sid = str(item.pk)
            try:
                negociacao = item.negociacao
            except Exception:
                negociacao = None
            linha = {
                "item": item,
                "negociacao": negociacao,
                "quantidade_atual": quantidade_por_item[item.pk],
                "quantidade_ofertada": item.quantidade,
                "valor_original": item.valor_unitario_cotado,
                "valor": self[f"valor_{sid}"],
                "quantidade": self[f"quantidade_{sid}"],
                "frete": self[f"frete_{sid}"],
                "prazo": self[f"prazo_{sid}"],
                "pagamento": self[f"pagamento_{sid}"],
                "observacoes": self[f"observacoes_{sid}"],
            }
            self.linhas.append(linha)
            grupos[item.necessidade].append(linha)
        self.grupos = []
        for necessidade, linhas in grupos.items():
            menor_preco = min((linha["item"].valor_unitario_cotado for linha in linhas), default=None)
            for linha in linhas:
                linha["menor_preco"] = (
                    menor_preco is not None and linha["item"].valor_unitario_cotado == menor_preco
                )
            self.grupos.append({
                "necessidade": necessidade,
                "linhas": linhas,
                "menor_preco": menor_preco,
            })

    def clean(self):
        cleaned = super().clean()
        totais = defaultdict(lambda: Decimal("0"))
        for linha in self.linhas:
            item = linha["item"]
            quantidade = cleaned.get(f"quantidade_{item.pk}") or Decimal("0")
            totais[item.necessidade_id] += quantidade

        necessidades = {n.pk: n for n in self.processo.necessidades.filter(situacao="ATIVA")}
        for necessidade_id, total in totais.items():
            necessidade = necessidades.get(necessidade_id)
            if necessidade and total > necessidade.quantidade_incluida:
                raise forms.ValidationError(
                    f"{necessidade.descricao}: selecionado {total} {necessidade.unidade}, "
                    f"mas o máximo é {necessidade.quantidade_incluida} {necessidade.unidade}."
                )
        return cleaned

    def dados_linhas(self):
        for linha in self.linhas:
            item = linha["item"]
            sid = str(item.pk)
            yield {
                "item": item,
                "valor_unitario_negociado": self.cleaned_data.get(f"valor_{sid}"),
                "quantidade": self.cleaned_data.get(f"quantidade_{sid}") or Decimal("0"),
                "frete_negociado": self.cleaned_data.get(f"frete_{sid}"),
                "prazo_entrega_dias_negociado": self.cleaned_data.get(f"prazo_{sid}"),
                "condicao_pagamento_negociada": self.cleaned_data.get(f"pagamento_{sid}", ""),
                "observacoes": self.cleaned_data.get(f"observacoes_{sid}", ""),
            }


class AprovacaoForm(forms.Form):
    decisao = forms.ChoiceField(choices=AprovacaoCompra.Decisao.choices)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _aplicar_classe_campos(self)


class DocumentoContratacaoForm(forms.Form):
    fornecedor = forms.ModelChoiceField(
        queryset=FornecedorCompra.objects.none(),
        label="Fornecedor",
    )
    documento = forms.FileField(
        required=True,
        label="Documento anexo",
        help_text="Anexe contrato, pedido assinado ou outro documento complementar relacionado ao fornecedor.",
    )

    def __init__(self, *args, processo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if processo:
            fornecedor_ids = processo.adjudicacoes.filter(cancelada=False).values_list(
                "cotacao__fornecedor_id", flat=True
            )
            self.fields["fornecedor"].queryset = (
                FornecedorCompra.objects.filter(id__in=fornecedor_ids)
                .distinct()
                .order_by("nome")
            )
        _aplicar_classe_campos(self)
