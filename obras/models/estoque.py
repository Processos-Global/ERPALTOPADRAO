from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class MovimentoEstoque(models.Model):
    class Tipo(models.TextChoices):
        SAIDA = "SAIDA", "Saída"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"

    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    obra_origem = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        related_name="movimentos_estoque_saida",
        verbose_name="Obra de origem",
    )
    obra_destino = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="movimentos_estoque_entrada",
        verbose_name="Obra de destino",
    )
    material = models.ForeignKey(
        "cadastros.Material",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="movimentos_estoque_obras",
        verbose_name="Material",
    )
    descricao_item = models.CharField(max_length=500, verbose_name="Item")
    unidade = models.CharField(max_length=20, verbose_name="Unidade")
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    custo_unitario_transferencia = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, help_text="Custo médio de compra no momento da transferência")
    data_movimento = models.DateTimeField(default=timezone.now, db_index=True)
    finalidade = models.CharField(max_length=255, blank=True)
    documento_referencia = models.CharField(max_length=100, blank=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movimentos_estoque_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-data_movimento", "-id")
        verbose_name = "Movimento de estoque"
        verbose_name_plural = "Movimentos de estoque"
        indexes = [
            models.Index(fields=["obra_origem", "tipo", "data_movimento"], name="obr_mov_orig_tipo_dt_idx"),
            models.Index(fields=["obra_destino", "data_movimento"], name="obr_mov_dest_dt_idx"),
            models.Index(fields=["material", "unidade"], name="obr_mov_mat_un_idx"),
        ]

    def clean(self):
        super().clean()
        if self.tipo == self.Tipo.TRANSFERENCIA:
            if not self.obra_destino_id:
                raise ValidationError({"obra_destino": "Informe a obra de destino da transferência."})
            if self.obra_destino_id == self.obra_origem_id:
                raise ValidationError({"obra_destino": "A obra de destino deve ser diferente da origem."})
        elif self.obra_destino_id:
            raise ValidationError({"obra_destino": "Saídas não possuem obra de destino."})

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.descricao_item} · {self.quantidade} {self.unidade}"
