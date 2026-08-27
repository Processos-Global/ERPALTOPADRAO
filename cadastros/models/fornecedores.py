from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import ModeloAtivoTimestamp


class Fornecedor(ModeloAtivoTimestamp):
    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        null=True,
        blank=True,
    )
    nome = models.CharField(max_length=255, db_index=True, verbose_name="Razão social / nome")
    nome_fantasia = models.CharField(max_length=255, blank=True, db_index=True)
    documento = models.CharField(max_length=30, blank=True, db_index=True, verbose_name="CPF / CNPJ")
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=40, blank=True)
    contato = models.CharField(max_length=150, blank=True, verbose_name="Pessoa de contato")
    cidade = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=2, blank=True)
    avaliacao = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
        help_text="Avaliação comercial de 0 a 5.",
    )
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        indexes = [
            models.Index(fields=["ativo", "nome"], name="cad_for_ativo_nome_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["documento"],
                condition=~models.Q(documento=""),
                name="cad_for_doc_uniq",
            )
        ]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.nome_fantasia = (self.nome_fantasia or "").strip()
        self.documento = (self.documento or "").strip()
        self.email = (self.email or "").strip()
        self.telefone = (self.telefone or "").strip()
        self.contato = (self.contato or "").strip()
        self.cidade = (self.cidade or "").strip()
        self.estado = (self.estado or "").strip().upper()
        self.observacao = (self.observacao or "").strip()
        criando = self.pk is None
        super().save(*args, **kwargs)
        if criando and not self.codigo:
            codigo = f"FOR-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(codigo=codigo)
            self.codigo = codigo

    @property
    def nome_exibicao(self):
        return self.nome_fantasia or self.nome

    def __str__(self):
        return f"{self.codigo or 'FOR'} · {self.nome_exibicao}"
