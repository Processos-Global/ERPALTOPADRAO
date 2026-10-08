from django.conf import settings
from django.db import models


class StatusChecklistProjeto(models.TextChoices):
    NAO_RECEBIDO = "NAO_RECEBIDO", "Não Recebido"
    PARCIALMENTE = "PARCIALMENTE", "Parcialmente"
    RECEBIDO = "RECEBIDO", "Recebido"
    NAO_SE_APLICA = "NAO_SE_APLICA", "Não se aplica"


class ChecklistProjetoResposta(models.Model):
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.CASCADE,
        related_name="respostas_checklist_projetos",
    )
    item = models.ForeignKey(
        "cadastros.ChecklistProjetoItem",
        on_delete=models.PROTECT,
        related_name="respostas_obras",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChecklistProjeto.choices,
        default=StatusChecklistProjeto.NAO_RECEBIDO,
    )
    observacao = models.TextField(blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checklists_projetos_atualizados",
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["item__grupo__ordem", "item__ordem", "item__id"]
        constraints = [
            models.UniqueConstraint(
                fields=["obra", "item"],
                name="projetos_checklist_resposta_obra_item_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["obra", "status"], name="proj_chk_obra_status_idx"),
            models.Index(fields=["item", "status"], name="proj_chk_item_status_idx"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.item} · {self.get_status_display()}"


class ChecklistProjetoHistorico(models.Model):
    CAMPO_STATUS = "STATUS"
    CAMPO_OBSERVACAO = "OBSERVACAO"
    CAMPOS = [
        (CAMPO_STATUS, "Status"),
        (CAMPO_OBSERVACAO, "Observação"),
    ]

    resposta = models.ForeignKey(
        ChecklistProjetoResposta,
        on_delete=models.CASCADE,
        related_name="historico",
    )
    campo = models.CharField(max_length=20, choices=CAMPOS)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historicos_checklist_projetos",
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-alterado_em", "-id"]
        indexes = [
            models.Index(fields=["resposta", "campo", "-alterado_em"], name="proj_chk_hist_idx"),
        ]

    def __str__(self):
        return f"{self.resposta_id} · {self.get_campo_display()} · {self.alterado_em:%d/%m/%Y %H:%M}"


class AlteracaoProjeto(models.Model):
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.CASCADE,
        related_name="alteracoes_projeto",
    )
    descricao = models.TextField()
    disciplina = models.ForeignKey("cadastros.ChecklistProjetoGrupo", on_delete=models.PROTECT, null=True, blank=True, related_name="alteracoes_projeto")
    arquivo = models.FileField(upload_to="projetos/alteracoes/%Y/%m/")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alteracoes_projeto_criadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(fields=["obra", "-criado_em"], name="proj_alt_obra_data_idx"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.criado_em:%d/%m/%Y}"
