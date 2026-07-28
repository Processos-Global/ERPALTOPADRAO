from django.db import models

from .importacao import Importacao


class ArquivoImportado(models.Model):
    class TipoArquivo(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel XLSX"
        XLS = "XLS", "Excel XLS"
        GOOGLE_SHEETS = (
            "GOOGLE_SHEETS",
            "Google Sheets",
        )
        OUTRO = "OUTRO", "Outro"

    importacao = models.ForeignKey(
        Importacao,
        on_delete=models.CASCADE,
        related_name="arquivos",
        verbose_name="Importação",
    )

    nome = models.CharField(
        max_length=255,
        verbose_name="Nome do arquivo",
    )

    tipo_arquivo = models.CharField(
        max_length=20,
        choices=TipoArquivo.choices,
        default=TipoArquivo.OUTRO,
        verbose_name="Tipo do arquivo",
    )

    google_drive_file_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        verbose_name="ID do arquivo no Google Drive",
    )

    mime_type = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="MIME type",
    )

    caminho_temporario = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Caminho temporário",
    )

    tamanho_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Tamanho em bytes",
    )

    hash_arquivo = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        verbose_name="Hash do arquivo",
    )

    data_modificacao_drive = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Modificado no Drive em",
    )

    data_referencia = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de referência",
    )

    aba = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Aba",
    )

    total_linhas = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Total de linhas",
    )

    processado = models.BooleanField(
        default=False,
        verbose_name="Processado",
    )

    metadados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadados",
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
        verbose_name = "Arquivo importado"
        verbose_name_plural = "Arquivos importados"
        ordering = [
            "-criado_em",
        ]
        indexes = [
            models.Index(
                fields=[
                    "google_drive_file_id",
                    "data_modificacao_drive",
                ],
                name="arquivo_drive_modificacao_idx",
            ),
            models.Index(
                fields=[
                    "hash_arquivo",
                ],
                name="arquivo_hash_idx",
            ),
        ]

    def __str__(self):
        if self.aba:
            return f"{self.nome} - {self.aba}"

        return self.nome