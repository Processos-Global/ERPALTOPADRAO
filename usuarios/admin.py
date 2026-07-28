from django.contrib import admin

from usuarios.models import (
    PerfilUsuario,
    PermissaoModulo,
)


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "cargo",
        "ativo",
        "criado_em",
    ]

    list_filter = [
        "cargo",
        "ativo",
    ]

    search_fields = [
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    ]

    autocomplete_fields = [
        "usuario",
    ]


@admin.register(PermissaoModulo)
class PermissaoModuloAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "modulo",
        "nivel",
        "ativo",
    ]

    list_filter = [
        "modulo",
        "nivel",
        "ativo",
    ]

    search_fields = [
        "usuario__username",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    ]

    autocomplete_fields = [
        "usuario",
    ]

    ordering = [
        "usuario__username",
        "modulo",
    ]