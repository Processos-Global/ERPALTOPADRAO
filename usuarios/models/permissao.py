from django.contrib.auth.models import User
from django.db import models


class ModuloSistema(models.TextChoices):
    OBRAS = "OBRAS", "Obras"
    PLANEJAMENTO = "PLANEJAMENTO", "Planejamento"
    SUPRIMENTOS = "SUPRIMENTOS", "Suprimentos"
    COMPRAS = "COMPRAS", "Compras"
    CONTRATOS = "CONTRATOS", "Contratos"
    FINANCEIRO = "FINANCEIRO", "Financeiro"
    ALMOXARIFADO = "ALMOXARIFADO", "Almoxarifado"
    PROJETOS = "PROJETOS", "Projetos"
    VISTORIAS = "VISTORIAS", "Vistorias"
    DIARIO_OBRA = "DIARIO_OBRA", "Diário de obra"
    POS_OBRA = "POS_OBRA", "Pós-obra"
    RELATORIOS = "RELATORIOS", "Relatórios"
    INTEGRACOES = "INTEGRACOES", "Integrações"
    USUARIOS = "USUARIOS", "Usuários e permissões"


class NivelPermissao(models.TextChoices):
    LEITURA = "LEITURA", "Somente leitura"
    EDICAO = "EDICAO", "Leitura e edição"
    APROVACAO = (
        "APROVACAO",
        "Leitura, edição e aprovação",
    )
    ADMINISTRADOR = (
        "ADMINISTRADOR",
        "Administrador do módulo",
    )


class PermissaoModulo(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="permissoes_modulos_erp",
        verbose_name="Usuário",
    )

    modulo = models.CharField(
        max_length=30,
        choices=ModuloSistema.choices,
        verbose_name="Módulo",
    )

    nivel = models.CharField(
        max_length=20,
        choices=NivelPermissao.choices,
        default=NivelPermissao.LEITURA,
        verbose_name="Nível de permissão",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Permissão ativa",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    class Meta:
        verbose_name = "Permissão de módulo"
        verbose_name_plural = "Permissões de módulos"

        ordering = [
            "usuario__username",
            "modulo",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "usuario",
                    "modulo",
                ],
                name="usr_perm_usu_mod_uniq",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "usuario",
                    "ativo",
                ],
                name="usr_perm_usu_ativo_idx",
            ),
            models.Index(
                fields=[
                    "modulo",
                    "nivel",
                ],
                name="usr_perm_mod_niv_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.usuario.username} - "
            f"{self.get_modulo_display()} - "
            f"{self.get_nivel_display()}"
        )