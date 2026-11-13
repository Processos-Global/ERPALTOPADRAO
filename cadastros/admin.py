from django.contrib import admin

from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida
from .models.pos_obra import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
class ClienteConsultaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):return False
    def has_change_permission(self, request, obj=None):return False
    def has_delete_permission(self, request, obj=None):return False

for _modelo in (Cliente, VinculoCliente):
    if not admin.site.is_registered(_modelo):admin.site.register(_modelo,ClienteConsultaAdmin)
for _modelo in (EmpreendimentoPosObra, CategoriaOcorrencia, TipoProblema):
    if not admin.site.is_registered(_modelo):
        admin.site.register(_modelo)
