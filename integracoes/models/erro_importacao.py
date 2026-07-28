from django.db import models

from .arquivo_importado import ArquivoImportado
from .importacao import Importacao


class ErroImportacao(models.Model):
    class Nivel(models.TextChoices):
        AVISO = "AVISO", "Aviso"
        ERRO = "ERRO", "Erro"
        CRITICO = "CRITICO", "Crítico"

    importacao = models.ForeignKey(
        Importacao,
        on_delete=models.CASCADE,
        related_name="erros",
        verbose_name="Importação",
    )

    arquivo = models.ForeignKey(
        ArquivoImportado,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erros",
        verbose_name="Arquivo",
    )

    nivel = models.CharField(
        max_length=20,
        choices=Nivel.choices,
        default=Nivel.ERRO,
        verbose_name="Nível",
    )

    linha = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Linha",
    )

    coluna = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Coluna",
    )

    codigo = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Código",
    )

    mensagem = models.TextField(
        verbose_name="Mensagem",
    )

    valor_original = models.TextField(
        blank=True,
        verbose_name="Valor original",
    )

    dados_linha = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dados da linha",
    )

    traceback = models.TextField(
        blank=True,
        verbose_name="Traceback",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    class Meta:
        verbose_name = "Erro de importação"
        verbose_name_plural = "Erros de importação"
        ordering = [
            "-criado_em",
        ]
        indexes = [
            models.Index(
                fields=[
                    "importacao",
                    "nivel",
                ],
                name="erro_importacao_nivel_idx",
            ),
            models.Index(
                fields=[
                    "arquivo",
                    "linha",
                ],
                name="erro_arquivo_linha_idx",
            ),
        ]

    def __str__(self):
        localizacao = ""

        if self.linha:
            localizacao = f" - linha {self.linha}"

        return f"{self.get_nivel_display()}{localizacao}: {self.mensagem[:80]}"