from django.conf import settings
from django.db import models

from obras.models import Obra


class InsumoOrcamento(models.Model):
    class Tipo(models.TextChoices):
        FASE = "F", "Fase"
        SERVICO = "S", "Serviço"
        INSUMO = "I", "Insumo"

    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name="insumos_orcamento",
        verbose_name="Obra",
    )

    nr = models.CharField(max_length=30, blank=True, default="", verbose_name="NR")

    tipo = models.CharField(
        max_length=1,
        choices=Tipo.choices,
        blank=True,
        default="",
        verbose_name="Tipo",
    )

    codigo = models.CharField(max_length=60, blank=True, default="", verbose_name="Código")

    alternativo = models.CharField(max_length=60, blank=True, default="", verbose_name="Alternativo")

    codigo_ins = models.CharField(max_length=60, blank=True, default="", verbose_name="Código insumo")

    svc_in_mega = models.CharField(max_length=60, blank=True, default="", verbose_name="SVC_IN_MEGA")

    descricao = models.CharField(max_length=500, blank=True, default="", verbose_name="Descrição")

    unid = models.CharField(max_length=20, blank=True, default="", verbose_name="Unidade")

    quant = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="Quantidade"
    )

    custo = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="Custo"
    )

    total = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Total"
    )

    data_custo = models.DateField(null=True, blank=True, verbose_name="Data custo")

    pro_in_mega = models.CharField(max_length=60, blank=True, default="", verbose_name="PRO_IN_MEGA")

    imp = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True, verbose_name="IMP"
    )

    encbdi = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True, verbose_name="ENCBDI"
    )

    encsociais = models.DecimalField(
        max_digits=9, decimal_places=4, null=True, blank=True, verbose_name="ENCSOCIAIS"
    )

    descricao_grupo = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Descrição do grupo"
    )

    natureza = models.CharField(max_length=120, blank=True, default="", verbose_name="Natureza")

    classe_financeira = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Classe financeira"
    )

    classe_gerencial = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Classe gerencial"
    )

    classe_macro = models.CharField(
        max_length=120, blank=True, default="", verbose_name="Classe macro"
    )

    mao_de_obra = models.BooleanField(default=False, verbose_name="Mão de obra")

    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")

    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Insumo de orçamento"
        verbose_name_plural = "Insumos de orçamento"
        ordering = ["obra", "codigo"]
        indexes = [
            models.Index(fields=["obra", "tipo"], name="orcamento_insumo_obra_tipo_idx"),
            models.Index(fields=["obra", "codigo"], name="orcamento_insumo_obra_cod_idx"),
            models.Index(fields=["mao_de_obra"], name="orcamento_insumo_mao_obra_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"


class ArquivoOrcamentoObra(models.Model):
    """Guarda o hash do último CSV de orçamento importado para cada obra."""

    obra = models.OneToOneField(
        Obra,
        on_delete=models.CASCADE,
        related_name="arquivo_orcamento",
        verbose_name="Obra",
    )

    nome_arquivo = models.CharField(max_length=255, blank=True, default="", verbose_name="Nome do arquivo")

    arquivo_drive_id = models.CharField(max_length=120, blank=True, default="", verbose_name="ID no Drive")

    hash_arquivo = models.CharField(max_length=64, blank=True, default="", verbose_name="Hash do arquivo")

    estrutura_eap_detectada = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Estrutura EAP detectada"
    )

    quantidade_itens = models.PositiveIntegerField(default=0, verbose_name="Quantidade de itens")

    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Arquivo de orçamento por obra"
        verbose_name_plural = "Arquivos de orçamento por obra"
        ordering = ["obra"]

    def __str__(self):
        return f"{self.obra} - {self.nome_arquivo}"


class ImportacaoOrcamento(models.Model):
    class Status(models.TextChoices):
        PROCESSANDO = "PROCESSANDO", "Processando"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        FALHOU = "FALHOU", "Falhou"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROCESSANDO, verbose_name="Status"
    )

    obras_criadas = models.PositiveIntegerField(default=0, verbose_name="Obras criadas")

    obras_atualizadas = models.PositiveIntegerField(default=0, verbose_name="Obras atualizadas")

    obras_ignoradas = models.PositiveIntegerField(default=0, verbose_name="Obras ignoradas (sem alteração)")

    total_itens_importados = models.PositiveIntegerField(default=0, verbose_name="Total de itens importados")

    mensagem = models.TextField(blank=True, default="", verbose_name="Mensagem")

    erro_detalhado = models.TextField(blank=True, default="", verbose_name="Erro detalhado")

    executado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_orcamento",
        verbose_name="Executado por",
    )

    iniciou_em = models.DateTimeField(null=True, blank=True, verbose_name="Iniciou em")

    finalizou_em = models.DateTimeField(null=True, blank=True, verbose_name="Finalizou em")

    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")

    class Meta:
        verbose_name = "Importação de orçamento"
        verbose_name_plural = "Importações de orçamento"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Importação de orçamento #{self.pk} - {self.get_status_display()}"
