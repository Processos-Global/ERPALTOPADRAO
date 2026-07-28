from django.db import models

from integracoes.models import Importacao
from obras.models import Obra


class ImportacaoCronograma(models.Model):
    importacao = models.OneToOneField(
        Importacao,
        on_delete=models.CASCADE,
        related_name="cronograma_obra",
        verbose_name="Importação",
    )

    obra = models.ForeignKey(
        Obra,
        on_delete=models.PROTECT,
        related_name="importacoes_cronograma",
        null=True,
        blank=True,
        verbose_name="Obra",
    )

    data_referencia = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de referência",
    )

    semana_inicial = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Semana inicial",
    )

    semana_final = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Semana final",
    )

    total_atividades = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Total de atividades",
    )

    ativa = models.BooleanField(
        default=False,
        verbose_name="Importação ativa",
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
        verbose_name = "Importação de cronograma"
        verbose_name_plural = "Importações de cronograma"
        ordering = [
            "-data_referencia",
            "-criado_em",
        ]
        indexes = [
            models.Index(
                fields=[
                    "obra",
                    "ativa",
                ],
                name="planej_import_obra_ativa_idx",
            ),
            models.Index(
                fields=[
                    "data_referencia",
                ],
                name="planej_import_data_idx",
            ),
        ]

    def __str__(self):
        obra = self.obra.nome if self.obra else "Sem obra"
        data = (
            self.data_referencia.strftime("%d/%m/%Y")
            if self.data_referencia
            else "Sem data"
        )

        return f"{obra} - {data}"