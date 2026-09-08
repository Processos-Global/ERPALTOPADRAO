from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ProcessoCompra(models.Model):
    class Etapa(models.TextChoices):
        COTACAO = "COTACAO", "Cotação"
        COMPATIBILIZACAO = "COMPATIBILIZACAO", "Análise técnica"
        NEGOCIACAO = "NEGOCIACAO", "Negociação"
        APROVACAO = "APROVACAO", "Aprovação"
        CONTRATACAO = "CONTRATACAO", "Contratação"
        CONTRATADO = "CONTRATADO", "Contratado"

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        PEDIDO_ENVIADO = "PEDIDO_ENVIADO", "Solicitação enviada"
        SOLICITACAO_COTACAO = "SOLICITACAO_COTACAO", "Aguardando fornecedor"
        AGUARDANDO_COTACAO = "AGUARDANDO_COTACAO", "Aguardando fornecedor"
        EM_COTACAO = "EM_COTACAO", "Proposta recebida"
        AGUARDANDO_COMPATIBILIZACAO = "AGUARDANDO_COMPATIBILIZACAO", "Aguardando análise técnica"
        EM_COMPATIBILIZACAO = "EM_COMPATIBILIZACAO", "Em análise técnica"
        EM_NEGOCIACAO = "EM_NEGOCIACAO", "Em negociação"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        AJUSTE_SOLICITADO = "AJUSTE_SOLICITADO", "Ajuste solicitado"
        APROVADO = "APROVADO", "Aprovado"
        EM_CONTRATACAO = "EM_CONTRATACAO", "Em contratação"
        CONTRATADO = "CONTRATADO", "Contratado"
        REPROVADO = "REPROVADO", "Reprovado"
        CANCELADO = "CANCELADO", "Cancelado"

    numero = models.CharField(max_length=20, unique=True, db_index=True)
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="processos_compra")
    item_cronograma = models.ForeignKey(
        "planejamento.ItemCronogramaSuprimento",
        on_delete=models.PROTECT,
        related_name="processos_compra",
    )
    titulo = models.CharField(max_length=255)
    descricao = models.TextField(blank=True)
    comprador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processos_compra_responsavel",
    )
    etapa_atual = models.CharField(max_length=30, choices=Etapa.choices, default=Etapa.COTACAO, db_index=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.RASCUNHO, db_index=True)
    data_abertura = models.DateField(auto_now_add=True)
    data_cotacao_concluida = models.DateTimeField(null=True, blank=True)
    data_compatibilizacao_concluida = models.DateTimeField(null=True, blank=True)
    data_negociacao_concluida = models.DateTimeField(null=True, blank=True)
    data_contratacao_concluida = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="processos_compra_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processos_compra_cancelados",
    )
    cancelado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        ordering = ("-criado_em",)
        indexes = [
            models.Index(fields=["obra", "status"], name="comp_proc_obra_st_idx"),
            models.Index(fields=["comprador", "etapa_atual"], name="comp_proc_comp_et_idx"),
        ]

    def __str__(self):
        return f"{self.numero} - {self.titulo}"


class ProcessoCompraAtividade(models.Model):
    processo = models.ForeignKey(ProcessoCompra, on_delete=models.CASCADE, related_name="vinculos_atividades")
    atividade = models.ForeignKey(
        "planejamento.AtividadePlanejamento",
        on_delete=models.PROTECT,
        related_name="vinculos_compras",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="vinculos_compra_atividade_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["processo", "atividade"], name="comp_proc_atv_uniq")
        ]


class NecessidadeCompra(models.Model):
    class Situacao(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        ATENDIDA = "ATENDIDA", "Atendida"
        CANCELADA = "CANCELADA", "Cancelada"

    class UnidadeMedida(models.TextChoices):
        UN = "UN", "Unidade"
        M = "M", "Metro"
        M2 = "M2", "Metro quadrado"
        M3 = "M3", "Metro cúbico"
        KG = "KG", "Quilograma"
        T = "T", "Tonelada"
        L = "L", "Litro"
        SC = "SC", "Saco"
        CX = "CX", "Caixa"
        PC = "PC", "Peça"
        GL = "GL", "Galão"
        RL = "RL", "Rolo"
        PT = "PT", "Pacote"
        VB = "VB", "Verba"

    processo = models.ForeignKey(ProcessoCompra, on_delete=models.CASCADE, related_name="necessidades")
    atividade_origem = models.ForeignKey(
        "planejamento.AtividadePlanejamento",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="necessidades_compra",
        help_text=(
            "Opcional. Quando vazio, o item atende ao conjunto de atividades "
            "vinculadas ao processo de compra."
        ),
    )
    material = models.ForeignKey(
        "cadastros.Material",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="necessidades_compra",
        help_text="Material do catálogo central. Obrigatório para novas compras.",
    )
    descricao = models.CharField(max_length=500)
    especificacao = models.TextField(blank=True)
    unidade = models.CharField(max_length=10, choices=UnidadeMedida.choices)
    quantidade_necessaria = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    quantidade_incluida = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    observacao = models.TextField(blank=True)
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.ATIVA, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("descricao", "id")

    def __str__(self):
        return f"{self.descricao} - {self.quantidade_incluida} {self.unidade}"

    @property
    def quantidade_adjudicada(self):
        return self.adjudicacoes.filter(cancelada=False).aggregate(v=models.Sum("quantidade"))["v"] or Decimal("0")

    @property
    def saldo(self):
        return max((self.quantidade_incluida or Decimal("0")) - self.quantidade_adjudicada, Decimal("0"))


class SequenciaDocumentoCompra(models.Model):
    tipo = models.CharField(max_length=10)
    ano = models.PositiveIntegerField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tipo", "ano"], name="comp_seq_tipo_ano_uniq")
        ]
