from django.contrib.auth.models import User
from django.db import models


class AcaoCompra(models.TextChoices):
    VISUALIZAR = "VISUALIZAR", "Visualizar Compras"
    SOLICITAR = "SOLICITAR", "Solicitar compra"
    COTAR = "COTAR", "Executar cotação"
    COMPATIBILIZAR = "COMPATIBILIZAR", "Compatibilizar tecnicamente"
    NEGOCIAR = "NEGOCIAR", "Negociar"
    APROVAR = "APROVAR", "Aprovar compra"
    GERENCIAR_PEDIDOS = "GERENCIAR_PEDIDOS", "Gerenciar pedidos"
    RECEBER_PEDIDOS = "RECEBER_PEDIDOS", "Registrar recebimentos"
    CANCELAR_PEDIDOS = "CANCELAR_PEDIDOS", "Cancelar pedidos"
    ADMINISTRAR = "ADMINISTRAR", "Administrar Compras"


class PermissaoCompras(models.Model):
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="permissao_compras_erp",
        verbose_name="Usuário",
    )

    visualizar = models.BooleanField(
        default=True,
        verbose_name="Visualizar Compras",
    )

    solicitar_compra = models.BooleanField(
        default=False,
        verbose_name="Solicitar compra",
    )

    executar_cotacao = models.BooleanField(
        default=False,
        verbose_name="Executar cotação",
    )

    compatibilizar = models.BooleanField(
        default=False,
        verbose_name="Compatibilizar tecnicamente",
    )

    negociar = models.BooleanField(
        default=False,
        verbose_name="Negociar",
    )

    aprovar_compra = models.BooleanField(
        default=False,
        verbose_name="Aprovar compra",
    )

    gerenciar_pedidos = models.BooleanField(
        default=False,
        verbose_name="Gerenciar pedidos",
    )

    receber_pedidos = models.BooleanField(
        default=False,
        verbose_name="Registrar recebimentos",
    )

    cancelar_pedidos = models.BooleanField(
        default=False,
        verbose_name="Cancelar pedidos",
    )

    administrar = models.BooleanField(
        default=False,
        verbose_name="Administrar Compras",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Permissões de Compras ativas",
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
        verbose_name = "Permissão de Compras"
        verbose_name_plural = "Permissões de Compras"
        ordering = [
            "usuario__username",
        ]

    def __str__(self):
        return f"{self.usuario.username} - Permissões de Compras"
