from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .cronograma import AtividadePlanejamento


class InsumoPlanejamento(models.Model):
    class UnidadeMedida(models.TextChoices):
        UN = "UN", "Unidade"
        M = "M", "Metro"
        M2 = "M2", "Metro quadrado"
        M3 = "M3", "Metro cúbico"
        KG = "KG", "Quilograma"
        T = "T", "Tonelada"
        L = "L", "Litro"
        SC = "SC", "Saco"
        CX = "CX", "Caixa"
        PC = "PC", "Peça"
        GL = "GL", "Galão"
        RL = "RL", "Rolo"
        PT = "PT", "Pacote"
        VB = "VB", "Verba"

    nome = models.CharField(max_length=255, unique=True, db_index=True)
    unidade_padrao = models.CharField(
        max_length=10,
        choices=UnidadeMedida.choices,
        blank=True,
    )
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True, db_index=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="insumos_planejamento_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Insumo de planejamento"
        verbose_name_plural = "Insumos de planejamento"

    def __str__(self):
        return self.nome


class SuprimentoAtividade(models.Model):
    atividade = models.ForeignKey(
        AtividadePlanejamento,
        on_delete=models.CASCADE,
        related_name="suprimentos",
    )
    insumo = models.ForeignKey(
        InsumoPlanejamento,
        on_delete=models.PROTECT,
        related_name="suprimentos_atividades",
    )
    quantidade = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unidade_medida = models.CharField(
        max_length=10,
        choices=InsumoPlanejamento.UnidadeMedida.choices,
    )
    valor_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    data_limite_compra = models.DateField(null=True, blank=True, db_index=True)
    observacao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True, db_index=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suprimentos_atividade_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = (
            "atividade_id",
            "data_limite_compra",
            "insumo__nome",
            "id",
        )
        verbose_name = "Suprimento de atividade"
        verbose_name_plural = "Suprimentos de atividades"
        indexes = [
            models.Index(
                fields=["atividade", "ativo"],
                name="plan_sup_ativ_ativo_idx",
            ),
            models.Index(
                fields=["atividade", "data_limite_compra"],
                name="plan_sup_ativ_data_idx",
            ),
            models.Index(
                fields=["insumo", "ativo"],
                name="plan_sup_ins_ativo_idx",
            ),
        ]

    @property
    def valor_total(self) -> Decimal:
        return (
            (self.quantidade or Decimal("0"))
            * (self.valor_unitario or Decimal("0"))
        )

    def __str__(self):
        return f"{self.atividade.nome_tarefa or self.atividade_id} - {self.insumo.nome}"
