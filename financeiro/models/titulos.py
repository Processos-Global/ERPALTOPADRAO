from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from financeiro.services.regras import calcular_saldo_titulo
from .cadastros import PlanoFinanceiro
from .previsoes import PrevisaoFinanceira


class TituloPagar(models.Model):
    class Origem(models.TextChoices):
        COMPRA = "COMPRA", "Compra"
        CONTRATO = "CONTRATO", "Contrato"
        MEDICAO = "MEDICAO", "Medição"
        DESPESA = "DESPESA", "Despesa"
        IMPOSTO = "IMPOSTO", "Imposto"
        ADIANTAMENTO = "ADIANTAMENTO", "Adiantamento"
        REEMBOLSO = "REEMBOLSO", "Reembolso"
        FOLHA = "FOLHA", "Folha"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        DOCUMENTO_RECEBIDO = "DOCUMENTO_RECEBIDO", "Documento recebido"
        EM_CONFERENCIA = "EM_CONFERENCIA", "Em conferência"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        APROVADO = "APROVADO", "Aprovado"
        PAGO = "PAGO", "Pago"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"
        REJEITADO = "REJEITADO", "Rejeitado"
        CANCELADO = "CANCELADO", "Cancelado"

    class Conferencia(models.TextChoices):
        NAO_CONFERIDO = "NAO_CONFERIDO", "Não conferido"
        CONFERIDO = "CONFERIDO", "Conferido"
        DIVERGENCIA = "DIVERGENCIA", "Divergência"

    numero = models.CharField(max_length=24, unique=True, db_index=True)
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.OUTRO, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.RASCUNHO, db_index=True)
    conferencia = models.CharField(max_length=20, choices=Conferencia.choices, default=Conferencia.NAO_CONFERIDO, db_index=True)
    fornecedor = models.ForeignKey("cadastros.Fornecedor", null=True, blank=True, on_delete=models.PROTECT, related_name="titulos_financeiros")
    obra = models.ForeignKey("obras.Obra", null=True, blank=True, on_delete=models.PROTECT, related_name="titulos_financeiros")
    plano_financeiro = models.ForeignKey(PlanoFinanceiro, null=True, blank=True, on_delete=models.PROTECT, related_name="titulos")
    pedido = models.ForeignKey("compras.PedidoCompra", null=True, blank=True, on_delete=models.PROTECT, related_name="titulos_financeiros")
    recebimento = models.OneToOneField("compras.RecebimentoPedido", null=True, blank=True, on_delete=models.PROTECT, related_name="titulo_financeiro")
    previsao_origem = models.ForeignKey(PrevisaoFinanceira, null=True, blank=True, on_delete=models.SET_NULL, related_name="titulos_gerados")
    descricao = models.CharField(max_length=300)
    documento_numero = models.CharField(max_length=100, blank=True, db_index=True)
    arquivo_documento = models.FileField(upload_to="financeiro/documentos/%Y/%m/", blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    competencia = models.DateField(null=True, blank=True)
    vencimento = models.DateField(null=True, blank=True, db_index=True)
    valor_original = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    desconto = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    juros = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    multa = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    outros_acrescimos = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    observacao = models.TextField(blank=True)
    ciclo_aprovacao = models.PositiveIntegerField(default=0)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="titulos_financeiros_criados")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("vencimento", "numero")
        indexes = [
            models.Index(fields=["status", "vencimento"], name="fin_tit_st_venc_idx"),
            models.Index(fields=["obra", "status"], name="fin_tit_obra_st_idx"),
            models.Index(fields=["fornecedor", "vencimento"], name="fin_tit_forn_venc_idx"),
        ]

    def __str__(self):
        return f"{self.numero} · {self.descricao}"

    @property
    def acrescimos(self):
        return (self.juros or Decimal("0")) + (self.multa or Decimal("0")) + (self.outros_acrescimos or Decimal("0"))

    @property
    def valor_liquido(self):
        return max((self.valor_original or Decimal("0")) + self.acrescimos - (self.desconto or Decimal("0")), Decimal("0"))

    @property
    def total_pago(self):
        pagamento = getattr(self, "pagamento", None)
        if pagamento and pagamento.status == "EFETIVADO":
            return pagamento.valor
        return Decimal("0")

    @property
    def saldo_aberto(self):
        return calcular_saldo_titulo(self.valor_original, self.acrescimos, self.desconto, self.total_pago)

    @property
    def esta_pago(self):
        return self.status == self.Status.PAGO or self.total_pago > 0

    @property
    def esta_vencido(self):
        return bool(
            self.vencimento
            and self.vencimento < timezone.localdate()
            and self.status not in {self.Status.PAGO, self.Status.CANCELADO}
            and self.saldo_aberto > 0
        )


class HistoricoTituloFinanceiro(models.Model):
    titulo = models.ForeignKey(TituloPagar, on_delete=models.CASCADE, related_name="historico")
    evento = models.CharField(max_length=80)
    descricao = models.CharField(max_length=500)
    dados = models.JSONField(default=dict, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="historicos_titulos_financeiros")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")


class AprovacaoTituloFinanceiro(models.Model):
    class Decisao(models.TextChoices):
        APROVADO = "APROVADO", "Aprovado"
        REJEITADO = "REJEITADO", "Rejeitado"

    titulo = models.ForeignKey(TituloPagar, on_delete=models.PROTECT, related_name="aprovacoes")
    ciclo = models.PositiveIntegerField(default=1)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="aprovacoes_financeiras")
    decisao = models.CharField(max_length=20, choices=Decisao.choices)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("criado_em", "id")
        constraints = [
            models.UniqueConstraint(fields=["titulo", "ciclo"], name="fin_aprov_tit_ciclo_uniq"),
        ]
