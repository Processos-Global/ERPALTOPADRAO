from django.core.paginator import Paginator
from django.shortcuts import render

from compras.models import PedidoCompra
from financeiro.services.agenda import _inteiro_positivo
from financeiro.services.compromissos import (
    contratos_assinados_separados,
    pedidos_comprometidos,
    totais_pedidos,
)
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra
from cadastros.models import Fornecedor


@financeiro_acao_required("VISUALIZAR")
def compromissos_contratados(request):
    obra_id = _inteiro_positivo(request.GET.get("obra"))
    fornecedor_id = _inteiro_positivo(request.GET.get("fornecedor"))
    busca = (request.GET.get("q") or "").strip()[:120]
    status = (request.GET.get("status") or "").strip()
    aba = request.GET.get("aba", "pedidos")
    filtros = {"obra_id": obra_id, "fornecedor_id": fornecedor_id, "busca": busca}
    contexto = {
        "obras": Obra.objects.order_by("nome"),
        "fornecedores": Fornecedor.objects.order_by("nome"),
        **filtros,
    }
    if aba == "contratos":
        contratos = contratos_assinados_separados(**filtros)
        contexto.update(
            aba="contratos",
            pagina=Paginator(contratos, 25).get_page(request.GET.get("page") or request.GET.get("page_contratos")),
        )
    else:
        pedidos = pedidos_comprometidos(**filtros, status=status)
        contexto.update(
            aba="pedidos", pagina=Paginator(pedidos, 25).get_page(request.GET.get("page")),
            totais=totais_pedidos(pedidos), status_choices=PedidoCompra.Status.choices, status_filtro=status,
        )
    return render(request, "financeiro/compromissos.html", contexto)
