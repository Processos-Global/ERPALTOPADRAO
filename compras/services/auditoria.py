from compras.models import HistoricoProcessoCompra

def registrar_evento(processo, tipo, usuario, descricao, dados=None):
    return HistoricoProcessoCompra.objects.create(
        processo=processo, tipo=tipo, usuario=usuario, descricao=descricao, dados=dados or {}
    )
