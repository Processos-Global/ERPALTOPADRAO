from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class RegraPrazoCompra(models.Model):
    class Escopo(models.TextChoices):
        ETAPA = "ETAPA", "Etapa interna"
        PROCESSO = "PROCESSO", "Processo completo"
        ENTREGA = "ENTREGA", "Entrega comercial"

    class Contagem(models.TextChoices):
        CORRIDOS = "CORRIDOS", "Dias corridos"
        UTEIS = "UTEIS", "Dias úteis"

    class TipoFornecedor(models.TextChoices):
        TODOS = "TODOS", "Todos"
        COMUM = "COMUM", "Fornecedor comum"
        GRANDE = "GRANDE", "Grande fornecedor"

    escopo = models.CharField(max_length=12, choices=Escopo.choices)
    etapa = models.CharField(max_length=30, choices=[(v, label) for v, label in (
        ("COTACAO", "Cotação"), ("COMPATIBILIZACAO", "Análise técnica"),
        ("NEGOCIACAO", "Negociação"), ("APROVACAO", "Aprovação"),
        ("CONTRATACAO", "Contratação"),
    )], blank=True)
    tipo_fornecedor = models.CharField(max_length=6, choices=TipoFornecedor.choices, default=TipoFornecedor.TODOS)
    categoria = models.ForeignKey("cadastros.CategoriaGrandeFornecedor", null=True, blank=True, on_delete=models.PROTECT)
    material = models.ForeignKey("cadastros.Material", null=True, blank=True, on_delete=models.PROTECT)
    dias = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    contagem = models.CharField(max_length=8, choices=Contagem.choices, default=Contagem.CORRIDOS)
    dias_alerta = models.PositiveIntegerField(default=2)
    vigente_desde = models.DateField()
    vigente_ate = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    justificativa = models.TextField()

    class Meta:
        ordering = ("-vigente_desde", "-id")
        indexes = [models.Index(fields=["escopo", "etapa", "vigente_desde"], name="comp_sla_regra_vig_idx")]

    def clean(self):
        from compras.models import ProcessoCompra

        if self.etapa and self.etapa not in ProcessoCompra.Etapa.values[:-1]:
            raise ValidationError({"etapa": "Etapa inexistente no fluxo de compras."})
        if self.escopo == self.Escopo.ETAPA and not self.etapa:
            raise ValidationError({"etapa": "Informe uma etapa existente."})
        if self.escopo != self.Escopo.ETAPA and self.etapa:
            raise ValidationError({"etapa": "Este escopo não admite etapa."})
        if self.vigente_ate and self.vigente_ate < self.vigente_desde:
            raise ValidationError({"vigente_ate": "Fim anterior ao início da vigência."})
        if not (self.justificativa or "").strip():
            raise ValidationError({"justificativa": "Justifique a alteração do prazo."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Regras de prazo são imutáveis; registre uma nova vigência.")
        self.full_clean()
        return super().save(*args, **kwargs)


class TransicaoEtapaCompra(models.Model):
    processo = models.ForeignKey("compras.ProcessoCompra", on_delete=models.PROTECT, related_name="transicoes_sla")
    etapa = models.CharField(max_length=30)
    iniciada_em = models.DateTimeField()
    encerrada_em = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    regra = models.ForeignKey(RegraPrazoCompra, null=True, blank=True, on_delete=models.PROTECT)
    prazo_dias = models.PositiveIntegerField(null=True, blank=True)
    contagem = models.CharField(max_length=8, blank=True)
    dias_alerta = models.PositiveIntegerField(null=True, blank=True)
    limite_em = models.DateField(null=True, blank=True)
    etapa_anterior = models.CharField(max_length=30, blank=True)
    motivo = models.CharField(max_length=100, blank=True)
    registrado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("iniciada_em", "id")
        indexes = [models.Index(fields=["processo", "encerrada_em"], name="comp_sla_tr_proc_fim_idx")]


class PrazoEntregaPedido(models.Model):
    """Regra comercial congelada na emissão; não substitui previsão contratual do pedido."""

    pedido = models.OneToOneField("compras.PedidoCompra", on_delete=models.PROTECT, related_name="prazo_sla")
    regra = models.ForeignKey(RegraPrazoCompra, null=True, blank=True, on_delete=models.PROTECT)
    prazo_dias = models.PositiveIntegerField(null=True, blank=True)
    contagem = models.CharField(max_length=8, blank=True)
    limite_em = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
