from django.conf import settings
from django.db import models


class VistoriaItem(models.Model):
    class Status(models.TextChoices):
        FEITO = "FEITO", "Feito"
        NAO_FEITO = "NAO_FEITO", "Não feito"

    atividade = models.OneToOneField(
        "planejamento.AtividadePlanejamento", on_delete=models.PROTECT,
        related_name="vistoria_item",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NAO_FEITO)
    atualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item de vistoria"
        verbose_name_plural = "Itens de vistoria"


class VistoriaHistorico(models.Model):
    item = models.ForeignKey(VistoriaItem, related_name="historico", on_delete=models.CASCADE)
    status_anterior = models.CharField(max_length=12, blank=True)
    status_novo = models.CharField(max_length=12)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-data", "-id")
