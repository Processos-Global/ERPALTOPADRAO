from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ModuloNotificacao(models.TextChoices):
    SISTEMA = "SISTEMA", "Sistema"
    COMPRAS = "COMPRAS", "Compras"
    PLANEJAMENTO = "PLANEJAMENTO", "Planejamento"


class TipoNotificacao(models.TextChoices):
    INFORMACAO = "INFORMACAO", "Informação"
    SUCESSO = "SUCESSO", "Sucesso"
    ATENCAO = "ATENCAO", "Atenção"
    ACAO = "ACAO", "Ação necessária"


class Notificacao(models.Model):
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notificacoes_erp",
        verbose_name="Usuário",
    )

    titulo = models.CharField(
        max_length=160,
        verbose_name="Título",
    )

    mensagem = models.CharField(
        max_length=500,
        verbose_name="Mensagem",
    )

    modulo = models.CharField(
        max_length=30,
        choices=ModuloNotificacao.choices,
        default=ModuloNotificacao.SISTEMA,
        db_index=True,
        verbose_name="Módulo",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TipoNotificacao.choices,
        default=TipoNotificacao.INFORMACAO,
        db_index=True,
        verbose_name="Tipo",
    )

    evento = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Evento",
    )

    url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Destino",
    )

    chave_unica = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Chave única",
    )

    dados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dados adicionais",
    )

    lida = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Lida",
    )

    lida_em = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Lida em",
    )

    criada_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criada em",
    )

    atualizada_em = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name="Atualizada em",
    )

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ["-atualizada_em", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "chave_unica"],
                name="usuarios_notificacao_usuario_chave_unica",
            )
        ]
        indexes = [
            models.Index(
                fields=["usuario", "lida", "atualizada_em"],
                name="usuarios_notif_user_lida_idx",
            ),
        ]

    def __str__(self):
        return f"{self.usuario.username} - {self.titulo}"

    def marcar_como_lida(self, salvar=True):
        if self.lida:
            return self

        self.lida = True
        self.lida_em = timezone.now()

        if salvar:
            self.save(update_fields=["lida", "lida_em"])

        return self
