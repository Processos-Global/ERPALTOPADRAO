from django.db import models

from .obra import Obra


class Unidade(models.Model):
    class TipoUnidade(models.TextChoices):
        CASA = "CASA", "Casa"
        APARTAMENTO = "APARTAMENTO", "Apartamento"
        BLOCO = "BLOCO", "Bloco"
        TORRE = "TORRE", "Torre"
        SETOR = "SETOR", "Setor"
        OUTRO = "OUTRO", "Outro"

    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="unidades",
        verbose_name="Obra",
    )

    codigo = models.CharField(
        max_length=60,
        verbose_name="Código",
    )

    nome = models.CharField(
        max_length=150,
        verbose_name="Nome",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TipoUnidade.choices,
        default=TipoUnidade.CASA,
        verbose_name="Tipo",
    )

    bloco = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Bloco",
    )

    pavimento = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Pavimento",
    )

    area = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Área",
    )

    ordem = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem",
    )

    ativa = models.BooleanField(
        default=True,
        verbose_name="Ativa",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    class Meta:
        verbose_name = "Unidade"
        verbose_name_plural = "Unidades"
        ordering = [
            "obra",
            "ordem",
            "codigo",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "obra",
                    "codigo",
                ],
                name="obras_unidade_obra_codigo_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "obra",
                    "ativa",
                ],
                name="obras_unidade_obra_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "tipo",
                ],
                name="obras_unidade_tipo_idx",
            ),
        ]

    def __str__(self):
        return f"{self.obra} - {self.nome}"