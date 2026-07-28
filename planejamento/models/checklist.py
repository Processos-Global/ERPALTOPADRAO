from django.db import models

from obras.models import Obra

from .atividade import AtividadeCronograma
from .importacao import ImportacaoCronograma


class ChecklistCronograma(models.Model):
    class Tipo(models.TextChoices):
        HABITESE = "HABITESE", "Habite-se"
        CEF = "CEF", "CEF"
        OUTRO = "OUTRO", "Outro"

    importacao_cronograma = models.ForeignKey(
        ImportacaoCronograma,
        on_delete=models.CASCADE,
        related_name="checklists",
        verbose_name="Importação do cronograma",
    )

    obra = models.ForeignKey(
        Obra,
        on_delete=models.PROTECT,
        related_name="checklists_cronograma",
        verbose_name="Obra",
    )

    atividade_origem = models.ForeignKey(
        AtividadeCronograma,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklists_gerados",
        verbose_name="Atividade de origem",
    )

    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        verbose_name="Tipo",
    )

    nome = models.CharField(
        max_length=255,
        verbose_name="Nome",
    )

    local = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Local",
    )

    semana = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Semana",
    )

    valor_original = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Valor original",
    )

    percentual_concluido = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="% concluído",
    )

    concluido = models.BooleanField(
        default=False,
        verbose_name="Concluído",
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
        verbose_name = "Checklist do cronograma"
        verbose_name_plural = "Checklists do cronograma"
        ordering = [
            "obra",
            "tipo",
            "semana",
            "nome",
        ]
        indexes = [
            models.Index(
                fields=[
                    "obra",
                    "tipo",
                ],
                name="planej_check_obra_tipo_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "concluido",
                ],
                name="planej_check_obra_conc_idx",
            ),
        ]

    def __str__(self):
        return f"{self.obra} - {self.get_tipo_display()} - {self.nome}"