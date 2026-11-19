from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class ReservaEstoqueCompra(models.Model):
    class Status(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        CONSUMIDA = "CONSUMIDA", "Consumida"
        LIBERADA = "LIBERADA", "Liberada"

    necessidade = models.OneToOneField(
        "compras.NecessidadeCompra", on_delete=models.PROTECT,
        related_name="reserva_estoque",
    )
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="reservas_estoque_compra")
    material = models.ForeignKey("cadastros.Material", on_delete=models.PROTECT, related_name="reservas_estoque_compra")
    unidade = models.CharField(max_length=20)
    especificacao = models.TextField(blank=True)
    quantidade_original = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))])
    quantidade_disponivel = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVA, db_index=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="reservas_estoque_criadas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["obra", "material", "status"], name="comp_res_obra_mat_st_idx")]
