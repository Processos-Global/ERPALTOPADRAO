from django.db import models

from .base import ModeloAtivoTimestamp


class CaracteristicaAmbiente(ModeloAtivoTimestamp):
    codigo = models.CharField(max_length=40, unique=True)
    nome = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Característica de ambiente"
        verbose_name_plural = "Características de ambientes"

    def __str__(self):
        return self.nome


class TipoPavimento(ModeloAtivoTimestamp):
    nome = models.CharField(max_length=100, unique=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Tipo de pavimento"
        verbose_name_plural = "Tipos de pavimento"

    def __str__(self):
        return self.nome


class TipoAmbiente(ModeloAtivoTimestamp):
    nome = models.CharField(max_length=140, unique=True)
    caracteristica_padrao = models.ForeignKey(
        CaracteristicaAmbiente,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tipos_ambiente",
    )

    class Meta:
        ordering = ("nome",)
        verbose_name = "Tipo de ambiente"
        verbose_name_plural = "Tipos de ambientes"

    def __str__(self):
        return self.nome


class CategoriaGrandeFornecedor(ModeloAtivoTimestamp):
    class TipoPreenchimento(models.TextChoices):
        MULTIPLA_PROJETO = "MULTIPLA_PROJETO", "Múltipla escolha - projeto"
        MULTIPLA_AMBIENTE = "MULTIPLA_AMBIENTE", "Múltipla escolha - por ambiente"
        SIM_NAO_PROJETO = "SIM_NAO_PROJETO", "Sim/Não - no projeto"
        SIM_NAO_AMBIENTE = "SIM_NAO_AMBIENTE", "Sim/Não - por ambiente"
        DESCRITIVO = "DESCRITIVO", "Descritivo - aberto"

    nome = models.CharField(max_length=160, unique=True)
    tipo_preenchimento = models.CharField(
        max_length=30,
        choices=TipoPreenchimento.choices,
        default=TipoPreenchimento.MULTIPLA_AMBIENTE,
    )
    somente_area_molhada = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Categoria de Grande Fornecedor"
        verbose_name_plural = "Categorias de Grandes Fornecedores"

    @property
    def por_ambiente(self):
        return self.tipo_preenchimento in {
            self.TipoPreenchimento.MULTIPLA_AMBIENTE,
            self.TipoPreenchimento.SIM_NAO_AMBIENTE,
        }

    def __str__(self):
        return self.nome


class TipoItemGrandeFornecedor(ModeloAtivoTimestamp):
    categoria = models.ForeignKey(
        CategoriaGrandeFornecedor,
        on_delete=models.CASCADE,
        related_name="tipos_itens",
    )
    nome = models.CharField(max_length=160)
    unidade_padrao = models.ForeignKey(
        "cadastros.UnidadeMedida",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tipos_itens_grande_fornecedor",
    )
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("categoria__ordem", "ordem", "nome")
        constraints = [
            models.UniqueConstraint(
                fields=("categoria", "nome"),
                name="cad_tipo_item_gf_cat_nome_uniq",
            )
        ]
        verbose_name = "Tipo de item de Grande Fornecedor"
        verbose_name_plural = "Tipos de itens de Grandes Fornecedores"

    def __str__(self):
        return f"{self.categoria.nome} · {self.nome}"


class OpcaoEspecificacaoGrandeFornecedor(ModeloAtivoTimestamp):
    categoria = models.ForeignKey(
        CategoriaGrandeFornecedor,
        on_delete=models.CASCADE,
        related_name="opcoes_especificacao",
    )
    tipo_item = models.ForeignKey(
        TipoItemGrandeFornecedor,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="opcoes_especificacao",
    )
    nome = models.CharField(max_length=220)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("categoria__ordem", "ordem", "nome")
        constraints = [
            models.UniqueConstraint(
                fields=("categoria", "tipo_item", "nome"),
                name="cad_opcao_esp_gf_uniq",
            )
        ]
        verbose_name = "Opção de especificação GF"
        verbose_name_plural = "Opções de especificação GF"

    def __str__(self):
        return self.nome
