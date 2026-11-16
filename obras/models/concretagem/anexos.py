"""Anexos da concretagem. O destino final é o Google Drive.

O arquivo fica no armazenamento privado do servidor apenas enquanto não
chegou ao Drive (`arquivo` preenchido + `status=PENDENTE`). Depois do envio
o arquivo local é apagado e só ficam `drive_id`/`drive_url`.
"""
from django.conf import settings
from django.db import models

from core.storage import private_media_storage


class AnexoConcretagem(models.Model):
    class Etapa(models.TextChoices):
        NOTA_FISCAL = "NOTA_FISCAL", "Nota fiscal do caminhão"
        ETIQUETA_CP = "ETIQUETA_CP", "Etiqueta dos CPs"
        FICHA_MOLDAGEM = "FICHA_MOLDAGEM", "Ficha de moldagem (PDF)"
        LAUDO = "LAUDO", "Laudo de resistência"
        CHEGADA = "CHEGADA", "Chegada do concreto"
        DESCARGA = "DESCARGA", "Descarga / lançamento"
        ADENSAMENTO = "ADENSAMENTO", "Adensamento"
        ACABAMENTO = "ACABAMENTO", "Acabamento"
        CURA = "CURA", "Cura"
        OCORRENCIA = "OCORRENCIA", "Ocorrência"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Aguardando envio ao Drive"
        NO_DRIVE = "NO_DRIVE", "No Drive"

    # Etapas que podem ser anexadas livremente na aba de fotos.
    ETAPAS_FOTOS = (
        Etapa.CHEGADA, Etapa.DESCARGA, Etapa.ADENSAMENTO, Etapa.ACABAMENTO,
        Etapa.CURA, Etapa.OCORRENCIA, Etapa.OUTRO,
    )

    concretagem = models.ForeignKey(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="anexos", verbose_name="Concretagem",
    )
    etapa = models.CharField("Etapa", max_length=20, choices=Etapa.choices)
    caminhao = models.ForeignKey(
        "obras.CaminhaoConcretagem", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="anexos", verbose_name="Caminhão",
    )
    laudo = models.ForeignKey(
        "obras.LaudoConcretagem", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="anexos", verbose_name="Laudo",
    )
    nome_original = models.CharField("Arquivo", max_length=255)
    tipo_conteudo = models.CharField(max_length=100, blank=True)
    tamanho = models.PositiveIntegerField(default=0)
    descricao = models.CharField("Descrição", max_length=300, blank=True)
    arquivo = models.FileField(
        "Arquivo temporário", storage=private_media_storage,
        upload_to="concretagem/temporarios/%Y/%m/", blank=True,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    drive_id = models.CharField(max_length=200, blank=True)
    drive_url = models.URLField(max_length=500, blank=True)
    ultimo_erro = models.CharField(max_length=300, blank=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    enviando_em = models.DateTimeField(
        null=True, blank=True,
        help_text="Marca do envio em andamento (evita mandar o mesmo arquivo duas vezes).",
    )
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="anexos_concretagem",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Anexo da concretagem"
        verbose_name_plural = "Anexos da concretagem"
        indexes = [
            models.Index(fields=["concretagem", "etapa", "ativo"], name="obras_conc_anexo_etapa_idx"),
            models.Index(fields=["status", "ativo"], name="obras_conc_anexo_status_idx"),
        ]

    def __str__(self):
        return f"{self.get_etapa_display()} — {self.nome_original}"

    @property
    def eh_imagem(self):
        return (self.tipo_conteudo or "").startswith("image/")

    @property
    def so_na_ficha(self):
        """Etiquetas dos CPs não vão ao Drive: ficam no sistema e entram na página 2 da ficha."""
        return self.etapa == self.Etapa.ETIQUETA_CP and not self.drive_id

    @property
    def no_drive(self):
        return self.status == self.Status.NO_DRIVE

    @property
    def situacao_drive(self):
        """Texto curto para a tela: No Drive / Enviando… / Falhou."""
        if self.no_drive:
            return "No Drive"
        if self.so_na_ficha:
            return "Na ficha"
        from obras.services.concretagem.drive import drive_habilitado

        if not drive_habilitado():
            return "Drive desligado"
        if self.ultimo_erro and not self.enviando_em:
            return "Falhou"
        return "Enviando…"

    @property
    def rotulo_origem(self):
        if self.caminhao_id:
            return self.caminhao.rotulo
        if self.laudo_id:
            return f"Laudo {self.laudo.idade_dias} dias"
        return ""
