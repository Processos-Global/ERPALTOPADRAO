from django.contrib import admin

from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida
from .models.pos_obra import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
for _modelo in (Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema):
    if not admin.site.is_registered(_modelo):
        admin.site.register(_modelo)
