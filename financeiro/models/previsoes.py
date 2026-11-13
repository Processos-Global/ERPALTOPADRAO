from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .cadastros import DespesaRecorrente, PlanoFinanceiro


class PrevisaoFinanceira(models.Model):
    class Origem(models.TextChoices):
        COMPRA = "COMPRA", "Compra"
        CONTRATO = "CONTRATO", "Contrato"
        MEDICAO = "MEDICAO", "Medição"
        RECORRENTE = "RECORRENTE", "Despesa recorrente"
        MANUAL = "MANUAL", "Manual"

    class Certeza(models.TextChoices):
        COMPROMETIDO = "COMPROMETIDO", "Comprometido"
        CONTRATADO = "CONTRATADO", "Contratado"
        PREVISTO = "PREVISTO", "Previsto"

    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.MANUAL, db_index=True)
    certeza = models.CharField(max_length=20, choices=Certeza.choices, default=Certeza.PREVISTO, db_index=True)
    descricao = models.CharField(max_length=300)
    obra = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previsoes_financeiras",
    )
    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previsoes_financeiras",
    )
    plano_financeiro = models.ForeignKey(
        PlanoFinanceiro,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previsoes",
    )
    pedido = models.ForeignKey(
        "compras.PedidoCompra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previsoes_financeiras",
    )
    parcela_pedido = models.OneToOneField(
        "compras.ParcelaPrevistaPedido",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="previsao_financeira",
    )
    despesa_recorrente = models.ForeignKey(
        DespesaRecorrente,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="previsoes",
    )
    competencia = models.DateField(null=True, blank=True)
    data_prevista = models.DateField(null=True, blank=True, db_index=True)
    valor_previsto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    ativa = models.BooleanField(default=True, db_index=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="previsoes_financeiras_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("data_prevista", "id")
        indexes = [
            models.Index(fields=["ativa", "data_prevista"], name="fin_prev_ativa_data_idx"),
            models.Index(fields=["obra", "origem"], name="fin_prev_obra_orig_idx"),
        ]

    def __str__(self):
        return f"{self.descricao} · R$ {self.valor_previsto}"
