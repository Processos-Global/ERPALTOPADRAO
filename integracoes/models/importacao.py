from django.conf import settings
from django.db import models


class Importacao(models.Model):
    class Tipo(models.TextChoices):
        CRONOGRAMA_OBRA = (
            "CRONOGRAMA_OBRA",
            "Cronograma de obra",
        )
        CRONOGRAMA_SUPRIMENTOS = (
            "CRONOGRAMA_SUPRIMENTOS",
            "Cronograma de suprimentos",
        )
        OUTRO = (
            "OUTRO",
            "Outro",
        )

    class Origem(models.TextChoices):
        GOOGLE_DRIVE = (
            "GOOGLE_DRIVE",
            "Google Drive",
        )
        UPLOAD_MANUAL = (
            "UPLOAD_MANUAL",
            "Upload manual",
        )
        DIRETORIO_LOCAL = (
            "DIRETORIO_LOCAL",
            "Diretório local",
        )

    class Status(models.TextChoices):
        PENDENTE = (
            "PENDENTE",
            "Pendente",
        )
        PROCESSANDO = (
            "PROCESSANDO",
            "Processando",
        )
        CONCLUIDA = (
            "CONCLUIDA",
            "Concluída",
        )
        CONCLUIDA_COM_ERROS = (
            "CONCLUIDA_COM_ERROS",
            "Concluída com erros",
        )
        FALHOU = (
            "FALHOU",
            "Falhou",
        )
        CANCELADA = (
            "CANCELADA",
            "Cancelada",
        )

    tipo = models.CharField(
        max_length=40,
        choices=Tipo.choices,
        verbose_name="Tipo",
    )

    origem = models.CharField(
        max_length=30,
        choices=Origem.choices,
        default=Origem.GOOGLE_DRIVE,
        verbose_name="Origem",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDENTE,
        verbose_name="Status",
    )

    iniciado_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Iniciado em",
    )

    finalizado_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Finalizado em",
    )

    total_linhas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Total de linhas",
    )

    total_processadas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Linhas processadas",
    )

    total_inseridas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Linhas inseridas",
    )

    total_atualizadas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Linhas atualizadas",
    )

    total_ignoradas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Linhas ignoradas",
    )

    total_erros = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Total de erros",
    )

    mensagem = models.TextField(
        blank=True,
        verbose_name="Mensagem",
    )

    detalhes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Detalhes",
    )

    executada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_executadas",
        verbose_name="Executada por",
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
        verbose_name = "Importação"
        verbose_name_plural = "Importações"
        ordering = [
            "-criado_em",
        ]
        indexes = [
            models.Index(
                fields=[
                    "tipo",
                    "status",
                ],
                name="integracao_tipo_status_idx",
            ),
            models.Index(
                fields=[
                    "criado_em",
                ],
                name="integracao_criado_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} "
            f"- {self.get_status_display()} "
            f"- {self.criado_em:%d/%m/%Y %H:%M}"
        )