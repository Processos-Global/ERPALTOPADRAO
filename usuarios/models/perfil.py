from django.contrib.auth.models import User
from django.db import models


class PerfilUsuario(models.Model):
    class Cargo(models.TextChoices):
        DIRETORIA = "DIRETORIA", "Diretoria"
        GERENCIA = "GERENCIA", "Gerência"
        ENGENHARIA = "ENGENHARIA", "Engenharia"
        PLANEJAMENTO = "PLANEJAMENTO", "Planejamento"
        SUPRIMENTOS = "SUPRIMENTOS", "Suprimentos"
        COMPRAS = "COMPRAS", "Compras"
        FINANCEIRO = "FINANCEIRO", "Financeiro"
        ALMOXARIFADO = "ALMOXARIFADO", "Almoxarifado"
        PROJETOS = "PROJETOS", "Projetos"
        POS_OBRA = "POS_OBRA", "Pós-obra"
        ADMINISTRATIVO = "ADMINISTRATIVO", "Administrativo"
        OUTRO = "OUTRO", "Outro"

    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="perfil_erp",
        verbose_name="Usuário",
    )

    cargo = models.CharField(
        max_length=30,
        choices=Cargo.choices,
        default=Cargo.OUTRO,
        verbose_name="Cargo/setor",
    )

    telefone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Telefone",
    )

    foto = models.ImageField(
        upload_to="usuarios/perfis/",
        null=True,
        blank=True,
        verbose_name="Foto",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Perfil ativo",
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
        verbose_name = "Perfil de usuário"
        verbose_name_plural = "Perfis de usuários"
        ordering = [
            "usuario__first_name",
            "usuario__username",
        ]

    def __str__(self):
        nome = self.usuario.get_full_name()

        return nome or self.usuario.username