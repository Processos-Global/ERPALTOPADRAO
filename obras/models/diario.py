from django.conf import settings
from django.db import models


class DiarioObra(models.Model):
    class Clima(models.TextChoices):
        ENSOLARADO = "ENSOLARADO", "Ensolarado"
        PARCIALMENTE_NUBLADO = "PARCIALMENTE_NUBLADO", "Parcialmente nublado"
        NUBLADO = "NUBLADO", "Nublado"
        CHUVA_LEVE = "CHUVA_LEVE", "Chuva leve"
        CHUVA_FORTE = "CHUVA_FORTE", "Chuva forte"
        OUTRO = "OUTRO", "Outro"

    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="diarios")
    data = models.DateField(db_index=True)
    clima = models.CharField(max_length=30, choices=Clima.choices, blank=True)
    efetivo = models.PositiveIntegerField(null=True, blank=True, verbose_name="Efetivo no dia")
    servicos_executados = models.TextField(verbose_name="Serviços executados")
    equipe_presente = models.TextField(blank=True, verbose_name="Equipe / terceiros presentes")
    ocorrencias = models.TextField(blank=True, verbose_name="Ocorrências / impedimentos")
    observacoes = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="diarios_obra_registrados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-data", "-id")
        verbose_name = "Diário de obra"
        verbose_name_plural = "Diários de obra"
        constraints = [
            models.UniqueConstraint(fields=["obra", "data"], name="obras_diario_obra_data_uniq"),
        ]
        indexes = [
            models.Index(fields=["obra", "data"], name="obras_diario_obra_dt_idx"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.data:%d/%m/%Y}"
