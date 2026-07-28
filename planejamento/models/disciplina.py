from django.db import models


class Disciplina(models.Model):
    nome = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Nome",
    )

    codigo = models.CharField(
        max_length=60,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Código",
    )

    estrutural = models.BooleanField(
        default=False,
        verbose_name="Disciplina estrutural",
        help_text=(
            "Marque para linhas como RESUMO, "
            "RESUMO GERAL e MARCOS."
        ),
    )

    ordem = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem",
    )

    ativa = models.BooleanField(
        default=True,
        verbose_name="Ativa",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    class Meta:
        verbose_name = "Disciplina"
        verbose_name_plural = "Disciplinas"
        ordering = [
            "ordem",
            "nome",
        ]
        indexes = [
            models.Index(
                fields=[
                    "estrutural",
                    "ativa",
                ],
                name="planej_disc_estrut_idx",
            ),
        ]

    def __str__(self):
        return self.nome