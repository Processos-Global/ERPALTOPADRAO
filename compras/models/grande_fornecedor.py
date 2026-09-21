from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.storage import private_media_storage


class GrandeFornecedorProcesso(models.Model):
    processo = models.OneToOneField(
        "compras.ProcessoCompra",
        on_delete=models.CASCADE,
        related_name="grande_fornecedor",
    )
    fornecedor_escolhido = models.ForeignKey(
        "cadastros.Fornecedor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="processos_grande_fornecedor_escolhidos",
    )
    fornecedor_confirmado_em = models.DateTimeField(null=True, blank=True)
    condicao_pagamento_resumo = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fluxo de grande fornecedor"
        verbose_name_plural = "Fluxos de grandes fornecedores"

    def __str__(self):
        return f"{self.processo.numero} - {self.processo.titulo}"

    @property
    def valor_total_negociado(self):
        """Total da matriz já negociada pelo comprador."""
        return sum((item.valor_total for item in self.itens.all()), Decimal("0"))

    @property
    def valor_total_matriz(self):
        """Alias mantido para compatibilidade com telas antigas."""
        return self.valor_total_negociado

    @property
    def percentual_itens_entregues(self):
        itens = list(self.itens.exclude(status=GrandeFornecedorItem.Status.CANCELADO))
        if not itens:
            return Decimal("0")
        entregues = sum(1 for item in itens if item.status == GrandeFornecedorItem.Status.ENTREGUE)
        return (Decimal(entregues) / Decimal(len(itens))) * Decimal("100")


class GrandeFornecedorParticipante(models.Model):
    fluxo = models.ForeignKey(
        GrandeFornecedorProcesso,
        on_delete=models.CASCADE,
        related_name="participantes",
    )
    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor",
        on_delete=models.PROTECT,
        related_name="participacoes_grande_fornecedor",
    )
    documento_contrato = models.FileField(
        storage=private_media_storage,
        upload_to="compras/grandes_fornecedores/contratos/%Y/%m/",
        blank=True,
    )
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("fornecedor__nome", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["fluxo", "fornecedor"],
                name="comp_gf_part_fluxo_forn_uniq",
            )
        ]

    def __str__(self):
        return f"{self.fluxo.processo.numero} - {self.fornecedor.nome}"


class GrandeFornecedorItem(models.Model):
    class Status(models.TextChoices):
        AGUARDANDO = "AGUARDANDO", "Pedido gerado"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        PRODUCAO = "PRODUCAO", "Em produção"
        PRONTO = "PRONTO", "Pronto para expedição"
        TRANSPORTE = "TRANSPORTE", "Em transporte"
        PARCIAL = "PARCIAL", "Entrega parcial"
        ENTREGUE = "ENTREGUE", "Entregue"
        CANCELADO = "CANCELADO", "Cancelado"

    fluxo = models.ForeignKey(
        GrandeFornecedorProcesso,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    pavimento = models.CharField(max_length=120, blank=True)
    local = models.CharField(max_length=255, blank=True)
    material = models.ForeignKey(
        "cadastros.Material",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="itens_grande_fornecedor",
        help_text="Material selecionado do catálogo central. Obrigatório para novos itens.",
    )
    item_ficha_tecnica = models.ForeignKey(
        "obras.ItemFichaTecnica",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="itens_compatibilizacao_gf",
        help_text="Origem técnica do item quando importado da Ficha Técnica da Obra.",
    )
    item = models.CharField(max_length=500)
    especificacao = models.TextField(blank=True)
    unidade = models.CharField(max_length=20, default="UN")
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AGUARDANDO,
        db_index=True,
    )
    quantidade_recebida = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    previsao_entrega = models.DateField(null=True, blank=True, db_index=True)
    ordem = models.PositiveIntegerField(default=0)
    necessidade_gerada = models.OneToOneField(
        "compras.NecessidadeCompra",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="item_grande_fornecedor",
    )
    pedido_item = models.OneToOneField(
        "compras.PedidoCompraItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="item_grande_fornecedor",
    )
    participante_aprovado = models.ForeignKey(
        "compras.GrandeFornecedorParticipante",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="itens_aprovados",
        help_text="Fornecedor escolhido pelo gestor para este micro item.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "id")
        indexes = [models.Index(fields=["fluxo", "status"], name="comp_gf_item_status_idx")]

    @property
    def fornecedor(self):
        participante = self.participante_aprovado
        return participante.fornecedor if participante else None

    @property
    def oferta_negociada(self):
        if not self.participante_aprovado_id:
            return None
        # O prefetch feito pelas telas evita consultas extras na listagem.
        for oferta in self.ofertas.all():
            if oferta.participante_id == self.participante_aprovado_id:
                return oferta
        return None

    @property
    def valor_unitario(self):
        oferta = self.oferta_negociada
        return oferta.valor_atual if oferta and oferta.valor_atual is not None else Decimal("0")

    @property
    def valor_total(self):
        return (self.quantidade or Decimal("0")) * self.valor_unitario

    @property
    def percentual_recebido(self):
        if not self.quantidade:
            return Decimal("0")
        return min((self.quantidade_recebida / self.quantidade) * Decimal("100"), Decimal("100"))

    def __str__(self):
        return self.item


class GrandeFornecedorOferta(models.Model):
    item = models.ForeignKey(
        GrandeFornecedorItem,
        on_delete=models.CASCADE,
        related_name="ofertas",
    )
    participante = models.ForeignKey(
        GrandeFornecedorParticipante,
        on_delete=models.CASCADE,
        related_name="ofertas",
    )
    valor_inicial = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_atual = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ofertas_grandes_fornecedores_editadas",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "participante"],
                name="comp_gf_oferta_item_part_uniq",
            )
        ]

    @property
    def valor_total(self):
        if self.valor_atual is None:
            return None
        return self.item.quantidade * self.valor_atual


class HistoricoValorGrandeFornecedor(models.Model):
    oferta = models.ForeignKey(
        GrandeFornecedorOferta,
        on_delete=models.CASCADE,
        related_name="historico",
    )
    valor_anterior = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    valor_novo = models.DecimalField(max_digits=18, decimal_places=2)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="historico_valores_grandes_fornecedores",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")

    @property
    def diferenca(self):
        if self.valor_anterior is None:
            return Decimal("0")
        return self.valor_novo - self.valor_anterior


class ParcelaGrandeFornecedor(models.Model):
    class Gatilho(models.TextChoices):
        DATA = "DATA", "Data"
        ASSINATURA = "ASSINATURA", "Assinatura"
        PROJETO = "PROJETO", "Aprovação de projeto"
        FABRICACAO = "FABRICACAO", "Fabricação"
        ENTREGA = "ENTREGA", "Entrega"
        INSTALACAO = "INSTALACAO", "Instalação"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        PREVISTO = "PREVISTO", "Previsto"
        LIBERADO = "LIBERADO", "Liberado"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"

    fluxo = models.ForeignKey(
        GrandeFornecedorProcesso,
        on_delete=models.CASCADE,
        related_name="parcelas",
    )
    ordem = models.PositiveIntegerField(default=1)
    descricao = models.CharField(max_length=255)
    percentual = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    valor = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    data_prevista = models.DateField(null=True, blank=True)
    gatilho = models.CharField(max_length=20, choices=Gatilho.choices, default=Gatilho.DATA)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREVISTO)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("ordem", "id")


class RateioParcelaGrandeFornecedor(models.Model):
    parcela = models.ForeignKey(
        ParcelaGrandeFornecedor,
        on_delete=models.CASCADE,
        related_name="rateios",
    )
    beneficiario_nome = models.CharField(max_length=255)
    documento = models.CharField(max_length=40, blank=True)
    valor = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
