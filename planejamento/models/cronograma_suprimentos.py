from django.conf import settings
from django.db import models
from django.utils import timezone


class ImportacaoCronogramaSuprimentos(models.Model):
    class Status(models.TextChoices):
        PROCESSANDO = "PROCESSANDO", "Processando"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        FALHOU = "FALHOU", "Falhou"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSANDO,
        db_index=True,
    )
    ativa = models.BooleanField(default=False, db_index=True)

    nome_arquivo = models.CharField(max_length=255, blank=True)
    arquivo_drive_id = models.CharField(max_length=255, blank=True, db_index=True)
    mime_type = models.CharField(max_length=255, blank=True)
    data_modificacao_drive = models.DateTimeField(null=True, blank=True)
    hash_arquivo = models.CharField(max_length=64, blank=True, db_index=True)
    tamanho_arquivo_bytes = models.BigIntegerField(default=0)

    total_abas_arquivo = models.PositiveIntegerField(default=0)
    abas_importadas = models.PositiveIntegerField(default=0)
    abas_ignoradas = models.PositiveIntegerField(default=0)
    total_itens_importados = models.PositiveIntegerField(default=0)

    mensagem = models.TextField(blank=True)
    erro_detalhado = models.TextField(blank=True)

    executado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="importacoes_cronograma_suprimentos",
    )

    iniciou_em = models.DateTimeField(null=True, blank=True)
    finalizou_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Importação do cronograma de suprimentos"
        verbose_name_plural = "Importações do cronograma de suprimentos"
        indexes = [
            models.Index(fields=["ativa", "status"], name="plan_cs_imp_ativa_idx"),
            models.Index(fields=["hash_arquivo"], name="plan_cs_imp_hash_idx"),
        ]

    def __str__(self):
        estado = "ativa" if self.ativa else self.get_status_display()
        return f"{self.nome_arquivo or 'Cronograma de suprimentos'} - {estado}"


class CronogramaSuprimentosObra(models.Model):
    importacao = models.ForeignKey(
        ImportacaoCronogramaSuprimentos,
        on_delete=models.CASCADE,
        related_name="obras_importadas",
    )
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        related_name="cronogramas_suprimentos_importados",
    )
    nome_aba = models.CharField(max_length=255, db_index=True)
    codigo_aba = models.CharField(max_length=30, db_index=True)
    data_inicio_obra = models.DateField(null=True, blank=True)
    quantidade_itens = models.PositiveIntegerField(default=0)
    ordem_aba = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("ordem_aba", "nome_aba")
        verbose_name = "Cronograma de suprimentos da obra"
        verbose_name_plural = "Cronogramas de suprimentos das obras"
        constraints = [
            models.UniqueConstraint(
                fields=["importacao", "obra"],
                name="plan_cs_imp_obra_unica",
            ),
            models.UniqueConstraint(
                fields=["importacao", "nome_aba"],
                name="plan_cs_imp_aba_unica",
            ),
        ]
        indexes = [
            models.Index(fields=["importacao", "obra"], name="plan_cs_imp_obra_idx"),
            models.Index(fields=["codigo_aba"], name="plan_cs_codigo_aba_idx"),
        ]

    def __str__(self):
        return f"{self.nome_aba} - {self.obra}"


class ItemCronogramaSuprimento(models.Model):
    """
    Cada item possui duas camadas de datas:

    - datas planejadas/base: importadas da planilha e não editadas na tela;
    - datas realizadas: acompanhamento operacional, inicialmente manual e
      futuramente alimentado pelo módulo de Compras.
    """

    class Etapa(models.TextChoices):
        COTACAO = "COTACAO", "Cotação"
        COMPATIBILIZACAO = "COMPATIBILIZACAO", "Compatibilização"
        NEGOCIACAO = "NEGOCIACAO", "Negociação"
        CONTRATACAO = "CONTRATACAO", "Contratação"
        CONCLUIDO = "CONCLUIDO", "Concluído"

    cronograma_obra = models.ForeignKey(
        CronogramaSuprimentosObra,
        on_delete=models.CASCADE,
        related_name="itens",
    )

    categoria = models.CharField(max_length=120, blank=True, db_index=True)
    situacao = models.CharField(max_length=120, blank=True, db_index=True)

    # Datas base/planejadas - vêm da planilha.
    data_cotacao = models.DateField(null=True, blank=True, db_index=True)
    duracao_cotacao = models.PositiveIntegerField(null=True, blank=True)

    data_compatibilizacao = models.DateField(null=True, blank=True)
    duracao_compatibilizacao = models.PositiveIntegerField(null=True, blank=True)

    data_negociacao = models.DateField(null=True, blank=True)
    duracao_negociacao = models.PositiveIntegerField(null=True, blank=True)

    prazo_limite_contratacao = models.DateField(null=True, blank=True, db_index=True)

    # Datas realizadas - acompanhamento do processo.
    data_real_cotacao = models.DateField(null=True, blank=True, db_index=True)
    data_real_compatibilizacao = models.DateField(null=True, blank=True, db_index=True)
    data_real_negociacao = models.DateField(null=True, blank=True, db_index=True)
    data_real_contratacao = models.DateField(null=True, blank=True, db_index=True)

    # Mantemos os nomes legados destes campos para não quebrar migrations/base.
    # A partir da 0009 eles passam a registrar a edição das DATAS REALIZADAS.
    datas_editadas_manualmente = models.BooleanField(default=False, db_index=True)
    datas_editadas_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="itens_cronograma_suprimentos_editados",
    )
    datas_editadas_em = models.DateTimeField(null=True, blank=True)

    item = models.CharField(max_length=500, db_index=True)
    local = models.CharField(max_length=500, blank=True)
    contratada_responsavel = models.CharField(max_length=255, blank=True)
    dias_apos_inicio = models.IntegerField(null=True, blank=True)
    mes_referencia = models.CharField(max_length=50, blank=True)

    linha_origem = models.PositiveIntegerField(default=0)
    ordem = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("cronograma_obra", "ordem", "id")
        verbose_name = "Item do cronograma de suprimentos"
        verbose_name_plural = "Itens do cronograma de suprimentos"
        indexes = [
            models.Index(
                fields=["cronograma_obra", "categoria"],
                name="plan_cs_item_cat_idx",
            ),
            models.Index(
                fields=["cronograma_obra", "situacao"],
                name="plan_cs_item_sit_idx",
            ),
            models.Index(
                fields=["cronograma_obra", "prazo_limite_contratacao"],
                name="plan_cs_item_prazo_idx",
            ),
        ]

    def __str__(self):
        return f"{self.cronograma_obra.nome_aba} - {self.item}"

    @property
    def percentual_andamento(self) -> int:
        concluidas = sum(
            bool(data)
            for data in (
                self.data_real_cotacao,
                self.data_real_compatibilizacao,
                self.data_real_negociacao,
                self.data_real_contratacao,
            )
        )
        return concluidas * 25


    @staticmethod
    def _calcular_desvio_dias(data_planejada, data_realizada):
        """
        Retorna o desvio em dias entre realizado e planejado.

        > 0: realizado depois do planejado (atraso)
        = 0: realizado na data planejada
        < 0: realizado antes do planejado (adiantamento)
        None: não há comparação possível
        """
        if not data_planejada or not data_realizada:
            return None
        return (data_realizada - data_planejada).days

    @property
    def desvio_cotacao_dias(self):
        return self._calcular_desvio_dias(self.data_cotacao, self.data_real_cotacao)

    @property
    def desvio_compatibilizacao_dias(self):
        return self._calcular_desvio_dias(
            self.data_compatibilizacao,
            self.data_real_compatibilizacao,
        )

    @property
    def desvio_negociacao_dias(self):
        return self._calcular_desvio_dias(self.data_negociacao, self.data_real_negociacao)

    @property
    def desvio_contratacao_dias(self):
        return self._calcular_desvio_dias(
            self.prazo_limite_contratacao,
            self.data_real_contratacao,
        )

    @property
    def etapa_atual(self) -> str:
        if not self.data_real_cotacao:
            return self.Etapa.COTACAO
        if not self.data_real_compatibilizacao:
            return self.Etapa.COMPATIBILIZACAO
        if not self.data_real_negociacao:
            return self.Etapa.NEGOCIACAO
        if not self.data_real_contratacao:
            return self.Etapa.CONTRATACAO
        return self.Etapa.CONCLUIDO

    @property
    def etapa_atual_label(self) -> str:
        return dict(self.Etapa.choices).get(self.etapa_atual, self.etapa_atual)

    @property
    def data_planejada_etapa_atual(self):
        mapa = {
            self.Etapa.COTACAO: self.data_cotacao,
            self.Etapa.COMPATIBILIZACAO: self.data_compatibilizacao,
            self.Etapa.NEGOCIACAO: self.data_negociacao,
            self.Etapa.CONTRATACAO: self.prazo_limite_contratacao,
        }
        return mapa.get(self.etapa_atual)

    @property
    def dias_atraso_etapa_atual(self) -> int:
        if self.etapa_atual == self.Etapa.CONCLUIDO:
            return 0
        planejada = self.data_planejada_etapa_atual
        if not planejada:
            return 0
        return max((timezone.localdate() - planejada).days, 0)

    @property
    def etapa_atual_atrasada(self) -> bool:
        return self.dias_atraso_etapa_atual > 0
