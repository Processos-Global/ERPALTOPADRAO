from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class SequenciaFinanceira(models.Model):
    tipo = models.CharField(max_length=30)
    ano = models.PositiveIntegerField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tipo", "ano"], name="fin_seq_tipo_ano_uniq"),
        ]


class PlanoFinanceiro(models.Model):
    class Tipo(models.TextChoices):
        DESPESA = "DESPESA", "Despesa"
        RECEITA = "RECEITA", "Receita"

    codigo = models.CharField(max_length=30, unique=True, db_index=True)
    nome = models.CharField(max_length=160, db_index=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.DESPESA)
    pai = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="filhos",
    )
    ativo = models.BooleanField(default=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("codigo", "nome")
        verbose_name = "Conta do plano financeiro"
        verbose_name_plural = "Plano financeiro"

    def __str__(self):
        return f"{self.codigo} · {self.nome}"

    @property
    def caminho(self):
        partes = [self.nome]
        atual = self.pai
        limite = 0
        while atual is not None and limite < 10:
            partes.append(atual.nome)
            atual = atual.pai
            limite += 1
        return " > ".join(reversed(partes))


class DespesaRecorrente(models.Model):
    descricao = models.CharField(max_length=220)
    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="despesas_recorrentes",
    )
    obra = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="despesas_recorrentes",
    )
    plano_financeiro = models.ForeignKey(
        PlanoFinanceiro,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="despesas_recorrentes",
    )
    valor = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    dia_vencimento = models.PositiveSmallIntegerField(default=10)
    inicio = models.DateField()
    fim = models.DateField(null=True, blank=True)
    ativo = models.BooleanField(default=True, db_index=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="despesas_recorrentes_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("descricao",)
        verbose_name = "Despesa recorrente"
        verbose_name_plural = "Despesas recorrentes"

    def __str__(self):
        return self.descricao
