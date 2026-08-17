from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .core import FornecedorCompra, NecessidadeCompra, ProcessoCompra
from .cotacao import CotacaoFornecedor, CotacaoFornecedorItem


class CompatibilizacaoItem(models.Model):
    class Resultado(models.TextChoices):
        APROVADO = "APROVADO", "Aprovado"
        APROVADO_COM_RESSALVA = "APROVADO_COM_RESSALVA", "Aprovado com ressalva"
        REPROVADO = "REPROVADO", "Reprovado"

    item_cotado = models.ForeignKey(
        CotacaoFornecedorItem,
        on_delete=models.PROTECT,
        related_name="compatibilizacoes",
    )
    resultado = models.CharField(max_length=30, choices=Resultado.choices)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="compatibilizacoes_compras",
    )
    data = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(blank=True)
    ressalva_motivo = models.TextField(blank=True)

    class Meta:
        ordering = ("-data", "-id")


class NegociacaoItem(models.Model):
    """Condição comercial final atual do item, sem alterar a proposta original."""

    item_cotado = models.OneToOneField(
        CotacaoFornecedorItem,
        on_delete=models.CASCADE,
        related_name="negociacao",
    )
    valor_unitario_negociado = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    frete_negociado = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    prazo_entrega_dias_negociado = models.PositiveIntegerField(null=True, blank=True)
    condicao_pagamento_negociada = models.CharField(max_length=255, blank=True)
    observacoes = models.TextField(blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="negociacoes_compras",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def valor_final_unitario(self):
        if self.valor_unitario_negociado is not None:
            return self.valor_unitario_negociado
        return self.item_cotado.valor_unitario_cotado


class HistoricoNegociacaoItem(models.Model):
    """Snapshot append-only de cada alteração de negociação."""

    item_cotado = models.ForeignKey(
        CotacaoFornecedorItem,
        on_delete=models.PROTECT,
        related_name="historico_negociacoes",
    )
    valor_unitario_negociado = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    frete_negociado = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    prazo_entrega_dias_negociado = models.PositiveIntegerField(null=True, blank=True)
    condicao_pagamento_negociada = models.CharField(max_length=255, blank=True)
    observacoes = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="historico_negociacoes_compras",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")


class AdjudicacaoCompra(models.Model):
    processo = models.ForeignKey(ProcessoCompra, on_delete=models.PROTECT, related_name="adjudicacoes")
    necessidade = models.ForeignKey(NecessidadeCompra, on_delete=models.PROTECT, related_name="adjudicacoes")
    cotacao = models.ForeignKey(CotacaoFornecedor, on_delete=models.PROTECT, related_name="adjudicacoes")
    item_cotado = models.ForeignKey(CotacaoFornecedorItem, on_delete=models.PROTECT, related_name="adjudicacoes")
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    valor_unitario_final = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    desconto_final = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Desconto congelado para a quantidade adjudicada.",
    )
    prazo_entrega_dias_final = models.PositiveIntegerField(null=True, blank=True)
    condicao_pagamento_final = models.CharField(max_length=255, blank=True)
    selecionado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="adjudicacoes_compras",
    )
    selecionado_em = models.DateTimeField(auto_now_add=True)
    cancelada = models.BooleanField(default=False, db_index=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjudicacoes_compras_canceladas",
    )
    cancelada_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)

    @property
    def valor_bruto(self):
        return self.quantidade * self.valor_unitario_final

    @property
    def valor_total(self):
        return max(self.valor_bruto - (self.desconto_final or Decimal("0")), Decimal("0"))


class AlcadaAprovacaoCompra(models.Model):
    """Configuração futura de alçadas sem hardcode de valores nas regras."""

    nome = models.CharField(max_length=120)
    obra = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="alcadas_compras",
    )
    valor_minimo = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    valor_maximo = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cargo = models.CharField(max_length=30, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alcadas_aprovacao_compras",
    )
    ordem = models.PositiveIntegerField(default=1)
    ativo = models.BooleanField(default=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "valor_minimo", "id")


class AprovacaoCompra(models.Model):
    class Decisao(models.TextChoices):
        APROVADO = "APROVADO", "Aprovado"
        REPROVADO = "REPROVADO", "Reprovado"
        AJUSTE_SOLICITADO = "AJUSTE_SOLICITADO", "Ajuste solicitado"

    processo = models.ForeignKey(ProcessoCompra, on_delete=models.PROTECT, related_name="aprovacoes")
    ciclo = models.PositiveIntegerField(default=1)
    alcada = models.ForeignKey(
        AlcadaAprovacaoCompra,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decisoes",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="aprovacoes_compras",
    )
    decisao = models.CharField(max_length=30, choices=Decisao.choices)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")


class ContratacaoCompra(models.Model):
    class TipoFormalizacao(models.TextChoices):
        PEDIDO = "PEDIDO", "Pedido"
        CONTRATO = "CONTRATO", "Contrato"
        PEDIDO_E_CONTRATO = "PEDIDO_E_CONTRATO", "Pedido e contrato"

    processo = models.ForeignKey(
        ProcessoCompra,
        on_delete=models.PROTECT,
        related_name="contratacoes",
    )
    fornecedor = models.ForeignKey(
        FornecedorCompra,
        on_delete=models.PROTECT,
        related_name="contratacoes",
    )
    tipo_formalizacao = models.CharField(
        max_length=30,
        choices=TipoFormalizacao.choices,
        default=TipoFormalizacao.PEDIDO,
    )
    condicao_pagamento = models.CharField(max_length=255, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    previsao_entrega = models.DateField(null=True, blank=True)
    local_entrega = models.CharField(max_length=500, blank=True)
    referencia_contrato = models.CharField(max_length=120, blank=True)
    documento = models.FileField(upload_to="compras/contratacoes/%Y/%m/", null=True, blank=True)
    observacoes = models.TextField(blank=True)
    formalizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="contratacoes_compras_formalizadas",
    )
    formalizado_em = models.DateTimeField(auto_now_add=True)
    cancelada = models.BooleanField(default=False, db_index=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contratacoes_compras_canceladas",
    )
    cancelada_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["processo", "fornecedor"],
                condition=models.Q(cancelada=False),
                name="comp_contrat_proc_forn_ativa_uniq",
            )
        ]
