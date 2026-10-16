from django.conf import settings
from django.db import models


class PermissaoAcao(models.Model):
    """Permissão explícita por ação para módulos sem modelo específico."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="permissoes_acoes_erp")
    modulo = models.CharField(max_length=30)
    acao = models.CharField(max_length=70)
    permitido = models.BooleanField(default=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Permissão de ação"
        verbose_name_plural = "Permissões de ações"
        constraints = [models.UniqueConstraint(fields=["usuario", "modulo", "acao"], name="usr_acao_usuario_modulo_acao_un")]
        indexes = [models.Index(fields=["usuario", "modulo"], name="usr_acao_usr_mod_idx")]
