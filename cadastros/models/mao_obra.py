from django.db import models

from .base import ModeloAtivoTimestamp
from .unidades import UnidadeMedida


class MaoObra(ModeloAtivoTimestamp):
    codigo = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        null=True,
        blank=True,
    )
    descricao = models.CharField(max_length=255, db_index=True)
    categoria = models.CharField(max_length=150, blank=True, db_index=True)
    unidade = models.ForeignKey(
        UnidadeMedida,
        on_delete=models.PROTECT,
        related_name="itens_mao_obra",
    )
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ("categoria", "descricao")
        verbose_name = "Mão de obra"
        verbose_name_plural = "Mão de obra"
        constraints = [
            models.UniqueConstraint(
                fields=["descricao", "categoria", "unidade"],
                name="cad_maoobra_catalogo_uniq",
            )
        ]

    def save(self, *args, **kwargs):
        self.descricao = (self.descricao or "").strip()
        self.categoria = (self.categoria or "").strip()
        self.observacao = (self.observacao or "").strip()
        criando = self.pk is None
        super().save(*args, **kwargs)
        if criando and not self.codigo:
            codigo = f"MO-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(codigo=codigo)
            self.codigo = codigo

    def __str__(self):
        return f"{self.codigo or 'MO'} · {self.descricao} · {self.unidade.sigla}"
