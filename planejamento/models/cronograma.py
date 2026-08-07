from django.conf import settings
from django.db import models


class ImportacaoCronograma(models.Model):
    class Status(models.TextChoices):
        PROCESSANDO = "PROCESSANDO", "Processando"
        VALIDANDO = "VALIDANDO", "Validando"
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
    arquivo_drive_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    data_modificacao_drive = models.DateTimeField(null=True, blank=True)
    hash_arquivo = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    tamanho_arquivo_bytes = models.BigIntegerField(default=0)

    total_linhas_arquivo = models.PositiveBigIntegerField(default=0)
    linhas_importadas = models.PositiveBigIntegerField(default=0)
    projetos_identificados = models.PositiveIntegerField(default=0)
    semanas_identificadas = models.PositiveIntegerField(default=0)

    mensagem = models.TextField(blank=True)
    erro_detalhado = models.TextField(blank=True)

    executado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="importacoes_cronograma_planejamento",
    )

    iniciou_em = models.DateTimeField(null=True, blank=True)
    finalizou_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Importação de cronograma"
        verbose_name_plural = "Importações de cronograma"
        indexes = [
            models.Index(fields=["ativa", "status"]),
            models.Index(fields=["hash_arquivo"]),
            models.Index(fields=["data_modificacao_drive"]),
        ]

    def __str__(self):
        estado = "ativa" if self.ativa else self.get_status_display()
        return f"{self.nome_arquivo or 'Cronograma'} - {estado}"


class AtividadePlanejamento(models.Model):
    """
    Identidade permanente de uma atividade física do planejamento.

    RegistroCronograma continua sendo o snapshot semanal. Esta entidade existe
    para que a mesma atividade, vista em semanas/importações diferentes, possua
    sempre a mesma identidade dentro do ERP.
    """

    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        related_name="atividades_planejamento",
    )
    chave = models.CharField(max_length=64, unique=True, db_index=True)

    # Mantém os textos normalizados/originais necessários para auditoria e
    # para facilitar o diagnóstico de vínculos no futuro.
    projeto_origem = models.CharField(max_length=255, blank=True, db_index=True)
    disciplina = models.CharField(max_length=255, blank=True, db_index=True)
    local_tarefa = models.TextField(blank=True)
    nome_tarefa = models.TextField(blank=True)

    ativa = models.BooleanField(default=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("obra", "disciplina", "local_tarefa", "nome_tarefa")
        verbose_name = "Atividade de planejamento"
        verbose_name_plural = "Atividades de planejamento"
        indexes = [
            models.Index(fields=["obra", "ativa"], name="plan_atv_obra_ativa_idx"),
            models.Index(fields=["obra", "disciplina"], name="plan_atv_obra_disc_idx"),
        ]

    def __str__(self):
        return f"{self.projeto_origem or self.obra_id} - {self.nome_tarefa}"


class RegistroCronograma(models.Model):
    importacao = models.ForeignKey(
        ImportacaoCronograma,
        on_delete=models.CASCADE,
        related_name="registros",
    )

    # A obra oficial do ERP. null=True preserva compatibilidade com snapshots
    # históricos anteriores a esta integração. Novas importações exigem vínculo.
    obra = models.ForeignKey(
        "obras.Obra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registros_cronograma_planejamento",
    )

    # Preenchida somente para atividades físicas. Linhas estruturais como
    # RESUMO GERAL, RESUMO e MARCOS podem permanecer sem atividade permanente.
    atividade_planejamento = models.ForeignKey(
        AtividadePlanejamento,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )

    # Nome exatamente como recebido do CSV. Continua existindo para auditoria
    # e compatibilidade com filtros/templates atuais.
    projeto = models.CharField(max_length=255, db_index=True)
    tipo = models.CharField(max_length=100, blank=True)
    quantidade_unidades = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    semana = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    data_atualizacao = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )

    local_tarefa = models.TextField(blank=True)
    nome_tarefa = models.TextField(blank=True)

    inicio_real = models.DateField(null=True, blank=True)
    duracao_real = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    termino_real = models.DateField(null=True, blank=True)

    inicio_base = models.DateField(null=True, blank=True)
    duracao_base = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    termino_base = models.DateField(null=True, blank=True)

    percentual_concluida = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    percentual_previsto_tarefa = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    disciplina = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    checklist_habitese = models.CharField(max_length=255, blank=True)
    checklist_cef = models.CharField(max_length=255, blank=True)
    responsavel = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    peso = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
    )
    percentual_executado = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    percentual_previsto = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    inicio_semana = models.DateField(null=True, blank=True)
    semana_anterior = models.CharField(max_length=100, blank=True)
    semana_seguinte = models.CharField(max_length=100, blank=True)
    inicio_semana_base = models.DateField(null=True, blank=True)

    # ============================================================
    # CONTROLE DE REPROGRAMAÇÃO
    # ============================================================

    # Agora representa a identidade permanente da atividade, sem a semana.
    # Em snapshots antigos pode conter a chave legada; novas importações usam
    # a mesma chave da AtividadePlanejamento.
    chave_atividade = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )

    inicio_base_anterior = models.DateField(null=True, blank=True)
    termino_base_anterior = models.DateField(null=True, blank=True)

    reprogramada = models.BooleanField(default=False, db_index=True)
    reprogramada_em = models.DateTimeField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("projeto", "semana", "id")
        verbose_name = "Registro de cronograma"
        verbose_name_plural = "Registros de cronograma"
        indexes = [
            models.Index(fields=["importacao", "projeto", "semana"]),
            models.Index(fields=["importacao", "obra", "semana"], name="plan_imp_obra_sem_idx"),
            models.Index(fields=["importacao", "atividade_planejamento", "semana"], name="plan_imp_atv_sem_idx"),
            models.Index(fields=["importacao", "disciplina"]),
            models.Index(fields=["importacao", "data_atualizacao"]),
            models.Index(fields=["projeto", "responsavel"]),
            models.Index(
                fields=["importacao", "chave_atividade"],
                name="plan_imp_chave_idx",
            ),
            models.Index(
                fields=["importacao", "reprogramada"],
                name="plan_imp_reprog_idx",
            ),
        ]

    def __str__(self):
        return f"{self.projeto} - semana {self.semana or '-'}"
