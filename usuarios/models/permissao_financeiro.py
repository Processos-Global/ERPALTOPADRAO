from django.contrib.auth.models import User
from django.db import models


class AcaoFinanceiro(models.TextChoices):
    VISUALIZAR = "VISUALIZAR", "Visualizar Financeiro"
    LANCAR_TITULOS = "LANCAR_TITULOS", "Lançar títulos"
    EDITAR_TITULOS = "EDITAR_TITULOS", "Editar títulos"
    APROVAR = "APROVAR", "Aprovar pagamentos"
    PAGAR = "PAGAR", "Registrar pagamentos"
    ADMINISTRAR = "ADMINISTRAR", "Administrar Financeiro"


class PermissaoFinanceiro(models.Model):
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="permissao_financeiro_erp",
        verbose_name="Usuário",
    )
    visualizar = models.BooleanField(default=True, verbose_name="Visualizar Financeiro")
    lancar_titulos = models.BooleanField(default=False, verbose_name="Lançar títulos")
    editar_titulos = models.BooleanField(default=False, verbose_name="Editar títulos")
    aprovar_pagamentos = models.BooleanField(default=False, verbose_name="Aprovar pagamentos")
    registrar_pagamentos = models.BooleanField(default=False, verbose_name="Registrar pagamentos")
    administrar = models.BooleanField(default=False, verbose_name="Administrar Financeiro")
    ativo = models.BooleanField(default=True, verbose_name="Permissões do Financeiro ativas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Permissão do Financeiro"
        verbose_name_plural = "Permissões do Financeiro"
        ordering = ["usuario__username"]

    def __str__(self):
        return f"{self.usuario.username} - Permissões do Financeiro"
