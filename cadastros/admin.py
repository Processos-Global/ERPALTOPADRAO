from django.contrib import admin

from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida


@admin.register(UnidadeMedida)
class UnidadeMedidaAdmin(admin.ModelAdmin):
    list_display = ("sigla", "descricao", "ativo")
    search_fields = ("sigla", "descricao")
    list_filter = ("ativo",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "especificacao", "unidade", "ativo")
    search_fields = ("codigo", "nome", "especificacao")
    list_filter = ("ativo", "unidade")
    list_select_related = ("unidade",)


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome", "nome_fantasia", "documento", "email", "telefone", "avaliacao", "ativo")
    search_fields = ("codigo", "nome", "nome_fantasia", "documento", "email")
    list_filter = ("ativo", "estado")


@admin.register(MaoObra)
class MaoObraAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "categoria", "unidade", "ativo")
    search_fields = ("codigo", "descricao", "categoria")
    list_filter = ("ativo", "categoria", "unidade")
