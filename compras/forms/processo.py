from django import forms
from django.forms import formset_factory

from compras.models import NecessidadeCompra, ProcessoCompra
from cadastros.models import Material
from compras.services.processos import permite_compra_sem_atividade
from financeiro.models import PlanoFinanceiro
from planejamento.models import (
    AtividadePlanejamento,
    ImportacaoCronograma,
    ItemCronogramaSuprimento,
    RegistroCronograma,
)


def _rotulo_usuario(usuario):
    """Exibe somente o nome da pessoa nos campos de seleção de usuário."""
    nome = (usuario.get_full_name() or "").strip()
    return nome or "Nome não cadastrado"


# ============================================================
# NOMES ESTRUTURAIS DO CRONOGRAMA
# ============================================================

NOMES_ESTRUTURAIS = {
    "TÉRREO",
    "TERREO",
    "SUPERIOR",
    "SUBSOLO",
    "GARAGEM",
    "COBERTURA",
    "RESUMO",
    "RESUMO GERAL",
    "MARCOS",
}


# ============================================================
# IMPORTAÇÃO ATIVA
# ============================================================


def obter_importacao_ativa():
    """
    Retorna a importação de cronograma atualmente ativa.
    """

    return (
        ImportacaoCronograma.objects
        .filter(
            ativa=True,
            status=ImportacaoCronograma.Status.CONCLUIDA,
        )
        .order_by("-id")
        .first()
    )


# ============================================================
# ATIVIDADES DISPONÍVEIS PARA COMPRAS
# ============================================================


def obter_atividades_e_datas(*, obra_id=None):
    """
    Retorna:
        (
            queryset de AtividadePlanejamento,
            mapa de datas por atividade
        )

    Somente atividades:
    - presentes na importação ativa;
    - ativas;
    - da obra selecionada;
    - com disciplina;
    - não estruturais.
    """

    importacao = obter_importacao_ativa()

    if importacao is None:
        return (
            AtividadePlanejamento.objects.none(),
            {},
        )

    registros = (
        RegistroCronograma.objects
        .filter(
            importacao=importacao,
            atividade_planejamento__isnull=False,
        )
    )

    if obra_id:
        registros = registros.filter(
            obra_id=obra_id
        )

    atividade_ids = (
        registros
        .values_list(
            "atividade_planejamento_id",
            flat=True,
        )
        .distinct()
    )

    atividades = (
        AtividadePlanejamento.objects
        .filter(
            id__in=atividade_ids,
            ativa=True,
        )
        .exclude(
            disciplina__exact=""
        )
        .exclude(
            nome_tarefa__in=NOMES_ESTRUTURAIS
        )
        .select_related(
            "obra"
        )
        .order_by(
            "disciplina",
            "local_tarefa",
            "nome_tarefa",
            "id",
        )
    )

    ids_atividades_validas = set(
        atividades.values_list(
            "id",
            flat=True,
        )
    )

    if not ids_atividades_validas:
        return (
            atividades,
            {},
        )

    registros_datas = (
        registros
        .filter(
            atividade_planejamento_id__in=(
                ids_atividades_validas
            )
        )
        .values(
            "atividade_planejamento_id",
            "inicio_base",
            "termino_base",
            "inicio_real",
            "termino_real",
        )
        .order_by(
            "atividade_planejamento_id",
            "semana",
            "id",
        )
    )

    dados_por_atividade = {}

    for registro in registros_datas:

        atividade_id = registro[
            "atividade_planejamento_id"
        ]

        if atividade_id in dados_por_atividade:
            continue

        dados_por_atividade[
            atividade_id
        ] = {
            "inicio_base": registro[
                "inicio_base"
            ],
            "termino_base": registro[
                "termino_base"
            ],
            "inicio_planejado": registro[
                "inicio_real"
            ],
            "termino_planejado": registro[
                "termino_real"
            ],
        }

    return (
        atividades,
        dados_por_atividade,
    )


# ============================================================
# LABEL COMPARTILHADO DAS ATIVIDADES
# ============================================================


class AtividadePlanejamentoLabelMixin:
    """
    Gera o mesmo label detalhado tanto para seleção múltipla
    quanto para seleção de uma atividade no item.
    """

    def __init__(
        self,
        *args,
        dados_por_atividade=None,
        **kwargs,
    ):
        self.dados_por_atividade = (
            dados_por_atividade
            or {}
        )

        super().__init__(
            *args,
            **kwargs,
        )

    @staticmethod
    def _formatar_data(valor):

        if not valor:
            return "—"

        try:
            return valor.strftime(
                "%d/%m/%Y"
            )
        except (
            AttributeError,
            TypeError,
            ValueError,
        ):
            return str(valor)

    @staticmethod
    def _normalizar_texto(valor):

        return (
            str(valor or "")
            .strip()
            .casefold()
        )

    def label_from_instance(
        self,
        obj,
    ):

        dados = (
            self.dados_por_atividade
            .get(
                obj.pk,
                {},
            )
        )

        inicio_base = dados.get(
            "inicio_base"
        )

        termino_base = dados.get(
            "termino_base"
        )

        inicio_planejado = dados.get(
            "inicio_planejado"
        )

        termino_planejado = dados.get(
            "termino_planejado"
        )

        nome = (
            str(
                obj.nome_tarefa
                or "Atividade"
            )
            .strip()
        )

        nome_normalizado = (
            self._normalizar_texto(
                nome
            )
        )

        contexto = []

        disciplina = (
            str(
                obj.disciplina
                or ""
            )
            .strip()
        )

        local = (
            str(
                obj.local_tarefa
                or ""
            )
            .strip()
        )

        disciplina_normalizada = (
            self._normalizar_texto(
                disciplina
            )
        )

        local_normalizado = (
            self._normalizar_texto(
                local
            )
        )

        if (
            disciplina
            and disciplina_normalizada
            != nome_normalizado
        ):
            contexto.append(
                disciplina
            )

        contexto_normalizado = {
            self._normalizar_texto(
                parte
            )
            for parte in contexto
        }

        if (
            local
            and local_normalizado
            != nome_normalizado
            and local_normalizado
            not in contexto_normalizado
        ):
            contexto.append(
                local
            )

        contexto_texto = (
            " • ".join(
                contexto
            )
        )

        base_texto = (
            "Base: "
            f"{self._formatar_data(inicio_base)}"
            " → "
            f"{self._formatar_data(termino_base)}"
        )

        planejado_texto = (
            "Planejada: "
            f"{self._formatar_data(inicio_planejado)}"
            " → "
            f"{self._formatar_data(termino_planejado)}"
        )

        partes = [
            nome,
        ]

        if contexto_texto:
            partes.append(
                contexto_texto
            )

        partes.append(
            base_texto
        )

        partes.append(
            planejado_texto
        )

        return " | ".join(
            partes
        )


# ============================================================
# CAMPO PARA UMA ATIVIDADE
# ============================================================


class AtividadePlanejamentoChoiceField(
    AtividadePlanejamentoLabelMixin,
    forms.ModelChoiceField,
):
    """
    Usado em cada item da compra.
    Permite uma única atividade.
    """

    pass


# ============================================================
# CAMPO PARA VÁRIAS ATIVIDADES
# ============================================================


class AtividadePlanejamentoMultipleChoiceField(
    AtividadePlanejamentoLabelMixin,
    forms.ModelMultipleChoiceField,
):
    """
    Usado na etapa 1 da compra.
    Permite selecionar várias atividades.
    """

    pass


# ============================================================
# PROCESSO DE COMPRA
# ============================================================


class ApropriacaoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.pai_id:
            return f"{obj.pai.nome} → {obj.nome}"
        return obj.nome


class ProcessoCompraForm(forms.ModelForm):
    apropriacao = ApropriacaoChoiceField(
        queryset=PlanoFinanceiro.objects.none(),
        required=True,
        label="Apropriação financeira",
        empty_label="Selecione a apropriação",
        widget=forms.Select(attrs={"class": "cp-input"}),
        help_text="A classe financeira é herdada da apropriação selecionada.",
    )

    class Meta:
        model = ProcessoCompra
        fields = [
            "item_cronograma",
            "titulo",
            "apropriacao",
            "descricao",
            "comprador",
            "observacao",
        ]
        widgets = {
            "item_cronograma": forms.HiddenInput(),
            "titulo": forms.HiddenInput(),
            "descricao": forms.Textarea(attrs={"class": "cp-input", "rows": 2, "placeholder": "Descrição geral da compra"}),
            "comprador": forms.Select(attrs={"class": "cp-input"}),
            "observacao": forms.Textarea(attrs={"class": "cp-input", "rows": 2, "placeholder": "Observações adicionais"}),
        }

    def __init__(self, *args, item_inicial=None, **kwargs):
        super().__init__(*args, **kwargs)
        comprador_field = self.fields.get("comprador")
        if comprador_field is not None:
            comprador_field.queryset = comprador_field.queryset.filter(is_active=True).order_by("first_name", "last_name")
            comprador_field.label_from_instance = _rotulo_usuario

        self.fields["item_cronograma"].queryset = (
            ItemCronogramaSuprimento.objects.select_related("cronograma_obra__obra")
            .order_by("cronograma_obra__obra__nome", "ordem", "item")
        )
        self.fields["apropriacao"].queryset = (
            PlanoFinanceiro.objects.filter(ativo=True, tipo=PlanoFinanceiro.Tipo.DESPESA, pai__isnull=False)
            .select_related("pai")
            .order_by("pai__codigo", "codigo", "nome")
        )

        item = item_inicial
        if self.is_bound:
            item_id = self.data.get("item_cronograma") or self.data.get("item_origem")
            if item_id:
                item = (ItemCronogramaSuprimento.objects.select_related("cronograma_obra__obra").filter(pk=item_id).first())
        if item:
            self.initial["item_cronograma"] = item.pk
            self.initial["titulo"] = item.item

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get("item_cronograma")
        apropriacao = cleaned.get("apropriacao")
        if not item:
            raise forms.ValidationError("O suprimento de origem não foi informado.")
        cleaned["titulo"] = item.item
        if not apropriacao:
            raise forms.ValidationError("Selecione a apropriação financeira da compra.")
        if apropriacao.pai_id is None:
            self.add_error("apropriacao", "Selecione uma apropriação, não apenas a classe financeira.")
        return cleaned


# ============================================================
# ITEM DA COMPRA
# ============================================================


class MaterialCompraChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        partes = [obj.codigo or "MAT", obj.nome]
        if obj.especificacao:
            partes.append(obj.especificacao)
        partes.append(obj.unidade.sigla)
        return " · ".join(partes)


class ItemCompraAberturaForm(forms.Form):
    """Item selecionado exclusivamente do catálogo central de materiais."""

    material = MaterialCompraChoiceField(
        queryset=Material.objects.none(),
        label="Material",
        empty_label="Selecione um material",
        widget=forms.Select(
            attrs={
                "data-material-select": "1",
            }
        ),
    )

    quantidade = forms.DecimalField(
        min_value=0.0001,
        max_digits=18,
        decimal_places=4,
        label="Quantidade",
    )

    observacao = forms.CharField(
        required=False,
        label="Observação",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Informações específicas desta compra",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["material"].queryset = (
            Material.objects.filter(ativo=True)
            .select_related("unidade")
            .order_by("nome", "especificacao", "codigo")
        )
        for field in self.fields.values():
            classe_atual = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{classe_atual} cp-input".strip()


# ============================================================
# FORMSET DOS ITENS
# ============================================================


ItemCompraAberturaFormSet = formset_factory(
    ItemCompraAberturaForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


ItemCompraAberturaGrandeFornecedorFormSet = formset_factory(
    ItemCompraAberturaForm,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)

class CompraAvulsaForm(forms.Form):
    obra = forms.ModelChoiceField(queryset=None, label="Obra", empty_label="Selecione a obra")
    apropriacao = ApropriacaoChoiceField(queryset=PlanoFinanceiro.objects.none(), label="Apropriação financeira", empty_label="Selecione a apropriação")
    titulo = forms.CharField(max_length=255, label="Título da compra")
    comprador = forms.ModelChoiceField(queryset=None, label="Comprador responsável", required=False)
    descricao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Descrição")
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Observação geral")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from obras.models import Obra
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields["obra"].queryset = Obra.objects.all().order_by("nome")
        self.fields["apropriacao"].queryset = (
            PlanoFinanceiro.objects.filter(ativo=True, tipo=PlanoFinanceiro.Tipo.DESPESA, pai__isnull=False)
            .select_related("pai").order_by("pai__codigo", "codigo", "nome")
        )
        self.fields["comprador"].queryset = User.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["comprador"].label_from_instance = _rotulo_usuario
        for field in self.fields.values():
            classe = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{classe} cp-input".strip()

    def clean_apropriacao(self):
        apropriacao = self.cleaned_data["apropriacao"]
        if apropriacao.pai_id is None:
            raise forms.ValidationError("Selecione uma apropriação, não apenas a classe financeira.")
        return apropriacao

