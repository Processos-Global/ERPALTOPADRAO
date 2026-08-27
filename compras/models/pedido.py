from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .core import NecessidadeCompra, ProcessoCompra


class PedidoCompra(models.Model):
    class Status(models.TextChoices):
        PEDIDO_EMITIDO = "PEDIDO_EMITIDO", "Aguardando fornecedor"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        EM_PRODUCAO = "EM_PRODUCAO", "Em produção"
        PRONTO_EXPEDICAO = "PRONTO_EXPEDICAO", "Pronto para expedição"
        EM_TRANSPORTE = "EM_TRANSPORTE", "Em transporte"
        ENTREGA_PARCIAL = "ENTREGA_PARCIAL", "Entrega parcial"
        ENTREGUE = "ENTREGUE", "Entregue"
        CANCELADO = "CANCELADO", "Cancelado"

    numero = models.CharField(max_length=20, unique=True, db_index=True)
    processo = models.ForeignKey(ProcessoCompra, on_delete=models.PROTECT, related_name="pedidos")
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="pedidos_compra")
    fornecedor = models.ForeignKey("cadastros.Fornecedor", on_delete=models.PROTECT, related_name="pedidos")
    data = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PEDIDO_EMITIDO, db_index=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    descontos = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    frete = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    valor_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    condicao_pagamento = models.CharField(max_length=255, blank=True)
    previsao_entrega_original = models.DateField(null=True, blank=True)
    previsao_entrega_atual = models.DateField(null=True, blank=True)
    local_entrega = models.CharField(max_length=500, blank=True)
    observacoes = models.TextField(blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="pedidos_compra_responsavel",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    recebido_em = models.DateTimeField(null=True, blank=True)
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pedidos_compra_recebidos",
    )
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pedidos_compra_cancelados",
    )
    cancelado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        ordering = ("-criado_em",)
        indexes = [
            models.Index(fields=["obra", "status"], name="comp_ped_obra_st_idx"),
            models.Index(fields=["processo", "fornecedor"], name="comp_ped_proc_forn_idx"),
        ]

    def __str__(self):
        return f"{self.numero} - {self.fornecedor.nome}"

    @property
    def percentual_recebido(self):
        itens = list(self.itens.all())
        if not itens:
            return Decimal("0")
        total = sum((item.quantidade for item in itens), Decimal("0"))
        recebido = sum((item.quantidade_recebida for item in itens), Decimal("0"))
        if total <= 0:
            return Decimal("0")
        return min((recebido / total) * Decimal("100"), Decimal("100"))


class PedidoCompraItem(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="itens")
    necessidade = models.ForeignKey(NecessidadeCompra, on_delete=models.PROTECT, related_name="itens_pedido")
    descricao = models.CharField(max_length=500)
    especificacao = models.TextField(blank=True)
    unidade = models.CharField(max_length=10)
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    quantidade_recebida = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    desconto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    @property
    def saldo_receber(self):
        return max(self.quantidade - self.quantidade_recebida, Decimal("0"))

    @property
    def quantidade_excedente(self):
        """Quantidade recebida acima do que foi originalmente pedido."""
        return max(self.quantidade_recebida - self.quantidade, Decimal("0"))


class ParcelaPrevistaPedido(models.Model):
    class Gatilho(models.TextChoices):
        DATA = "DATA", "Data"
        ASSINATURA = "ASSINATURA", "Assinatura"
        FABRICACAO = "FABRICACAO", "Fabricação"
        ENTREGA = "ENTREGA", "Entrega"
        INSTALACAO = "INSTALACAO", "Instalação"
        OUTRO = "OUTRO", "Outro"

    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="parcelas_previstas")
    ordem = models.PositiveIntegerField(default=1)
    percentual = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    valor = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    data_prevista = models.DateField(null=True, blank=True)
    dias = models.IntegerField(null=True, blank=True)
    evento_gatilho = models.CharField(max_length=20, choices=Gatilho.choices, default=Gatilho.DATA)
    descricao = models.CharField(max_length=255, blank=True)


class HistoricoPrevisaoPedido(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="historico_previsoes")
    previsao_anterior = models.DateField(null=True, blank=True)
    previsao_nova = models.DateField()
    motivo = models.TextField(blank=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="alteracoes_previsao_pedido",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")


class RecebimentoPedido(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.PROTECT, related_name="recebimentos")
    numero_nota_fiscal = models.CharField(max_length=80, null=True, blank=True)
    arquivo_nota_fiscal = models.FileField(upload_to="compras/notas_fiscais/%Y/%m/", blank=True)
    valor_total_nota = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="recebimentos_pedidos_compra",
    )
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["pedido", "numero_nota_fiscal"],
                name="comp_rec_ped_nf_uniq",
            )
        ]

    @property
    def valor_itens_recebidos(self):
        return sum(((item.valor_recebido or Decimal("0")) for item in self.itens.all()), Decimal("0"))

    @property
    def nome_arquivo_nota_fiscal(self):
        return self.arquivo_nota_fiscal.name.rsplit("/", 1)[-1] if self.arquivo_nota_fiscal else ""


class RecebimentoPedidoItem(models.Model):
    recebimento = models.ForeignKey(RecebimentoPedido, on_delete=models.CASCADE, related_name="itens")
    item_pedido = models.ForeignKey(PedidoCompraItem, on_delete=models.PROTECT, related_name="recebimentos")
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    valor_recebido = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recebimento", "item_pedido"],
                name="comp_rec_item_uniq",
            )
        ]


class PedidoCompraAnexo(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="compras/pedidos/%Y/%m/")
    descricao = models.CharField(max_length=255, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="anexos_pedidos_compra",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em",)

    def __str__(self):
        return f"{self.pedido.numero} - {self.arquivo.name.rsplit('/', 1)[-1]}"

    @property
    def nome_arquivo(self):
        return self.arquivo.name.rsplit("/", 1)[-1]