from django.contrib import admin

from obras.models import Ambiente, Obra, Unidade


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = [
        "codigo",
        "nome",
        "tipo_obra",
        "status",
        "area_construida",
        "data_inicio_prevista",
        "ativa",
    ]

    list_filter = [
        "tipo_obra",
        "status",
        "ativa",
    ]

    search_fields = [
        "codigo",
        "nome",
        "nome_curto",
        "endereco",
    ]

    ordering = [
        "nome",
    ]


@admin.register(Ambiente)
class AmbienteAdmin(admin.ModelAdmin):
    list_display = [
        "nome",
        "obra",
        "tipo",
        "pavimento",
        "area",
        "ativo",
    ]

    list_filter = [
        "obra",
        "tipo",
        "ativo",
    ]

    search_fields = [
        "nome",
        "codigo",
        "obra__nome",
        "pavimento",
    ]

    ordering = [
        "obra",
        "ordem",
        "nome",
    ]


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = [
        "codigo",
        "nome",
        "obra",
        "tipo",
        "bloco",
        "pavimento",
        "ativa",
    ]

    list_filter = [
        "obra",
        "tipo",
        "ativa",
    ]

    search_fields = [
        "codigo",
        "nome",
        "obra__nome",
        "bloco",
        "pavimento",
    ]

    ordering = [
        "obra",
        "ordem",
        "codigo",
    ]