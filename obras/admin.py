from django.contrib import admin

from obras.models import Ambiente, DiarioObra, MovimentoEstoque, Obra, Unidade


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nome", "tipo_obra", "status", "area_construida", "data_inicio_prevista", "ativa"]
    list_filter = ["tipo_obra", "status", "ativa"]
    search_fields = ["codigo", "nome", "nome_curto", "endereco"]
    ordering = ["nome"]


@admin.register(Ambiente)
class AmbienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "obra", "tipo", "pavimento", "area", "ativo"]
    list_filter = ["obra", "tipo", "ativo"]
    search_fields = ["nome", "codigo", "obra__nome", "pavimento"]
    ordering = ["obra", "ordem", "nome"]


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nome", "obra", "tipo", "bloco", "pavimento", "ativa"]
    list_filter = ["obra", "tipo", "ativa"]
    search_fields = ["codigo", "nome", "obra__nome", "bloco", "pavimento"]
    ordering = ["obra", "ordem", "codigo"]


@admin.register(MovimentoEstoque)
class MovimentoEstoqueAdmin(admin.ModelAdmin):
    list_display = ["data_movimento", "tipo", "obra_origem", "obra_destino", "descricao_item", "quantidade", "unidade", "criado_por"]
    list_filter = ["tipo", "obra_origem", "obra_destino"]
    search_fields = ["descricao_item", "documento_referencia", "obra_origem__nome", "obra_destino__nome"]
    readonly_fields = ["criado_em"]


@admin.register(DiarioObra)
class DiarioObraAdmin(admin.ModelAdmin):
    list_display = ["data", "obra", "clima", "efetivo", "registrado_por", "atualizado_em"]
    list_filter = ["obra", "clima", "data"]
    search_fields = ["obra__nome", "obra__codigo", "servicos_executados", "ocorrencias"]
    readonly_fields = ["criado_em", "atualizado_em"]
