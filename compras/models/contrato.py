from decimal import Decimal

from django.conf import settings
from django.db import models

from core.storage import private_media_storage


class ContratoCompra(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        DEVOLVIDO = "DEVOLVIDO", "Devolvido para correção"
        REPROVADO = "REPROVADO", "Reprovado"
        APROVADO = "APROVADO", "Aprovado"
        AGUARDANDO_ASSINATURA = "AGUARDANDO_ASSINATURA", "Aguardando assinatura"
        ASSINADO = "ASSINADO", "Assinado"

    numero = models.CharField(max_length=24, unique=True, db_index=True)
    processo = models.ForeignKey(
        "compras.ProcessoCompra",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contratos",
    )
    obra = models.ForeignKey(
        "obras.Obra",
        on_delete=models.PROTECT,
        related_name="contratos_compra",
    )
    fornecedor = models.ForeignKey(
        "cadastros.Fornecedor",
        on_delete=models.PROTECT,
        related_name="contratos_compra",
    )

    # Snapshot cadastral/comercial. O contrato não muda caso o cadastro seja alterado depois.
    contratado_razao_social = models.CharField(max_length=255)
    contratado_cnpj = models.CharField(max_length=32, blank=True)
    contratado_endereco = models.CharField(max_length=500, blank=True)
    contratado_email = models.EmailField(blank=True)

    representante_nome = models.CharField(max_length=255, blank=True)
    representante_nacionalidade = models.CharField(max_length=80, blank=True, default="brasileiro(a)")
    representante_estado_civil = models.CharField(max_length=80, blank=True)
    representante_profissao = models.CharField(max_length=120, blank=True)
    representante_cpf = models.CharField(max_length=32, blank=True)
    representante_endereco = models.CharField(max_length=500, blank=True)

    modalidade_fornecimento = models.CharField(
        max_length=255,
        default="somente com o fornecimento de mão-de-obra",
    )
    objeto_contrato = models.TextField()
    area_obra = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    descricao_ambientes_objeto = models.TextField(blank=True)
    escritorio_arquitetura = models.CharField(max_length=255, blank=True)
    responsavel_supervisao = models.CharField(max_length=255, blank=True)

    prazo_execucao = models.CharField(max_length=120)
    multa_atraso = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("1500.00"))
    valor_total = models.DecimalField(max_digits=18, decimal_places=2)

    favorecido_nome = models.CharField(max_length=255, blank=True)
    favorecido_documento_tipo = models.CharField(max_length=10, blank=True, default="CNPJ")
    favorecido_documento = models.CharField(max_length=32, blank=True)
    banco = models.CharField(max_length=120, blank=True)
    agencia = models.CharField(max_length=50, blank=True)
    conta = models.CharField(max_length=80, blank=True)
    operacao = models.CharField(max_length=50, blank=True)
    pix = models.CharField(max_length=255, blank=True)

    avalista_1_nome = models.CharField(max_length=255, blank=True)
    avalista_1_cpf = models.CharField(max_length=32, blank=True)
    avalista_2_nome = models.CharField(max_length=255, blank=True)
    avalista_2_cpf = models.CharField(max_length=32, blank=True)

    cidade_assinatura = models.CharField(max_length=120, default="Brasília")
    data_contrato = models.DateField()

    observacoes_internas = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.RASCUNHO,
        db_index=True,
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contratos_compra_criados",
    )
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contratos_compra_aprovados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    enviado_aprovacao_em = models.DateTimeField(null=True, blank=True)
    decidido_em = models.DateTimeField(null=True, blank=True)
    assinado_em = models.DateTimeField(null=True, blank=True)
    motivo_decisao = models.TextField(blank=True)

    # Google Drive / Google Docs
    drive_folder_id = models.CharField(max_length=255, blank=True)
    google_doc_id = models.CharField(max_length=255, blank=True)
    google_doc_url = models.URLField(max_length=1000, blank=True)
    drive_assinado_id = models.CharField(max_length=255, blank=True)
    drive_assinado_url = models.URLField(max_length=1000, blank=True)

    arquivo_docx = models.FileField(
        storage=private_media_storage,
        upload_to="compras/contratos/gerados/%Y/%m/",
        blank=True,
    )
    arquivo_assinado = models.FileField(
        storage=private_media_storage,
        upload_to="compras/contratos/assinados/%Y/%m/",
        blank=True,
    )

    class Meta:
        ordering = ("-criado_em", "-id")
        indexes = [
            models.Index(fields=["status", "criado_em"], name="comp_cont_status_idx"),
            models.Index(fields=["obra", "status"], name="comp_cont_obra_idx"),
            models.Index(fields=["fornecedor", "status"], name="comp_cont_forn_idx"),
        ]

    def __str__(self):
        return f"{self.numero} - {self.contratado_razao_social}"

    @property
    def pode_editar(self):
        return self.status in {self.Status.RASCUNHO, self.Status.DEVOLVIDO}

    @property
    def aguardando_assinatura(self):
        return self.status in {self.Status.APROVADO, self.Status.AGUARDANDO_ASSINATURA}


class HistoricoContratoCompra(models.Model):
    contrato = models.ForeignKey(
        ContratoCompra,
        on_delete=models.CASCADE,
        related_name="historico",
    )
    evento = models.CharField(max_length=60)
    descricao = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historicos_contratos_compra",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em", "-id")

    def __str__(self):
        return f"{self.contrato.numero} - {self.evento}"
