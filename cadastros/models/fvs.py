from django.db import models


class ModeloFVS(models.Model):
    nome = models.CharField(max_length=180, unique=True, verbose_name="Nome do modelo")
    disciplina = models.CharField(max_length=120, blank=True, verbose_name="Disciplina")
    descricao = models.TextField(blank=True, verbose_name="Descrição")
    normas_referencias = models.TextField(blank=True, verbose_name="Normas / referências")
    revisao = models.CharField(max_length=30, default="R01", verbose_name="Revisão")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Modelo de FVS"
        verbose_name_plural = "Modelos de FVS"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} · {self.revisao}"


class ItemModeloFVS(models.Model):
    modelo = models.ForeignKey(
        ModeloFVS,
        on_delete=models.CASCADE,
        related_name="itens",
        verbose_name="Modelo",
    )
    ordem = models.PositiveIntegerField(default=1, verbose_name="Ordem")
    item_verificacao = models.CharField(max_length=255, verbose_name="Item de verificação")
    metodo_instrumento = models.CharField(max_length=255, blank=True, verbose_name="Método / instrumento")
    criterio_aceite = models.TextField(blank=True, verbose_name="Critério de aceite")
    tolerancia = models.TextField(blank=True, verbose_name="Tolerância")
    obrigatorio = models.BooleanField(default=True, verbose_name="Obrigatório")

    class Meta:
        verbose_name = "Item do modelo de FVS"
        verbose_name_plural = "Itens do modelo de FVS"
        ordering = ["ordem", "pk"]

    def __str__(self):
        return f"{self.ordem:02d} · {self.item_verificacao}"
