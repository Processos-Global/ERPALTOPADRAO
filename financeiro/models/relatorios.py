from decimal import Decimal

from django.conf import settings
from django.db import models

from .titulos import AprovacaoTituloFinanceiro, TituloPagar


class RelatorioPagamento(models.Model):
    """Fechamento imutável de aprovações enviado ao setor responsável pelo pagamento."""

    numero = models.CharField(max_length=24, unique=True, db_index=True)
    periodo_inicio = models.DateField(db_index=True)
    periodo_fim = models.DateField(db_index=True)
    quantidade_itens = models.PositiveIntegerField(default=0)
    valor_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="relatorios_pagamento_emitidos",
    )
    emitido_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-emitido_em", "-id")
        verbose_name = "Relatório de pagamentos"
        verbose_name_plural = "Relatórios de pagamentos"

    def __str__(self):
        return self.numero


class ItemRelatorioPagamento(models.Model):
    """Snapshot do pagamento aprovado no momento da emissão do relatório."""

    relatorio = models.ForeignKey(
        RelatorioPagamento,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    aprovacao = models.OneToOneField(
        AprovacaoTituloFinanceiro,
        on_delete=models.PROTECT,
        related_name="item_relatorio_pagamento",
    )
    titulo = models.ForeignKey(
        TituloPagar,
        on_delete=models.PROTECT,
        related_name="itens_relatorio_pagamento",
    )

    data_aprovacao = models.DateTimeField()
    conta_numero = models.CharField(max_length=24)
    pedido_numero = models.CharField(max_length=80, blank=True)
    obra_nome = models.CharField(max_length=255, blank=True)
    beneficiario_nome = models.CharField(max_length=255)
    beneficiario_documento = models.CharField(max_length=40, blank=True)
    descricao = models.CharField(max_length=300)
    especificacao_pagamento = models.TextField(blank=True)
    apropriacao = models.CharField(max_length=350, blank=True)
    parcela = models.CharField(max_length=30, blank=True)
    vencimento = models.DateField(null=True, blank=True)
    valor = models.DecimalField(max_digits=18, decimal_places=2)
    origem = models.CharField(max_length=120, blank=True)
    observacao = models.TextField(blank=True)
    documento_numero = models.CharField(max_length=100, blank=True)
    competencia = models.DateField(null=True, blank=True)
    centro_custo_codigo = models.CharField(max_length=30, blank=True)
    centro_custo_descricao = models.CharField(max_length=160, blank=True)
    forma_pagamento = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("data_aprovacao", "id")
        verbose_name = "Item do relatório de pagamentos"
        verbose_name_plural = "Itens do relatório de pagamentos"

    def __str__(self):
        return f"{self.relatorio.numero} · {self.conta_numero}"
