"""Ficha de Moldagem de CP's (modelo SENAI): cabeçalho por concretagem e uma série por caminhão.

Horários de chegada/descarga, NF e quantidade de CPs vêm do caminhão
(fonte única); a série guarda só o que é próprio da moldagem.
"""
from django.conf import settings
from django.db import models


class FichaMoldagem(models.Model):
    class Tempo(models.TextChoices):
        SOL = "SOL", "Sol"
        CHUVA = "CHUVA", "Chuva"

    class LocalMoldagem(models.TextChoices):
        LABORATORIO = "LABORATORIO", "Laboratório"
        OBRA = "OBRA", "Obra"

    class Autorizacao(models.TextChoices):
        INICIO_DESCARGA = "INICIO_DESCARGA", "Início da descarga"
        TERCO_MEDIO = "TERCO_MEDIO", "Terço médio da descarga"

    concretagem = models.OneToOneField(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="ficha_moldagem",
    )
    empresa = models.CharField("Empresa", max_length=200, blank=True)
    referencia = models.CharField("Ref.", max_length=100, blank=True)
    central_concreto = models.CharField("Central de concreto", max_length=200, blank=True)
    abatimento = models.CharField("Abatimento (mm)", max_length=20, blank=True)
    abatimento_tolerancia = models.CharField("Tolerância abatimento (± mm)", max_length=20, blank=True)
    slump_flow = models.CharField("Slump flow (mm)", max_length=20, blank=True)
    slump_flow_tolerancia = models.CharField("Tolerância slump flow (± mm)", max_length=20, blank=True)
    tempo = models.CharField("Tempo", max_length=10, choices=Tempo.choices, blank=True)
    data = models.DateField("Data da concretagem", null=True, blank=True)
    local_moldagem = models.CharField("Moldagem realizada em", max_length=15, choices=LocalMoldagem.choices, blank=True)
    moldador = models.CharField("Moldador", max_length=200, blank=True)
    responsavel_conferencia = models.CharField("Responsável pela conferência", max_length=200, blank=True)
    observacoes = models.CharField("Observações", max_length=200, blank=True)
    idade_ruptura = models.CharField("Idade de ruptura (dias)", max_length=50, blank=True, default="7, 14 e 28")
    hora_entrada = models.TimeField("Hora de entrada", null=True, blank=True)
    hora_saida = models.TimeField("Hora de saída", null=True, blank=True)
    autorizacao = models.CharField("Moldagem autorizada a partir do", max_length=20, choices=Autorizacao.choices, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ficha de moldagem"
        verbose_name_plural = "Fichas de moldagem"

    def __str__(self):
        return f"Ficha de moldagem {self.concretagem}"


class SerieMoldagem(models.Model):
    class LocalAplicacao(models.TextChoices):
        ESTACA = "ESTACA", "Estaca"
        TUBULAO = "TUBULAO", "Tubulão"
        BLOCO = "BLOCO", "Bloco"
        VIGA_BALDRAME = "VIGA_BALDRAME", "Viga baldrame"
        RADIER = "RADIER", "Radier"
        PILAR = "PILAR", "Pilar"
        VIGA = "VIGA", "Viga"
        PAREDE = "PAREDE", "Parede"
        CONTENCAO = "CONTENCAO", "Contenção"
        CORTINA = "CORTINA", "Cortina"
        ESCADA = "ESCADA", "Escada"
        PISO = "PISO", "Piso"
        LAJE = "LAJE", "Laje"
        SAPATA = "SAPATA", "Sapata"
        RAMPA = "RAMPA", "Rampa"

    caminhao = models.OneToOneField(
        "obras.CaminhaoConcretagem", on_delete=models.CASCADE, related_name="serie_moldagem",
    )
    abatimento_medido = models.CharField("Abatimento medido (mm)", max_length=20, blank=True)
    slump_flow = models.CharField("Slump flow (mm)", max_length=20, blank=True)
    slump_flow_tolerancia = models.CharField("Tolerância slump flow (± mm)", max_length=20, blank=True)
    hora_moldagem = models.TimeField("Hora da moldagem", null=True, blank=True)
    inicio_mistura = models.TimeField("Início da mistura", null=True, blank=True)
    concreto_aplicado_m3 = models.DecimalField("Concreto aplicado (m³)", max_digits=7, decimal_places=2, null=True, blank=True)
    local_aplicacao = models.CharField("Local de aplicação", max_length=20, choices=LocalAplicacao.choices, blank=True)
    junta = models.CharField("Junta", max_length=50, blank=True)
    pavimento = models.CharField("Pavimento", max_length=50, blank=True)
    torre = models.CharField("Torre", max_length=50, blank=True)
    identificacao_amostra = models.TextField("Identificação da amostra", blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="series_moldagem_atualizadas",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Série de moldagem"
        verbose_name_plural = "Séries de moldagem"

    def __str__(self):
        return f"Série {self.caminhao.ordem}"

    @property
    def numero_serie(self):
        return self.caminhao.ordem

    @property
    def slump_flow_valor(self):
        """Informado na série ou, por padrão, o slump flow da solicitação."""
        return self.slump_flow or self.caminhao.concretagem.slump

    @property
    def slump_flow_tolerancia_valor(self):
        return self.slump_flow_tolerancia or self.caminhao.concretagem.slump_tolerancia

    @property
    def concreto_aplicado(self):
        """Valor informado na série ou, por padrão, o volume entregue pelo caminhão."""
        if self.concreto_aplicado_m3 is not None:
            return self.concreto_aplicado_m3
        return self.caminhao.volume_entregue

    def pendencias(self):
        """Campos essenciais para fechar a execução (mesma regra do sistema anterior)."""
        cam = self.caminhao
        faltando = []
        if not cam.cps_moldados:
            faltando.append("quantidade de CPs")
        if not self.inicio_mistura:
            faltando.append("início da mistura")
        if not cam.horario_chegada:
            faltando.append("chegada")
        if not cam.inicio_descarga:
            faltando.append("início da descarga")
        if not cam.termino_descarga:
            faltando.append("término da descarga")
        if not self.concreto_aplicado:
            faltando.append("concreto aplicado")
        if not self.local_aplicacao:
            faltando.append("local de aplicação")
        return faltando
