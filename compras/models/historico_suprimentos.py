from django.db import models


class SuprimentoReferencia(models.Model):
    """
    Cadastro canônico de suprimentos usado para ligar:
    - nomes atuais do cronograma;
    - históricos legados;
    - compras novas fechadas no ERP.

    A chave é normalizada e estável; o nome preserva a grafia atual.
    """

    nome = models.CharField(max_length=500)
    chave = models.CharField(max_length=500, unique=True, db_index=True)
    ativo = models.BooleanField(default=True, db_index=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Referência de suprimento"
        verbose_name_plural = "Referências de suprimentos"

    def __str__(self):
        return self.nome


class HistoricoCompraSuprimento(models.Model):
    class Origem(models.TextChoices):
        LEGADO = "LEGADO", "Histórico importado"
        ERP = "ERP", "ERP Alto Padrão"

    # Texto original da compra/histórico.
    suprimento = models.CharField(max_length=500, db_index=True)

    # Mantido por compatibilidade e como fallback para registros antigos.
    # Para vínculos múltiplos, a relação oficial é `suprimentos_referencia`.
    suprimento_chave = models.CharField(max_length=500, db_index=True)

    suprimentos_referencia = models.ManyToManyField(
        "compras.SuprimentoReferencia",
        blank=True,
        related_name="historicos",
    )

    obra = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historico_compras_suprimentos",
    )
    obra_codigo = models.CharField(max_length=50, blank=True, db_index=True)
    obra_nome = models.CharField(max_length=255, blank=True)

    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historico_compras_suprimentos",
    )
    fornecedor_nome = models.CharField(max_length=255)

    valor = models.DecimalField(max_digits=18, decimal_places=2)
    data_fechamento = models.DateField(null=True, blank=True, db_index=True)

    origem = models.CharField(
        max_length=10,
        choices=Origem.choices,
        default=Origem.ERP,
        db_index=True,
    )

    processo = models.ForeignKey(
        "compras.ProcessoCompra",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_historico_suprimento",
    )
    pedido = models.OneToOneField(
        "compras.PedidoCompra",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historico_suprimento",
    )

    arquivo_origem = models.CharField(max_length=255, blank=True)
    aba_origem = models.CharField(max_length=255, blank=True)
    linha_origem = models.PositiveIntegerField(null=True, blank=True)
    chave_importacao = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-data_fechamento", "-id")
        verbose_name = "Histórico de compra de suprimento"
        verbose_name_plural = "Histórico de compras de suprimentos"
        indexes = [
            models.Index(fields=["suprimento_chave", "data_fechamento"], name="comp_hist_sup_data_idx"),
            models.Index(fields=["obra", "suprimento_chave"], name="comp_hist_obra_sup_idx"),
            models.Index(fields=["origem", "processo"], name="comp_hist_orig_proc_idx"),
        ]

    def __str__(self):
        return f"{self.suprimento} - {self.fornecedor_nome} - {self.valor}"
