from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class LiberacaoFinanceiraPedido(models.Model):
    """Valor individualmente reconhecido para pagamento de um pedido.

    A autorização cria um título próprio; o pedido e os títulos antigos não são
    alterados em valor. A origem é identificada pela referência idempotente.
    """

    class Tipo(models.TextChoices):
        RECEBIMENTO = "RECEBIMENTO", "Recebimento"
        ANTECIPACAO = "ANTECIPACAO", "Antecipação"
        PARCELA = "PARCELA", "Parcela contratual"
        MEDICAO = "MEDICAO", "Medição"
        CONDICAO = "CONDICAO", "Condição contratual"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente de liberação"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        AUTORIZADA = "AUTORIZADA", "Liberada"
        COMPENSADA = "COMPENSADA", "Coberta por antecipação"
        CANCELADA = "CANCELADA", "Cancelada"

    pedido = models.ForeignKey("compras.PedidoCompra", on_delete=models.PROTECT, related_name="liberacoes_financeiras")
    recebimento = models.OneToOneField("compras.RecebimentoPedido", null=True, blank=True, on_delete=models.PROTECT, related_name="liberacao_financeira")
    parcela = models.ForeignKey("compras.ParcelaPrevistaPedido", null=True, blank=True, on_delete=models.PROTECT, related_name="liberacoes_financeiras")
    titulo = models.OneToOneField("financeiro.TituloPagar", null=True, blank=True, on_delete=models.PROTECT, related_name="liberacao_pedido")
    referencia = models.CharField(max_length=160, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, db_index=True)
    valor = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    valor_origem = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    valor_compensado = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    justificativa = models.TextField(blank=True)
    divergencia = models.TextField(blank=True)
    motivo_cancelamento = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="liberacoes_pedido_criadas")
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="liberacoes_pedido_autorizadas")
    criado_em = models.DateTimeField(auto_now_add=True)
    autorizado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="liberacoes_pedido_canceladas")
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-criado_em", "-id")
        indexes = [models.Index(fields=["pedido", "status"], name="fin_lib_ped_st_idx")]

    def __str__(self):
        return f"{self.pedido.numero} · {self.get_tipo_display()} · R$ {self.valor:.2f}"
