from django.db import models

from obras.models import Obra

from .disciplina import Disciplina
from .importacao import ImportacaoCronograma


class AtividadeCronograma(models.Model):
    importacao_cronograma = models.ForeignKey(
        ImportacaoCronograma,
        on_delete=models.CASCADE,
        related_name="atividades",
        verbose_name="Importação do cronograma",
    )

    obra = models.ForeignKey(
        Obra,
        on_delete=models.PROTECT,
        related_name="atividades_cronograma",
        verbose_name="Obra",
    )

    disciplina = models.ForeignKey(
        Disciplina,
        on_delete=models.PROTECT,
        related_name="atividades",
        null=True,
        blank=True,
        verbose_name="Disciplina",
    )

    nome_projeto_original = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        verbose_name="Nome original do projeto",
    )

    tipo_empreendimento = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Prédio ou casa",
    )

    quantidade_unidades = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantidade de unidades",
    )

    semana = models.PositiveIntegerField(
        db_index=True,
        verbose_name="Semana",
    )

    data_atualizacao = models.DateField(
        db_index=True,
        verbose_name="Data de atualização",
    )

    local_tarefa = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Local da tarefa",
    )

    nome_tarefa = models.CharField(
        max_length=500,
        verbose_name="Nome da tarefa",
    )

    inicio_real = models.DateField(
        null=True,
        blank=True,
        verbose_name="Início real",
    )

    duracao_real = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Duração real",
    )

    termino_real = models.DateField(
        null=True,
        blank=True,
        verbose_name="Término real",
    )

    inicio_base = models.DateField(
        null=True,
        blank=True,
        verbose_name="Início base",
    )

    duracao_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Duração base",
    )

    termino_base = models.DateField(
        null=True,
        blank=True,
        verbose_name="Término base",
    )

    percentual_concluida = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="% concluída",
    )

    percentual_previsto_tarefa = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="% previsto da tarefa",
    )

    checklist_habitese = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Checklist Habite-se",
    )

    checklist_cef = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Checklist CEF",
    )

    responsavel = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Responsável",
    )

    peso = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Peso",
    )

    percentual_executado = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="% executado",
    )

    percentual_previsto = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="% previsto",
    )

    inicio_semana = models.DateField(
        null=True,
        blank=True,
        verbose_name="Início da semana",
    )

    semana_anterior = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Semana anterior",
    )

    semana_seguinte = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Semana seguinte",
    )

    linha_origem = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Linha de origem",
    )

    dados_originais = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dados originais",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    class Meta:
        verbose_name = "Atividade do cronograma"
        verbose_name_plural = "Atividades do cronograma"
        ordering = [
            "obra",
            "semana",
            "disciplina",
            "nome_tarefa",
        ]
        indexes = [
            models.Index(
                fields=[
                    "importacao_cronograma",
                    "obra",
                ],
                name="planej_ativ_import_obra_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "semana",
                ],
                name="planej_ativ_obra_sem_idx",
            ),
            models.Index(
                fields=[
                    "obra",
                    "data_atualizacao",
                ],
                name="planej_ativ_obra_data_idx",
            ),
            models.Index(
                fields=[
                    "disciplina",
                    "semana",
                ],
                name="planej_ativ_disc_sem_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.obra} - "
            f"Semana {self.semana} - "
            f"{self.nome_tarefa}"
        )