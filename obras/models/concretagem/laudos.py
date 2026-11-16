"""Laudos de resistência (rompimento dos CPs) aos 7, 14 e 28 dias."""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models

# Percentual mínimo do fck de projeto por idade (regra do sistema anterior).
LIMITES_FCK = {7: Decimal("0.600"), 14: Decimal("0.717"), 28: Decimal("0.950")}


class LaudoConcretagem(models.Model):
    class Idade(models.IntegerChoices):
        D7 = 7, "7 dias"
        D14 = 14, "14 dias"
        D28 = 28, "28 dias"

    concretagem = models.ForeignKey(
        "obras.Concretagem", on_delete=models.CASCADE, related_name="laudos", verbose_name="Concretagem",
    )
    idade_dias = models.PositiveSmallIntegerField("Idade", choices=Idade.choices)
    resistencia_mpa = models.DecimalField("Resistência obtida (MPa)", max_digits=6, decimal_places=1)
    enviado_por_nome = models.CharField(
        "Quem enviou os CPs ao laboratório", max_length=200, blank=True,
        help_text="Pessoa que levou/enviou os corpos de prova (cadeia de custódia).",
    )
    observacao = models.CharField("Observação", max_length=300, blank=True)
    lancado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="laudos_concretagem_lancados",
    )
    lancado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["idade_dias"]
        verbose_name = "Laudo de resistência"
        verbose_name_plural = "Laudos de resistência"
        constraints = [
            models.UniqueConstraint(fields=["concretagem", "idade_dias"], name="obras_conc_laudo_idade_uniq"),
        ]

    def __str__(self):
        return f"{self.concretagem} — {self.idade_dias} dias: {self.resistencia_mpa} MPa"

    @property
    def limite_percentual(self):
        return LIMITES_FCK.get(self.idade_dias, Decimal("0"))

    @property
    def limite_minimo_mpa(self):
        fck = self.concretagem.fck_projeto
        if not fck:
            return None
        return (fck * self.limite_percentual).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def percentual_fck(self):
        """Resistência / fck de projeto, em % com 1 casa (ex.: 96.7)."""
        fck = self.concretagem.fck_projeto
        if not fck:
            return None
        return (self.resistencia_mpa / fck * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def aprovado(self):
        fck = self.concretagem.fck_projeto
        if not fck:
            return False
        return self.resistencia_mpa >= fck * self.limite_percentual
