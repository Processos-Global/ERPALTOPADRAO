from django.conf import settings
from django.core.validators import MinValueValidator
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

    class Programa(models.TextChoices):
        ALTO_PADRAO = "ALTO_PADRAO", "Alto Padrão"
        MCMV = "MCMV", "Minha Casa Minha Vida"

    class EstruturaEap(models.IntegerChoices):
        QUATRO_NIVEIS = 4, "4 níveis"
        CINCO_NIVEIS = 5, "5 níveis"

    programa = models.CharField(
        max_length=20,
        choices=Programa.choices,
        default=Programa.ALTO_PADRAO,
        verbose_name="Programa",
        help_text="Define se a obra é Alto Padrão ou Minha Casa Minha Vida.",
    )

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

    quantidade_blocos = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Quantidade de blocos",
        help_text=(
            "Quantidade total de blocos da obra. Obras sem divisão "
            "por blocos (ex: Alto Padrão) devem permanecer com 1."
        ),
    )

    quantidade_pavimentos = models.PositiveIntegerField(
        default=0,
        verbose_name="Quantidade de pavimentos por bloco",
        help_text=(
            "Quantidade de pavimentos existentes em cada bloco. "
            "Nesta configuração, todos os blocos da obra usam a "
            "mesma quantidade de pavimentos."
        ),
    )

    estrutura_eap = models.PositiveSmallIntegerField(
        choices=EstruturaEap.choices,
        default=EstruturaEap.QUATRO_NIVEIS,
        verbose_name="Estrutura da EAP",
        help_text="Quantidade de níveis hierárquicos usados na EAP orçamentária desta obra.",
    )

    possui_condominio = models.BooleanField(
        default=False,
        verbose_name="Possui local Condomínio/área comum",
        help_text=(
            "Marque para liberar um local de Condomínio (área externa, "
            "área comum ou serviços gerais) separado dos blocos/unidades."
        ),
    )

    nome_local_condominio = models.CharField(
        max_length=120,
        blank=True,
        default="Condomínio",
        verbose_name="Nome do local Condomínio",
        help_text="Nome exibido nas telas para o local de serviços gerais da obra.",
    )

    link_maps = models.URLField(
        "Link Google Maps",
        blank=True,
        default="",
        help_text="Link do Google Maps da obra (usado em mensagens automáticas).",
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
            models.Index(
                fields=["programa"],
                name="obras_obra_programa_idx",
            ),
        ]

    @property
    def local_condominio_label(self):
        """Nome a exibir para o local geral da obra, sem depender de espaços em branco."""
        nome = (self.nome_local_condominio or "").strip()
        return nome or "Condomínio"

    @property
    def quantidade_blocos_efetiva(self):
        try:
            quantidade = int(self.quantidade_blocos or 0)
        except (TypeError, ValueError):
            quantidade = 0

        return max(quantidade, 1)

    @property
    def quantidade_pavimentos_total(self):
        """Total de combinações bloco/pavimento da obra (blocos x pavimentos por bloco)."""
        quantidade_pavimentos = int(self.quantidade_pavimentos or 0)
        return self.quantidade_blocos_efetiva * quantidade_pavimentos

    @property
    def possui_estrutura_de_unidades(self):
        return (
            self.quantidade_blocos_efetiva > 0
            and int(self.quantidade_pavimentos or 0) > 0
            and int(self.quantidade_unidades or 0) > 0
        )

    @property
    def resumo_estrutura(self):
        blocos = self.quantidade_blocos_efetiva
        pavimentos = int(self.quantidade_pavimentos or 0)
        unidades = int(self.quantidade_unidades or 0)

        texto_bloco = "bloco" if blocos == 1 else "blocos"
        texto_pavimento = "pavimento" if pavimentos == 1 else "pavimentos"
        texto_unidade = "unidade" if unidades == 1 else "unidades"

        return (
            f"{blocos} {texto_bloco}, "
            f"{pavimentos} {texto_pavimento} por bloco e "
            f"{unidades} {texto_unidade} no total"
        )

    def __str__(self):
        return self.nome