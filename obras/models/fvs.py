from django.conf import settings
from django.db import models

from cadastros.models import ModeloFVS
from .ficha_tecnica import AmbienteFichaTecnica
from .obra import Obra


class FVS(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        EM_PREENCHIMENTO = "EM_PREENCHIMENTO", "Em preenchimento"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        DEVOLVIDA = "DEVOLVIDA", "Devolvida para correção"
        APROVADA = "APROVADA", "Aprovada pelo gestor"

    class Parecer(models.TextChoices):
        APROVADA = "APROVADA", "Aprovada"
        APROVADA_RESTRICAO = "APROVADA_RESTRICAO", "Aprovada com restrição"
        REPROVADA = "REPROVADA", "Reprovada"

    numero = models.CharField(max_length=30, unique=True, blank=True, verbose_name="Número")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="fvs", verbose_name="Obra")
    modelo_origem = models.ForeignKey(ModeloFVS, on_delete=models.PROTECT, related_name="fvs_geradas", verbose_name="Modelo de origem")
    modelo_nome = models.CharField(max_length=180, verbose_name="Modelo")
    modelo_revisao = models.CharField(max_length=30, verbose_name="Revisão")
    normas_referencias = models.TextField(blank=True, verbose_name="Normas / referências")
    ambientes = models.ManyToManyField(AmbienteFichaTecnica, related_name="fvs", verbose_name="Ambientes")
    pavimento_etapa = models.CharField(max_length=120, blank=True, verbose_name="Pavimento / etapa")
    empresa_executora = models.CharField(max_length=180, blank=True, verbose_name="Empresa executora")
    responsavel_execucao = models.CharField(max_length=180, blank=True, verbose_name="Responsável pela execução")
    responsavel_inspecao = models.CharField(max_length=180, blank=True, verbose_name="Responsável pela inspeção")
    projeto_versao = models.CharField(max_length=180, blank=True, verbose_name="Projeto / versão")
    data_abertura = models.DateField(auto_now_add=True, verbose_name="Data de abertura")
    data_fechamento = models.DateField(null=True, blank=True, verbose_name="Data de fechamento")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.RASCUNHO, verbose_name="Status")
    parecer = models.CharField(max_length=30, choices=Parecer.choices, blank=True, verbose_name="Parecer técnico")
    observacao_final = models.TextField(blank=True, verbose_name="Observação final")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fvs_criadas", verbose_name="Criado por")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    enviado_aprovacao_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fvs_enviadas_aprovacao", null=True, blank=True)
    enviado_aprovacao_em = models.DateTimeField(null=True, blank=True)
    aprovado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fvs_aprovadas", null=True, blank=True)
    aprovado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "FVS"
        verbose_name_plural = "FVS"
        ordering = ["-criado_em"]
        permissions = [("aprovar_fvs", "Pode aprovar e devolver FVS")]
        indexes = [
            models.Index(fields=["obra", "status"], name="obras_fvs_obra_status_idx"),
            models.Index(fields=["status", "criado_em"], name="obras_fvs_status_data_idx"),
        ]

    def __str__(self):
        return self.numero or f"FVS #{self.pk or 'nova'}"

    @property
    def pode_editar(self):
        return self.status in {self.Status.RASCUNHO, self.Status.EM_PREENCHIMENTO, self.Status.DEVOLVIDA}

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.numero:
            self.numero = f"FVS-{self.criado_em.year}-{self.pk:04d}"
            type(self).objects.filter(pk=self.pk).update(numero=self.numero)


class FVSItem(models.Model):
    class Resultado(models.TextChoices):
        CONFORME = "C", "Conforme"
        NAO_CONFORME = "NC", "Não conforme"
        NAO_APLICAVEL = "NA", "Não aplicável"

    fvs = models.ForeignKey(FVS, on_delete=models.CASCADE, related_name="itens", verbose_name="FVS")
    ordem = models.PositiveIntegerField(default=1)
    item_verificacao = models.CharField(max_length=255)
    metodo_instrumento = models.CharField(max_length=255, blank=True)
    criterio_aceite = models.TextField(blank=True)
    tolerancia = models.TextField(blank=True)
    obrigatorio = models.BooleanField(default=True)
    resultado = models.CharField(max_length=2, choices=Resultado.choices, blank=True, verbose_name="Resultado")
    data_verificacao = models.DateField(null=True, blank=True, verbose_name="Data da verificação")
    observacao = models.TextField(blank=True, verbose_name="Observações / ações corretivas")

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "Item da FVS"
        verbose_name_plural = "Itens da FVS"

    def __str__(self):
        return f"{self.fvs.numero} · {self.ordem:02d}"


class FVSHistorico(models.Model):
    class Acao(models.TextChoices):
        CRIADA = "CRIADA", "Criada"
        SALVA = "SALVA", "Preenchimento salvo"
        ENVIADA = "ENVIADA", "Enviada para aprovação"
        DEVOLVIDA = "DEVOLVIDA", "Devolvida para correção"
        APROVADA = "APROVADA", "Aprovada pelo gestor"

    fvs = models.ForeignKey(FVS, on_delete=models.CASCADE, related_name="historico")
    acao = models.CharField(max_length=20, choices=Acao.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="historico_fvs")
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Histórico da FVS"
        verbose_name_plural = "Históricos da FVS"
