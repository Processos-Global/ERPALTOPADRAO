from django.db import models

from .base import ModeloAtivoTimestamp
from .unidades import UnidadeMedida


class Material(ModeloAtivoTimestamp):
    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        null=True,
        blank=True,
    )
    nome = models.CharField(max_length=255, db_index=True)
    especificacao = models.CharField(max_length=255, blank=True, db_index=True)
    unidade = models.ForeignKey(
        UnidadeMedida,
        on_delete=models.PROTECT,
        related_name="materiais",
    )
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ("nome", "especificacao", "codigo")
        verbose_name = "Material"
        verbose_name_plural = "Materiais"
        indexes = [
            models.Index(fields=["ativo", "nome"], name="cad_mat_ativo_nome_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "especificacao", "unidade"],
                name="cad_material_catalogo_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        self.especificacao = (self.especificacao or "").strip()
        self.observacao = (self.observacao or "").strip()
        criando = self.pk is None
        super().save(*args, **kwargs)
        if criando and not self.codigo:
            codigo = f"MAT-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(codigo=codigo)
            self.codigo = codigo

    @property
    def descricao_completa(self):
        return f"{self.nome} — {self.especificacao}" if self.especificacao else self.nome

    def __str__(self):
        return f"{self.codigo or 'MAT'} · {self.descricao_completa} · {self.unidade.sigla}"
