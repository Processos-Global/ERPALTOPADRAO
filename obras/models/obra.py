from django.conf import settings
from django.db import models


class Obra(models.Model):
    class TipoObra(models.TextChoices):
        CASA = "CASA", "Casa"
        PREDIO = "PREDIO", "Prédio"
        CONDOMINIO = "CONDOMINIO", "Condomínio"
        COMERCIAL = "COMERCIAL", "Comercial"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        PLANEJAMENTO = "PLANEJAMENTO", "Planejamento"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        PARALISADA = "PARALISADA", "Paralisada"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    nome = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nome da obra",
    )

    codigo = models.CharField(
        max_length=60,
        unique=True,
        verbose_name="Código",
    )

    nome_curto = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Nome curto",
    )

    tipo_obra = models.CharField(
        max_length=20,
        choices=TipoObra.choices,
        default=TipoObra.CASA,
        verbose_name="Tipo de obra",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PLANEJAMENTO,
        verbose_name="Status",
    )

    endereco = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Endereço",
    )

    cidade = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Cidade",
    )

    estado = models.CharField(
        max_length=2,
        blank=True,
        verbose_name="Estado",
    )

    cep = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="CEP",
    )

    area_terreno = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Área do terreno",
    )

    area_construida = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Área construída",
    )

    quantidade_unidades = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantidade de unidades",
    )

    data_inicio_prevista = models.DateField(
        null=True,
        blank=True,
        verbose_name="Início previsto",
    )

    data_termino_prevista = models.DateField(
        null=True,
        blank=True,
        verbose_name="Término previsto",
    )

    data_inicio_real = models.DateField(
        null=True,
        blank=True,
        verbose_name="Início real",
    )

    data_termino_real = models.DateField(
        null=True,
        blank=True,
        verbose_name="Término real",
    )

    descricao = models.TextField(
        blank=True,
        verbose_name="Descrição",
    )

    ativa = models.BooleanField(
        default=True,
        verbose_name="Ativa",
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="obras_criadas",
        null=True,
        blank=True,
        verbose_name="Criado por",
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
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = [
            "nome",
        ]
        indexes = [
            models.Index(
                fields=["codigo"],
                name="obras_obra_codigo_idx",
            ),
            models.Index(
                fields=["status", "ativa"],
                name="obras_obra_status_idx",
            ),
        ]

    def __str__(self):
        return self.nome