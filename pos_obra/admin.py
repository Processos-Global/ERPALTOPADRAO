"""Admin de apoio: OS encerradas e registros de auditoria são apenas consultáveis."""
from django import forms
from django.contrib import admin
from .models import Chamado, MaterialOS, RegistroChamado, AnexoChamado, PesquisaSatisfacao

ENCERRADOS = ('CONCLUIDO', 'CANCELADO')


class ChamadoAdminForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        if data.get('status') == 'CONCLUIDO' and self.instance.status != 'CONCLUIDO':
            self.add_error('status', 'Finalize o chamado na tela de Pós-Obra, com a documentação exigida.')
        return data


class ChamadoRelacionadoAdminForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        chamado = data.get('chamado')
        if chamado and chamado.status in ENCERRADOS:
            # Compartilhar um anexo existente é a única edição permitida após encerramento.
            apenas_visibilidade = (isinstance(self.instance, AnexoChamado) and self.instance.pk
                                    and set(self.changed_data) <= {'publico'})
            if not apenas_visibilidade:
                raise forms.ValidationError('Os dados de uma OS encerrada não podem ser alterados.')
        return data


class EncerramentoAdminMixin:
    def chamado_encerrado(self, obj):
        if obj is None:
            return False
        chamado = obj if isinstance(obj, Chamado) else obj.chamado
        return chamado.status in ENCERRADOS

    def has_change_permission(self, request, obj=None):
        return not self.chamado_encerrado(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self.chamado_encerrado(obj) and super().has_delete_permission(request, obj)


@admin.register(Chamado)
class ChamadoAdmin(EncerramentoAdminMixin, admin.ModelAdmin):
    form = ChamadoAdminForm
    list_display = ('numero', 'cliente', 'empreendimento', 'status', 'criado_em')
    list_filter = ('status', 'origem')
    search_fields = ('numero', 'cliente__nome')
    readonly_fields = ('numero', 'criado_em', 'atualizado_em', 'finalizado_em')

    def has_add_permission(self, request):
        return False


@admin.register(MaterialOS)
class MaterialOSAdmin(EncerramentoAdminMixin, admin.ModelAdmin):
    form = ChamadoRelacionadoAdminForm


@admin.register(AnexoChamado)
class AnexoChamadoAdmin(admin.ModelAdmin):
    form = ChamadoRelacionadoAdminForm

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.chamado.status in ENCERRADOS:
            return ('chamado', 'etapa', 'arquivo', 'criado_em')
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.chamado.status in ENCERRADOS) and super().has_delete_permission(request, obj)


class SomenteConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(RegistroChamado, SomenteConsultaAdmin)
admin.site.register(PesquisaSatisfacao, SomenteConsultaAdmin)
