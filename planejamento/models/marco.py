from django.db import models

from obras.models import Obra

from .atividade import AtividadeCronograma
from .importacao import ImportacaoCronograma


class Marco(models.Model):
    importacao_cronograma = models.ForeignKey(
        ImportacaoCronograma,
        on_delete=models.CASCADE,
        related_name="marcos",
        verbose_name="Importação do cronograma",
    )

    obra = models.ForeignKey(
        Obra,
        on_delete=models.PROTECT,
        related_name="marcos",
        verbose_name="Obra",
    )

    atividade_origem = models.ForeignKey(
        AtividadeCronograma,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marcos_gerados",
        verbose_name="Atividade de origem",
    )

    nome = models.CharField(
        max_length=255,
        verbose_name="Nome",
    )

    semana = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Semana",
    )

    data_prevista = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data prevista",
    )

    data_realizada = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data realizada",
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

    observacoes = models.TextField(
        blank=True,
        verbose_name="Observações",
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
        verbose_name = "Marco"
        verbose_name_plural = "Marcos"
        ordering = [
            "obra",
            "data_prevista",
            "nome",
        ]
        indexes = [
            models.Index(
                fields=[
                    "obra",
                    "concluido",
                ],
                name="planej_marco_obra_conc_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "data_prevista",
                ],
                name="planej_marco_obra_data_idx",
            ),
        ]

    def __str__(self):
        return f"{self.obra} - {self.nome}"