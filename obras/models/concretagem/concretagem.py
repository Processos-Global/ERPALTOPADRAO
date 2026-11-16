"""Entidade central da concretagem e seus registros de planejamento/auditoria.

As transições de status nunca são feitas diretamente: use
`obras.services.concretagem.fluxo.mudar_status`, que valida a transição,
aplica as regras da etapa e grava o histórico.
"""
import uuid

from django.conf import settings
from django.db import models


class Concretagem(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        SOLICITADA = "SOLICITADA", "Solicitada"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        EXECUTADA = "EXECUTADA", "Executada"
        AGUARDANDO_LAUDOS = "AGUARDANDO_LAUDOS", "Aguardando laudos"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    class RespostaConcreteira(models.TextChoices):
        ACEITO = "ACEITO", "Aceito"
        REJEITADO = "REJEITADO", "Rejeitado"
        REAGENDAMENTO = "REAGENDAMENTO", "Pediu reagendamento"

    STATUS_TERMINAIS = (Status.CONCLUIDA, Status.CANCELADA)
    # Ordem exibida na barra de etapas da tela de detalhe.
    ETAPAS = (
        Status.RASCUNHO, Status.SOLICITADA, Status.CONFIRMADA,
        Status.EXECUTADA, Status.AGUARDANDO_LAUDOS, Status.CONCLUIDA,
    )

    codigo = models.CharField("Código", max_length=20, unique=True, editable=False)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.PROTECT, related_name="concretagens", verbose_name="Obra",
    )
    engenheiro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="concretagens_responsavel", verbose_name="Engenheiro responsável",
    )
    concreteira = models.ForeignKey(
        "cadastros.Fornecedor", on_delete=models.PROTECT, null=True, blank=True,
        related_name="concretagens", verbose_name="Concreteira",
    )

    # Dados técnicos
    fck_projeto = models.DecimalField("Fck de projeto (MPa)", max_digits=6, decimal_places=1, null=True, blank=True)
    slump = models.CharField("Slump flow", max_length=50, blank=True)
    slump_tolerancia = models.CharField("Tolerância do slump (±)", max_length=20, blank=True)
    agregado = models.CharField("Agregado / brita", max_length=60, blank=True)
    volume_solicitado = models.DecimalField("Volume solicitado (m³)", max_digits=8, decimal_places=2, null=True, blank=True)
    com_bomba = models.BooleanField("Com bomba estacionária", default=False)
    nome_bombista = models.CharField("Bombista", max_length=200, blank=True)

    # Agendamento e entrega
    data_programada = models.DateField("Data programada", null=True, blank=True)
    horario_programado = models.TimeField("Horário programado", null=True, blank=True)
    endereco_entrega = models.CharField("Endereço de entrega", max_length=500, blank=True)
    link_maps_entrega = models.URLField("Link Google Maps", max_length=500, blank=True)
    razao_social_empreendimento = models.CharField(
        "Razão social do empreendimento", max_length=255, blank=True,
        help_text="Aparece na mensagem para a concreteira (SPE/incorporadora da obra).",
    )
    observacoes = models.TextField("Observações", blank=True)

    status = models.CharField("Status", max_length=30, choices=Status.choices, default=Status.RASCUNHO)
    solicitada_em = models.DateTimeField("Solicitada em", null=True, blank=True)

    # Resposta da concreteira pelo link público (ou aceite manual do gerente)
    token_confirmacao = models.UUIDField("Token público", default=uuid.uuid4, unique=True, editable=False)
    confirmacao_cliente = models.CharField(
        "Resposta da concreteira", max_length=20, blank=True, choices=RespostaConcreteira.choices,
    )
    confirmacao_observacao = models.TextField("Observação da concreteira", blank=True)
    confirmado_em = models.DateTimeField("Respondida em", null=True, blank=True)
    aceite_manual_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="concretagens_aceitas_manualmente", verbose_name="Aceite manual por",
    )
    reagendamento_data_sugerida = models.DateField("Data sugerida", null=True, blank=True)
    reagendamento_horario_sugerido = models.TimeField("Horário sugerido", null=True, blank=True)
    reagendamento_solicitante = models.CharField("Quem pediu o reagendamento", max_length=150, blank=True)

    # Marcos da execução e do controle tecnológico
    executada_em = models.DateTimeField("Finalizada em campo em", null=True, blank=True)
    ocorrencias = models.TextField("Ocorrências da execução", blank=True)
    cps_enviados_em = models.DateTimeField("CPs enviados ao laboratório em", null=True, blank=True)
    cps_enviados_por_nome = models.CharField("Quem enviou os CPs", max_length=200, blank=True)
    concluida_em = models.DateTimeField("Concluída em", null=True, blank=True)
    concluida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="concretagens_concluidas", verbose_name="Concluída por",
    )

    # Google Drive
    drive_pasta_id = models.CharField("ID da pasta no Drive", max_length=200, blank=True)
    drive_pasta_url = models.URLField("Pasta no Drive", max_length=500, blank=True)

    cancelado_em = models.DateTimeField("Cancelada em", null=True, blank=True)
    motivo_cancelamento = models.TextField("Motivo do cancelamento", blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="concretagens_criadas", verbose_name="Criada por",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="concretagens_atualizadas", verbose_name="Atualizada por",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_programada", "-criado_em"]
        verbose_name = "Concretagem"
        verbose_name_plural = "Concretagens"
        indexes = [
            models.Index(fields=["obra", "status"], name="obras_conc_obra_status_idx"),
            models.Index(fields=["data_programada"], name="obras_conc_data_idx"),
            models.Index(fields=["status"], name="obras_conc_status_idx"),
            models.Index(fields=["concreteira", "status"], name="obras_conc_forn_status_idx"),
        ]

    def __str__(self):
        return self.codigo or f"Concretagem #{self.pk or 'nova'}"

    @property
    def concreteira_nome(self):
        if not self.concreteira_id:
            return ""
        return self.concreteira.nome_fantasia or self.concreteira.nome

    @property
    def slump_texto(self):
        if not self.slump:
            return ""
        return f"{self.slump} ± {self.slump_tolerancia}" if self.slump_tolerancia else self.slump

    @property
    def terminal(self):
        return self.status in self.STATUS_TERMINAIS

    @property
    def aguardando_resposta(self):
        return self.status == self.Status.SOLICITADA and not self.confirmacao_cliente

    @property
    def pediu_reagendamento(self):
        return (
            self.status == self.Status.SOLICITADA
            and self.confirmacao_cliente == self.RespostaConcreteira.REAGENDAMENTO
        )

    def descricao_servico(self):
        """Resumo curto das peças planejadas, usado em listas, mensagem e nome da pasta."""
        nomes = []
        for item in self.itens_planejados.all():
            texto = item.local.descricao_completa if item.local_id else item.descricao
            if texto and texto not in nomes:
                nomes.append(texto)
        return ", ".join(nomes)


class ItemConcretagemPlanejado(models.Model):
    concretagem = models.ForeignKey(
        Concretagem, on_delete=models.CASCADE, related_name="itens_planejados", verbose_name="Concretagem",
    )
    local = models.ForeignKey(
        "obras.LocalUsoObra", on_delete=models.PROTECT, null=True, blank=True,
        related_name="itens_planejados", verbose_name="Local de uso",
    )
    descricao = models.CharField("Descrição", max_length=300, blank=True)
    volume_previsto = models.DecimalField("Volume previsto (m³)", max_digits=8, decimal_places=2)
    ordem = models.PositiveSmallIntegerField("Ordem", default=0)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Item planejado"
        verbose_name_plural = "Itens planejados"

    def __str__(self):
        return f"{self.titulo} — {self.volume_previsto} m³"

    @property
    def titulo(self):
        if self.local_id:
            return self.local.descricao_completa + (f" — {self.descricao}" if self.descricao else "")
        return self.descricao or "Item sem descrição"


class HistoricoConcretagem(models.Model):
    """Linha do tempo imutável da concretagem."""

    class Acao(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        EDICAO = "EDICAO", "Edição"
        MUDANCA_STATUS = "MUDANCA_STATUS", "Mudança de status"
        ENVIO_MENSAGEM = "ENVIO_MENSAGEM", "Envio à concreteira"
        RESPOSTA_CONCRETEIRA = "RESPOSTA_CONCRETEIRA", "Resposta da concreteira"
        REAGENDAMENTO = "REAGENDAMENTO", "Reagendamento"
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        ANEXO = "ANEXO", "Anexo"
        OUTRO = "OUTRO", "Outro"

    concretagem = models.ForeignKey(
        Concretagem, on_delete=models.CASCADE, related_name="historicos", verbose_name="Concretagem",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="historicos_concretagem", verbose_name="Usuário",
    )
    acao = models.CharField("Ação", max_length=30, choices=Acao.choices, default=Acao.OUTRO)
    status_anterior = models.CharField(max_length=30, blank=True)
    status_novo = models.CharField(max_length=30, blank=True)
    observacao = models.TextField("Observação", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Histórico da concretagem"
        verbose_name_plural = "Histórico das concretagens"
        indexes = [models.Index(fields=["concretagem", "criado_em"], name="obras_conc_hist_idx")]

    def __str__(self):
        return f"{self.concretagem} — {self.get_acao_display()}"


class EnvioMensagemConcretagem(models.Model):
    class Canal(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "E-mail"
        COPIADO = "COPIADO", "Copiado"

    concretagem = models.ForeignKey(
        Concretagem, on_delete=models.CASCADE, related_name="envios_mensagem", verbose_name="Concretagem",
    )
    canal = models.CharField("Canal", max_length=20, choices=Canal.choices)
    destinatario = models.CharField("Destinatário", max_length=500, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="envios_concretagem",
    )
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-enviado_em"]
        verbose_name = "Envio de mensagem da concretagem"
        verbose_name_plural = "Envios de mensagem da concretagem"

    def __str__(self):
        return f"{self.concretagem} → {self.get_canal_display()}"
