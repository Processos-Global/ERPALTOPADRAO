from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class FichaTecnicaObra(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        EM_PREENCHIMENTO = "EM_PREENCHIMENTO", "Em preenchimento"
        CONCLUIDA = "CONCLUIDA", "Concluída"

    obra = models.OneToOneField(
        "obras.Obra",
        on_delete=models.CASCADE,
        related_name="ficha_tecnica",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO, db_index=True)
    versao = models.PositiveIntegerField(default=1)
    observacoes = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fichas_tecnicas_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("obra__nome",)
        verbose_name = "Ficha técnica da obra"
        verbose_name_plural = "Fichas técnicas das obras"

    def __str__(self):
        return f"Ficha Técnica · {self.obra.nome}"


class PavimentoFichaTecnica(models.Model):
    ficha = models.ForeignKey(FichaTecnicaObra, on_delete=models.CASCADE, related_name="pavimentos")
    tipo_pavimento = models.ForeignKey(
        "cadastros.TipoPavimento",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pavimentos_obras",
    )
    nome = models.CharField(max_length=120)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ("ordem", "id")
        constraints = [
            models.UniqueConstraint(fields=("ficha", "nome"), name="obras_ficha_pav_nome_uniq")
        ]

    def __str__(self):
        return self.nome


class AmbienteFichaTecnica(models.Model):
    pavimento = models.ForeignKey(PavimentoFichaTecnica, on_delete=models.CASCADE, related_name="ambientes")
    tipo_ambiente = models.ForeignKey(
        "cadastros.TipoAmbiente",
        on_delete=models.PROTECT,
        related_name="ambientes_fichas_tecnicas",
    )
    identificacao = models.CharField(max_length=160)
    caracteristica = models.ForeignKey(
        "cadastros.CaracteristicaAmbiente",
        on_delete=models.PROTECT,
        related_name="ambientes_fichas_tecnicas",
    )
    area_m2 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ("pavimento__ordem", "ordem", "identificacao")
        constraints = [
            models.UniqueConstraint(
                fields=("pavimento", "identificacao"),
                name="obras_ficha_amb_pav_ident_uniq",
            )
        ]

    @property
    def ficha(self):
        return self.pavimento.ficha

    def __str__(self):
        return f"{self.pavimento.nome} · {self.identificacao}"


class CategoriaFichaTecnica(models.Model):
    ficha = models.ForeignKey(FichaTecnicaObra, on_delete=models.CASCADE, related_name="categorias_aplicadas")
    categoria = models.ForeignKey(
        "cadastros.CategoriaGrandeFornecedor",
        on_delete=models.PROTECT,
        related_name="aplicacoes_ficha_tecnica",
    )
    ambiente = models.ForeignKey(
        AmbienteFichaTecnica,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="categorias_gf",
        help_text="Vazio quando a categoria é aplicada à obra inteira.",
    )
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("categoria__ordem", "categoria__nome", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("ficha", "categoria", "ambiente"),
                name="obras_ficha_cat_amb_uniq",
            )
        ]

    @property
    def escopo(self):
        return self.ambiente.identificacao if self.ambiente_id else "Obra inteira"

    def __str__(self):
        return f"{self.categoria.nome} · {self.escopo}"


class ItemFichaTecnica(models.Model):
    aplicacao_categoria = models.ForeignKey(
        CategoriaFichaTecnica,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    tipo_item = models.ForeignKey(
        "cadastros.TipoItemGrandeFornecedor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="itens_fichas_tecnicas",
    )
    descricao_item = models.CharField(
        max_length=180,
        blank=True,
        help_text="Usado quando a categoria possui preenchimento descritivo ou não tem tipo pré-cadastrado.",
    )
    quantidade = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    unidade = models.ForeignKey(
        "cadastros.UnidadeMedida",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="itens_fichas_tecnicas",
    )
    opcao_especificacao = models.ForeignKey(
        "cadastros.OpcaoEspecificacaoGrandeFornecedor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="itens_fichas_tecnicas",
    )
    especificacao = models.TextField(blank=True)
    observacao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("aplicacao_categoria_id", "ordem", "id")

    @property
    def nome_item(self):
        if self.tipo_item_id:
            return self.tipo_item.nome
        return self.descricao_item or self.aplicacao_categoria.categoria.nome

    @property
    def especificacao_completa(self):
        partes = []
        if self.opcao_especificacao_id:
            partes.append(self.opcao_especificacao.nome)
        if self.especificacao:
            partes.append(self.especificacao.strip())
        return " · ".join(p for p in partes if p)

    @property
    def ambiente(self):
        return self.aplicacao_categoria.ambiente

    def __str__(self):
        return self.nome_item
