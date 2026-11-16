"""Execução em campo: caminhões, onde o concreto foi aplicado e o que sobrou.

Todo volume entregue precisa ter destino (utilização ou sobra) antes de
finalizar: `obras.services.concretagem.campo.resumo_volume`.
Remoções são lógicas (`ativo=False`) para preservar o histórico.
"""
from django.conf import settings
from django.db import models

# Cores bem distintas para o mapa; depois delas, gera tons pelo índice (ângulo áureo).
PALETA_MAPA = (
    "#2E86AB", "#E4572E", "#4CB944", "#F2A541", "#8E5DB8", "#17BEBB", "#D7263D", "#7A9E3B",
    "#C06C84", "#1B998B", "#F46036", "#5B5F97", "#B8860B", "#2F4858", "#E07A5F", "#3D9970",
    "#A23B72", "#6C8EAD", "#C9A227", "#55286F",
)


def _cor_hsl(indice):
    import colorsys

    h = (indice * 0.618033988749895) % 1
    r, g, b = colorsys.hls_to_rgb(h, 0.48, 0.62)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def proxima_cor(obra_id):
    """Primeira cor da paleta ainda não usada por usos/sobras desta obra."""
    usadas = set(UtilizacaoConcreto.objects.filter(concretagem__obra_id=obra_id).exclude(cor="").values_list("cor", flat=True))
    usadas |= set(SobraConcreto.objects.filter(concretagem__obra_id=obra_id).exclude(cor="").values_list("cor", flat=True))
    for cor in PALETA_MAPA:
        if cor not in usadas:
            return cor
    return _cor_hsl(len(usadas))


class CaminhaoConcretagem(models.Model):
    concretagem = models.ForeignKey(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="caminhoes", verbose_name="Concretagem",
    )
    ordem = models.PositiveSmallIntegerField("Ordem", default=1)
    placa = models.CharField("Placa / identificação", max_length=20, blank=True)
    numero_lacre = models.CharField("Nº do lacre", max_length=50, blank=True)
    numero_nota_fiscal = models.CharField("Nº da nota fiscal", max_length=30, blank=True)
    fck_nota = models.DecimalField("Fck informado na NF (MPa)", max_digits=6, decimal_places=1, null=True, blank=True)
    volume_entregue = models.DecimalField("Volume entregue (m³)", max_digits=7, decimal_places=2)
    horario_chegada = models.TimeField("Chegada à obra", null=True, blank=True)
    inicio_descarga = models.TimeField("Início da descarga", null=True, blank=True)
    termino_descarga = models.TimeField("Término da descarga", null=True, blank=True)
    cps_moldados = models.PositiveSmallIntegerField("CPs moldados", default=0)
    observacoes = models.TextField("Observações", blank=True)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="caminhoes_concretagem_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Caminhão da concretagem"
        verbose_name_plural = "Caminhões da concretagem"
        indexes = [models.Index(fields=["concretagem", "ativo"], name="obras_conc_cam_ativo_idx")]

    def __str__(self):
        return self.rotulo

    @property
    def rotulo(self):
        return f"Caminhão {self.ordem}" + (f" · {self.placa}" if self.placa else "")


class UtilizacaoConcreto(models.Model):
    """Volume aplicado em um local de uso da obra."""

    concretagem = models.ForeignKey(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="utilizacoes", verbose_name="Concretagem",
    )
    caminhao = models.ForeignKey(
        CaminhaoConcretagem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="utilizacoes", verbose_name="Caminhão",
    )
    local = models.ForeignKey(
        "obras.LocalUsoObra", on_delete=models.PROTECT, null=True, blank=True,
        related_name="utilizacoes", verbose_name="Local de uso",
    )
    descricao = models.CharField("Descrição / complemento", max_length=300, blank=True)
    volume_utilizado = models.DecimalField("Volume utilizado (m³)", max_digits=7, decimal_places=2)
    cor = models.CharField("Cor no mapa", max_length=7, blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="utilizacoes_concreto",
    )
    registrado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["registrado_em", "id"]
        verbose_name = "Utilização de concreto"
        verbose_name_plural = "Utilizações de concreto"
        indexes = [models.Index(fields=["concretagem", "ativo"], name="obras_conc_uso_ativo_idx")]

    def __str__(self):
        return f"{self.volume_utilizado} m³ → {self.titulo}"

    def save(self, *args, **kwargs):
        if not self.cor and self.concretagem_id:
            self.cor = proxima_cor(self.concretagem.obra_id)
        super().save(*args, **kwargs)

    @property
    def titulo(self):
        if self.local_id:
            return self.local.descricao_completa + (f" — {self.descricao}" if self.descricao else "")
        return self.descricao or "—"


class SobraConcreto(models.Model):
    class Destino(models.TextChoices):
        CALCADA = "CALCADA", "Utilizado em calçada"
        MURO = "MURO", "Utilizado em muro"
        CONTRAPISO = "CONTRAPISO", "Utilizado em contrapiso"
        AREA_EXTERNA = "AREA_EXTERNA", "Utilizado em área externa"
        OUTRA_ESTRUTURA = "OUTRA_ESTRUTURA", "Utilizado em outra estrutura da obra"
        OUTRA_OBRA = "OUTRA_OBRA", "Enviado para outra obra"
        DESCARTADO = "DESCARTADO", "Descartado"
        DEVOLVIDO = "DEVOLVIDO", "Devolvido à concreteira"
        AGUARDANDO = "AGUARDANDO", "Aguardando definição"
        OUTRO = "OUTRO", "Outro"

    class Situacao(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente de destinação"
        REAPROVEITADA = "REAPROVEITADA", "Reaproveitada"
        PERDIDA = "PERDIDA", "Descartada / devolvida"

    DESTINOS_PERDA = (Destino.DESCARTADO, Destino.DEVOLVIDO)

    concretagem = models.ForeignKey(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="sobras", verbose_name="Concretagem",
    )
    caminhao = models.ForeignKey(
        CaminhaoConcretagem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sobras", verbose_name="Caminhão",
    )
    volume_sobra = models.DecimalField("Volume da sobra (m³)", max_digits=7, decimal_places=2)
    destino = models.CharField("Destino", max_length=20, choices=Destino.choices, default=Destino.AGUARDANDO)
    obra_destino = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sobras_recebidas_concretagem", verbose_name="Obra de destino",
    )
    local_destino = models.ForeignKey(
        "obras.LocalUsoObra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sobras_recebidas", verbose_name="Local de destino",
    )
    descricao_destino = models.CharField("Descrição do destino", max_length=300, blank=True)
    situacao = models.CharField("Situação", max_length=20, choices=Situacao.choices, default=Situacao.PENDENTE)
    cor = models.CharField("Cor no mapa", max_length=7, blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sobras_concreto",
    )
    registrado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["registrado_em", "id"]
        verbose_name = "Sobra de concreto"
        verbose_name_plural = "Sobras de concreto"
        indexes = [models.Index(fields=["concretagem", "situacao"], name="obras_conc_sobra_sit_idx")]

    def __str__(self):
        return f"Sobra {self.volume_sobra} m³ — {self.get_destino_display()}"

    def save(self, *args, **kwargs):
        if self.destino == self.Destino.AGUARDANDO:
            self.situacao = self.Situacao.PENDENTE
        elif self.destino in self.DESTINOS_PERDA:
            self.situacao = self.Situacao.PERDIDA
        else:
            self.situacao = self.Situacao.REAPROVEITADA
        if not self.cor and self.concretagem_id:
            self.cor = proxima_cor(self.concretagem.obra_id)
        super().save(*args, **kwargs)

    @property
    def destino_texto(self):
        if self.destino == self.Destino.OUTRA_OBRA and self.obra_destino_id:
            base = f"Outra obra: {self.obra_destino.nome}"
        elif self.destino == self.Destino.OUTRA_ESTRUTURA and self.local_destino_id:
            base = f"Outra estrutura: {self.local_destino.descricao_completa}"
        else:
            base = self.get_destino_display()
        return base + (f" — {self.descricao_destino}" if self.descricao_destino else "")
