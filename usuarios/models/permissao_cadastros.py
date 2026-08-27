from django.contrib.auth.models import User
from django.db import models


class PermissaoCadastros(models.Model):
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="permissao_cadastros_erp",
        verbose_name="Usuário",
    )
    visualizar = models.BooleanField(default=True, verbose_name="Visualizar Cadastros")
    criar = models.BooleanField(default=False, verbose_name="Criar cadastros")
    editar = models.BooleanField(default=False, verbose_name="Editar cadastros")
    excluir = models.BooleanField(default=False, verbose_name="Excluir cadastros")
    administrar = models.BooleanField(default=False, verbose_name="Administrar Cadastros")
    ativo = models.BooleanField(default=True, verbose_name="Permissões de Cadastros ativas")
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Permissão de Cadastros"
        verbose_name_plural = "Permissões de Cadastros"

    def __str__(self):
        return f"{self.usuario.username} - Permissões de Cadastros"
