from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from financeiro.models import LiberacaoFinanceiraPedido
from financeiro.services.liberacoes import autorizar_liberacao
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def liberacoes_lista(request):
    qs = LiberacaoFinanceiraPedido.objects.select_related(
        "pedido__obra", "pedido__fornecedor", "recebimento", "titulo", "autorizado_por",
    )
    status = request.GET.get("status", "")
    if status in LiberacaoFinanceiraPedido.Status.values:
        qs = qs.filter(status=status)
    obra = request.GET.get("obra", "")
    if obra.isdigit():
        qs = qs.filter(pedido__obra_id=int(obra))
    pedido = request.GET.get("pedido", "")
    if pedido.isdigit():
        qs = qs.filter(pedido_id=int(pedido))
    return render(request, "financeiro/liberacoes.html", {
        "pagina": Paginator(qs, 25).get_page(request.GET.get("page")),
        "status_choices": LiberacaoFinanceiraPedido.Status.choices,
        "obras": Obra.objects.order_by("nome"),
        "status_filtro": status, "obra_filtro": obra, "pedido_filtro": pedido,
        "pode_autorizar": possui_acao_financeiro(request.user, "APROVAR"),
    })


@financeiro_acao_required("APROVAR")
@require_POST
def liberacao_autorizar(request, pk):
    liberacao = get_object_or_404(LiberacaoFinanceiraPedido, pk=pk)
    try:
        titulo = autorizar_liberacao(liberacao, usuario=request.user)
        if titulo:
            messages.success(request, f"Liberação registrada no título {titulo.numero}. Prepare o título para aprovação.")
        else:
            messages.success(request, "Recebimento totalmente coberto por antecipação; nenhum novo título foi criado.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:liberacoes")
