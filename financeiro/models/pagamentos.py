from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.storage import private_media_storage

from .titulos import TituloPagar


class Pagamento(models.Model):
    class Status(models.TextChoices):
        EFETIVADO = "EFETIVADO", "Efetivado"
        ESTORNADO = "ESTORNADO", "Estornado"

    class Forma(models.TextChoices):
        PIX = "PIX", "PIX"
        TED = "TED", "TED"
        BOLETO = "BOLETO", "Boleto"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        DEBITO = "DEBITO", "Débito"
        CHEQUE = "CHEQUE", "Cheque"
        DINHEIRO = "DINHEIRO", "Dinheiro"
        OUTRO = "OUTRO", "Outro"

    # Regra Alto Padrão: um título possui no máximo um pagamento efetivado.
    titulo = models.OneToOneField(
        TituloPagar,
        on_delete=models.PROTECT,
        related_name="pagamento",
    )
    data_pagamento = models.DateField(db_index=True)
    valor = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    forma = models.CharField(max_length=20, choices=Forma.choices, default=Forma.PIX)
    referencia_bancaria = models.CharField(max_length=120, blank=True)
    comprovante = models.FileField(storage=private_media_storage, upload_to="financeiro/comprovantes/%Y/%m/", blank=True)
    observacao = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EFETIVADO, db_index=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="pagamentos_financeiros_registrados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    estornado_em = models.DateTimeField(null=True, blank=True)
    estornado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pagamentos_financeiros_estornados",
    )
    motivo_estorno = models.TextField(blank=True)

    class Meta:
        ordering = ("-data_pagamento", "-id")

    def __str__(self):
        return f"{self.titulo.numero} · R$ {self.valor}"
