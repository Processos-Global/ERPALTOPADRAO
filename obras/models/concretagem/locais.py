"""Cadastros de apoio da concretagem, todos por obra ou reutilizáveis.

`LocalUsoObra` substitui a importação de EAP do sistema anterior: cada obra
mantém sua própria lista de locais/estruturas que recebem concreto (lajes,
pilares, piscina, muros...). É a base dos itens planejados e, nas próximas
etapas, da utilização e do mapa de concretagem.
"""
from django.conf import settings
from django.db import models


class LocalUsoObra(models.Model):
    class Tipo(models.TextChoices):
        ESTACA = "ESTACA", "Estaca"
        FUNDACAO = "FUNDACAO", "Fundação / bloco"
        BALDRAME = "BALDRAME", "Baldrame"
        PILAR = "PILAR", "Pilar"
        VIGA = "VIGA", "Viga"
        LAJE = "LAJE", "Laje"
        ESCADA = "ESCADA", "Escada"
        PAREDE = "PAREDE", "Parede / cortina"
        MURO = "MURO", "Muro"
        PISCINA = "PISCINA", "Piscina"
        RESERVATORIO = "RESERVATORIO", "Reservatório"
        CONTRAPISO = "CONTRAPISO", "Contrapiso / piso"
        CALCADA = "CALCADA", "Calçada"
        AREA_EXTERNA = "AREA_EXTERNA", "Área externa"
        OUTRO = "OUTRO", "Outro"

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE,
        related_name="locais_concretagem", verbose_name="Obra",
    )
    nome = models.CharField("Nome do local", max_length=160)
    tipo = models.CharField("Tipo", max_length=20, choices=Tipo.choices, default=Tipo.OUTRO)
    bloco = models.CharField("Bloco", max_length=60, blank=True)
    pavimento = models.CharField("Pavimento", max_length=80, blank=True)
    volume_estimado = models.DecimalField(
        "Volume estimado (m³)", max_digits=8, decimal_places=2, null=True, blank=True,
    )
    ordem = models.PositiveIntegerField("Ordem", default=0)
    ativo = models.BooleanField("Ativo", default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="locais_concretagem_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "Local de uso da concretagem"
        verbose_name_plural = "Locais de uso da concretagem"
        constraints = [
            models.UniqueConstraint(fields=["obra", "nome"], name="obras_conc_local_obra_nome_uniq"),
        ]
        indexes = [models.Index(fields=["obra", "ativo"], name="obras_conc_local_ativo_idx")]

    def __str__(self):
        return self.descricao_completa

    @property
    def descricao_completa(self):
        partes = [self.nome]
        if self.bloco:
            partes.append(f"Bloco {self.bloco}")
        if self.pavimento:
            partes.append(self.pavimento)
        return " · ".join(partes)


class EnderecoEntregaSalvo(models.Model):
    """Endereço de entrega reutilizável; é copiado (não referenciado) na concretagem."""

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, null=True, blank=True,
        related_name="enderecos_entrega_concretagem", verbose_name="Obra",
    )
    nome = models.CharField("Identificação", max_length=160)
    endereco = models.CharField("Endereço", max_length=500)
    link_maps = models.URLField("Link Google Maps", max_length=500, blank=True)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enderecos_concretagem_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Endereço de entrega salvo"
        verbose_name_plural = "Endereços de entrega salvos"

    def __str__(self):
        return self.nome


class ContatoEmailConcreteira(models.Model):
    """E-mails extras que recebem a solicitação, além do e-mail do fornecedor."""

    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor", on_delete=models.CASCADE,
        related_name="contatos_concretagem", verbose_name="Concreteira",
    )
    nome = models.CharField("Nome", max_length=150, blank=True)
    email = models.EmailField("E-mail")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome", "email"]
        verbose_name = "Contato de e-mail da concreteira"
        verbose_name_plural = "Contatos de e-mail das concreteiras"
        constraints = [
            models.UniqueConstraint(fields=["fornecedor", "email"], name="obras_conc_contato_forn_email_uniq"),
        ]

    def __str__(self):
        return f"{self.nome} <{self.email}>" if self.nome else self.email
