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


# Concretagem
from obras.models import (  # noqa: E402
    Concretagem, ContatoEmailConcreteira, EnderecoEntregaSalvo, HistoricoConcretagem,
    ItemConcretagemPlanejado, LocalUsoObra,
)


class ItemConcretagemPlanejadoInline(admin.TabularInline):
    model = ItemConcretagemPlanejado
    extra = 0


class HistoricoConcretagemInline(admin.TabularInline):
    model = HistoricoConcretagem
    extra = 0
    can_delete = False
    readonly_fields = ["criado_em", "usuario", "acao", "status_anterior", "status_novo", "observacao"]


@admin.register(Concretagem)
class ConcretagemAdmin(admin.ModelAdmin):
    list_display = ["codigo", "obra", "data_programada", "concreteira", "volume_solicitado", "status"]
    list_filter = ["status", "obra"]
    search_fields = ["codigo", "obra__nome", "concreteira__nome"]
    readonly_fields = ["codigo", "token_confirmacao", "criado_em", "atualizado_em"]
    inlines = [ItemConcretagemPlanejadoInline, HistoricoConcretagemInline]


@admin.register(LocalUsoObra)
class LocalUsoObraAdmin(admin.ModelAdmin):
    list_display = ["nome", "obra", "tipo", "bloco", "pavimento", "ativo"]
    list_filter = ["obra", "tipo", "ativo"]
    search_fields = ["nome", "obra__nome"]


admin.site.register(EnderecoEntregaSalvo)
admin.site.register(ContatoEmailConcreteira)


from obras.models import (  # noqa: E402
    AnexoConcretagem, CaminhaoConcretagem, FichaMoldagem, LaudoConcretagem, SobraConcreto, UtilizacaoConcreto,
)


@admin.register(CaminhaoConcretagem)
class CaminhaoConcretagemAdmin(admin.ModelAdmin):
    list_display = ["concretagem", "ordem", "placa", "numero_nota_fiscal", "volume_entregue", "cps_moldados", "ativo"]
    list_filter = ["ativo"]
    search_fields = ["concretagem__codigo", "placa", "numero_nota_fiscal"]


@admin.register(LaudoConcretagem)
class LaudoConcretagemAdmin(admin.ModelAdmin):
    list_display = ["concretagem", "idade_dias", "resistencia_mpa", "lancado_em"]
    list_filter = ["idade_dias"]


@admin.register(AnexoConcretagem)
class AnexoConcretagemAdmin(admin.ModelAdmin):
    list_display = ["concretagem", "etapa", "nome_original", "status", "tentativas", "ativo", "criado_em"]
    list_filter = ["status", "etapa", "ativo"]
    readonly_fields = ["drive_id", "drive_url", "ultimo_erro", "tentativas"]


admin.site.register(UtilizacaoConcreto)
admin.site.register(SobraConcreto)
admin.site.register(FichaMoldagem)
