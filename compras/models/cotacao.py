from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from .core import FornecedorCompra, NecessidadeCompra, ProcessoCompra


class SolicitacaoCotacaoFornecedor(models.Model):
    class Status(models.TextChoices):
        PENDENTE_ENVIO = "PENDENTE_ENVIO", "Pendente de envio"
        ENVIADA = "ENVIADA", "Aguardando proposta"
        RESPONDIDA = "RESPONDIDA", "Proposta recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    class MeioEnvio(models.TextChoices):
        EMAIL = "EMAIL", "E-mail"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        TELEFONE = "TELEFONE", "Telefone"
        PORTAL = "PORTAL", "Portal do fornecedor"
        OUTRO = "OUTRO", "Outro"

    processo = models.ForeignKey(
        ProcessoCompra,
        on_delete=models.CASCADE,
        related_name="solicitacoes_cotacao",
    )
    fornecedor = models.ForeignKey(
        FornecedorCompra,
        on_delete=models.PROTECT,
        related_name="solicitacoes_cotacao",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE_ENVIO,
        db_index=True,
    )
    meio_envio = models.CharField(
        max_length=20,
        choices=MeioEnvio.choices,
        blank=True,
    )
    observacao_envio = models.TextField(blank=True)
    enviada_em = models.DateTimeField(null=True, blank=True, db_index=True)
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="solicitacoes_cotacao_enviadas",
    )
    respondida_em = models.DateTimeField(null=True, blank=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("fornecedor__nome", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["processo", "fornecedor"],
                name="comp_solcot_proc_forn_uniq",
            )
        ]

    def __str__(self):
        return f"{self.processo.numero} - {self.fornecedor.nome}"


class CotacaoFornecedor(models.Model):
    processo = models.ForeignKey(ProcessoCompra, on_delete=models.CASCADE, related_name="cotacoes")
    fornecedor = models.ForeignKey(FornecedorCompra, on_delete=models.PROTECT, related_name="cotacoes")
    data_proposta = models.DateField(null=True, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    condicao_pagamento = models.CharField(max_length=255, blank=True)
    frete = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    validade = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    documento = models.FileField(upload_to="compras/cotacoes/%Y/%m/", null=True, blank=True)
    enviada_compatibilizacao_em = models.DateTimeField(null=True, blank=True, db_index=True)
    enviada_compatibilizacao_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cotacoes_enviadas_compatibilizacao",
    )
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cotacoes_fornecedor_criadas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["processo", "fornecedor"], name="comp_cot_proc_forn_uniq")]

    def __str__(self):
        return f"{self.fornecedor.nome} - {self.processo.numero}"

    @property
    def enviada_para_compatibilizacao(self):
        return self.enviada_compatibilizacao_em is not None


class CotacaoFornecedorItem(models.Model):
    cotacao = models.ForeignKey(CotacaoFornecedor, on_delete=models.CASCADE, related_name="itens")
    necessidade = models.ForeignKey(NecessidadeCompra, on_delete=models.PROTECT, related_name="itens_cotados")
    descricao_comercial = models.CharField(max_length=500, blank=True)
    marca = models.CharField(max_length=120, blank=True)
    modelo = models.CharField(max_length=120, blank=True)
    especificacao_ofertada = models.TextField(blank=True)
    quantidade = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))])
    valor_unitario_cotado = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    desconto_cotado = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    observacoes = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cotacao", "necessidade"], name="comp_cot_item_uniq")
        ]

    def __str__(self):
        return f"{self.cotacao.fornecedor.nome} - {self.necessidade.descricao}"

    @property
    def valor_total_cotado(self):
        return max(self.quantidade * self.valor_unitario_cotado - self.desconto_cotado, Decimal("0"))
