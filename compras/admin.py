from django.contrib import admin
from compras.models import *

MODELOS = [
    FornecedorCompra, ProcessoCompra, ProcessoCompraAtividade, NecessidadeCompra,
    CotacaoFornecedor, CotacaoFornecedorItem, CompatibilizacaoItem, NegociacaoItem,
    HistoricoNegociacaoItem, AdjudicacaoCompra, AlcadaAprovacaoCompra, AprovacaoCompra,
    ContratacaoCompra, PedidoCompra, PedidoCompraItem, ParcelaPrevistaPedido,
    HistoricoPrevisaoPedido, HistoricoProcessoCompra, SequenciaDocumentoCompra,
]
for model in MODELOS:
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
