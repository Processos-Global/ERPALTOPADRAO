from django.db import models

from .base import ModeloAtivoTimestamp


class UnidadeMedida(ModeloAtivoTimestamp):
    sigla = models.CharField(max_length=20, unique=True, db_index=True)
    descricao = models.CharField(max_length=100)

    class Meta:
        ordering = ("sigla",)
        verbose_name = "Unidade de medida"
        verbose_name_plural = "Unidades de medida"

    def save(self, *args, **kwargs):
        self.sigla = (self.sigla or "").strip().upper()
        self.descricao = (self.descricao or self.sigla).strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.sigla
