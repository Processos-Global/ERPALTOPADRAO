from django.db import models
from django.utils.text import slugify


class ChecklistProjetoGrupo(models.Model):
    TIPO_COMPATIBILIZACAO = "COMPATIBILIZACAO"
    TIPO_CHOICES = [
        (TIPO_COMPATIBILIZACAO, "Acompanhamento de Projetos"),
    ]

    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    nome = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "ordem", "nome", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tipo", "slug"], name="cad_chk_grupo_tipo_slug_uniq")
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.nome}"


class ChecklistProjetoItem(models.Model):
    grupo = models.ForeignKey(
        ChecklistProjetoGrupo,
        on_delete=models.CASCADE,
        related_name="itens",
    )
    etapa = models.CharField(max_length=40, blank=True)
    codigo = models.CharField(max_length=40, blank=True)
    entrega_atividade = models.CharField(max_length=500)
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["grupo__ordem", "ordem", "id"]
        indexes = [
            models.Index(fields=["grupo", "ativo", "ordem"], name="cad_chk_item_ordem_idx")
        ]

    def __str__(self):
        prefixo = " · ".join([p for p in [self.etapa, self.codigo] if p])
        return f"{prefixo} · {self.entrega_atividade}" if prefixo else self.entrega_atividade
