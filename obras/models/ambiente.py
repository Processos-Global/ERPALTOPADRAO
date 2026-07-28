from django.db import models

from .obra import Obra


class Ambiente(models.Model):
    class TipoAmbiente(models.TextChoices):
        INTERNO = "INTERNO", "Interno"
        EXTERNO = "EXTERNO", "Externo"
        TECNICO = "TECNICO", "Técnico"
        COMUM = "COMUM", "Área comum"
        OUTRO = "OUTRO", "Outro"

    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="ambientes",
        verbose_name="Obra",
    )

    nome = models.CharField(
        max_length=150,
        verbose_name="Nome",
    )

    codigo = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Código",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TipoAmbiente.choices,
        default=TipoAmbiente.INTERNO,
        verbose_name="Tipo",
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

    descricao = models.TextField(
        blank=True,
        verbose_name="Descrição",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Ativo",
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
        verbose_name = "Ambiente"
        verbose_name_plural = "Ambientes"
        ordering = [
            "obra",
            "ordem",
            "nome",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "obra",
                    "nome",
                ],
                name="obras_ambiente_obra_nome_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "obra",
                    "ativo",
                ],
                name="obras_ambiente_obra_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "tipo",
                ],
                name="obras_ambiente_tipo_idx",
            ),
        ]

    def __str__(self):
        return f"{self.obra} - {self.nome}"