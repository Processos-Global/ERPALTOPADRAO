from django.core.paginator import Paginator
from django.shortcuts import render

from compras.models import PedidoCompra
from financeiro.services.compromissos import (
    contratos_assinados_separados,
    pedidos_comprometidos,
    totais_pedidos,
)
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra
from cadastros.models import Fornecedor


def _id_filtro(valor):
    return int(valor) if str(valor or "").isdigit() and int(valor) > 0 else None


@financeiro_acao_required("VISUALIZAR")
def compromissos_contratados(request):
    obra_id = _id_filtro(request.GET.get("obra"))
    fornecedor_id = _id_filtro(request.GET.get("fornecedor"))
    busca = (request.GET.get("q") or "").strip()[:120]
    status = (request.GET.get("status") or "").strip()
    pedidos = pedidos_comprometidos(
        obra_id=obra_id, fornecedor_id=fornecedor_id, busca=busca, status=status
    )
    contratos = contratos_assinados_separados(
        obra_id=obra_id, fornecedor_id=fornecedor_id, busca=busca
    )
    return render(request, "financeiro/compromissos.html", {
        "pagina": Paginator(pedidos, 25).get_page(request.GET.get("page")),
        "pagina_contratos": Paginator(contratos, 10).get_page(request.GET.get("page_contratos")),
        "totais": totais_pedidos(pedidos),
        "obras": Obra.objects.order_by("nome"),
        "fornecedores": Fornecedor.objects.order_by("nome"),
        "status_choices": PedidoCompra.Status.choices,
        "obra_id": obra_id,
        "fornecedor_id": fornecedor_id,
        "busca": busca,
        "status_filtro": status,
    })
