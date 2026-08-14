from django.conf import settings
from django.db import models
from .core import ProcessoCompra


class HistoricoProcessoCompra(models.Model):
    processo = models.ForeignKey(ProcessoCompra, on_delete=models.PROTECT, related_name="historico")
    tipo = models.CharField(max_length=60, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="historicos_compras")
    descricao = models.TextField()
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-criado_em", "-id")
