"""Mapa de concretagem: grade por local de uso, pintada com os usos/sobras de concreto.

- `FormatoDesenho`: contorno reutilizável entre obras (células fora da planta).
- `SolicitacaoFormato`: proposta de criação/edição de formato feita por quem
  não é gerente; vira formato só quando o gerente aprova.
- `MapaLocal`: tamanho da grade de um local de uso e o formato aplicado.
- `CelulaMapa`: célula pintada, ligada a um uso ou a uma sobra.
"""
from django.conf import settings
from django.db import models

MAX_DIMENSAO = 60


def _normalizar_celulas(celulas, linhas, colunas):
    """Lista ordenada e sem repetição de [linha, coluna] (1-based) dentro da grade."""
    vistas = set()
    for item in celulas or []:
        try:
            linha, coluna = int(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 1 <= linha <= linhas and 1 <= coluna <= colunas:
            vistas.add((linha, coluna))
    return [list(c) for c in sorted(vistas)]


class FormatoDesenho(models.Model):
    nome = models.CharField("Nome", max_length=120, unique=True)
    obra_origem = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="formatos_desenho", verbose_name="Obra de origem",
    )
    linhas = models.PositiveSmallIntegerField("Linhas")
    colunas = models.PositiveSmallIntegerField("Colunas")
    celulas_fora = models.JSONField("Células fora do contorno", default=list, blank=True)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="formatos_desenho_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Formato de desenho"
        verbose_name_plural = "Formatos de desenho"

    def __str__(self):
        return f"{self.nome} ({self.linhas}×{self.colunas})"

    def save(self, *args, **kwargs):
        self.celulas_fora = _normalizar_celulas(self.celulas_fora, self.linhas, self.colunas)
        super().save(*args, **kwargs)


class SolicitacaoFormato(models.Model):
    class Tipo(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        EDICAO = "EDICAO", "Edição"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Aguardando aprovação"
        CORRECAO = "CORRECAO", "Devolvida para correção"
        APROVADA = "APROVADA", "Aprovada"
        REJEITADA = "REJEITADA", "Rejeitada"

    tipo = models.CharField("Tipo", max_length=10, choices=Tipo.choices)
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.PENDENTE)
    formato = models.ForeignKey(
        FormatoDesenho, on_delete=models.CASCADE, null=True, blank=True,
        related_name="solicitacoes", verbose_name="Formato",
    )
    nome = models.CharField("Nome", max_length=120)
    obra_origem = models.ForeignKey(
        "obras.Obra", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    linhas = models.PositiveSmallIntegerField("Linhas")
    colunas = models.PositiveSmallIntegerField("Colunas")
    celulas_fora = models.JSONField("Células fora do contorno", default=list, blank=True)
    motivo = models.TextField("Motivo da devolução/rejeição", blank=True)
    solicitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitacoes_formato",
    )
    solicitado_em = models.DateTimeField(auto_now_add=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitacoes_formato_revisadas",
    )
    revisado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-solicitado_em"]
        verbose_name = "Solicitação de formato"
        verbose_name_plural = "Solicitações de formato"
        indexes = [models.Index(fields=["status"], name="obras_conc_solform_st_idx")]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.nome} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        self.celulas_fora = _normalizar_celulas(self.celulas_fora, self.linhas, self.colunas)
        super().save(*args, **kwargs)


class DestinatarioEmailFormato(models.Model):
    """Quem recebe o e-mail de "formato aguardando aprovação"."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="destinatario_formato_concretagem",
    )
    adicionado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    adicionado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Destinatário do e-mail de formatos"
        verbose_name_plural = "Destinatários do e-mail de formatos"

    def __str__(self):
        return self.usuario.get_full_name() or self.usuario.username


class MapaLocal(models.Model):
    local = models.OneToOneField("obras.LocalUsoObra", on_delete=models.CASCADE, related_name="mapa")
    linhas = models.PositiveSmallIntegerField("Linhas", default=10)
    colunas = models.PositiveSmallIntegerField("Colunas", default=10)
    formato = models.ForeignKey(
        FormatoDesenho, on_delete=models.PROTECT, null=True, blank=True,
        related_name="mapas", verbose_name="Formato aplicado",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mapa do local"
        verbose_name_plural = "Mapas dos locais"

    def __str__(self):
        return f"Mapa {self.local} ({self.linhas}×{self.colunas})"

    @property
    def celulas_fora(self):
        """Contorno vem do formato (se o formato mudar, o mapa acompanha)."""
        if self.formato_id and self.formato.linhas == self.linhas and self.formato.colunas == self.colunas:
            return self.formato.celulas_fora
        return []


class CelulaMapa(models.Model):
    mapa = models.ForeignKey(MapaLocal, on_delete=models.CASCADE, related_name="celulas")
    linha = models.PositiveSmallIntegerField()
    coluna = models.PositiveSmallIntegerField()
    utilizacao = models.ForeignKey(
        "obras.UtilizacaoConcreto", on_delete=models.CASCADE, null=True, blank=True, related_name="celulas_mapa",
    )
    sobra = models.ForeignKey(
        "obras.SobraConcreto", on_delete=models.CASCADE, null=True, blank=True, related_name="celulas_mapa",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Célula do mapa"
        verbose_name_plural = "Células do mapa"
        constraints = [
            models.UniqueConstraint(fields=["mapa", "linha", "coluna"], name="obras_conc_celula_pos_uniq"),
        ]

    def __str__(self):
        return f"{self.mapa} ({self.linha},{self.coluna})"
