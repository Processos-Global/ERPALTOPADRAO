from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from cadastros.models import Fornecedor
from financeiro.models import LiberacaoFinanceiraPedido
from financeiro.services.agenda import _inteiro_positivo
from financeiro.services.liberacoes import autorizar_liberacao
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from obras.models import Obra


def recorte_liberacoes(parametros):
    qs = LiberacaoFinanceiraPedido.objects.select_related(
        "pedido__obra", "pedido__fornecedor", "recebimento", "titulo", "autorizado_por",
    )
    status = parametros.get("status", "")
    if status in LiberacaoFinanceiraPedido.Status.values:
        qs = qs.filter(status=status)
    elif parametros.get("pendencias") == "1":
        qs = qs.filter(status__in=[LiberacaoFinanceiraPedido.Status.PENDENTE, LiberacaoFinanceiraPedido.Status.DIVERGENTE])
    for chave, campo in (("obra", "pedido__obra_id"), ("pedido", "pedido_id"), ("fornecedor", "pedido__fornecedor_id")):
        if identificador := _inteiro_positivo(parametros.get(chave)):
            qs = qs.filter(**{campo: identificador})
    busca = parametros.get("q", "").strip()[:120]
    if busca:
        qs = qs.filter(Q(pedido__numero__icontains=busca) | Q(pedido__processo__numero__icontains=busca))
    return qs


@financeiro_acao_required("VISUALIZAR")
def liberacoes_lista(request):
    qs = recorte_liberacoes(request.GET)
    return render(request, "financeiro/liberacoes.html", {
        "pagina": Paginator(qs, 25).get_page(request.GET.get("page")),
        "status_choices": LiberacaoFinanceiraPedido.Status.choices,
        "obras": Obra.objects.order_by("nome"),
        "fornecedores": Fornecedor.objects.order_by("nome"),
        "status_filtro": request.GET.get("status", ""), "obra_filtro": request.GET.get("obra", ""),
        "pedido_filtro": request.GET.get("pedido", ""), "fornecedor_filtro": request.GET.get("fornecedor", ""),
        "busca": request.GET.get("q", "").strip()[:120],
        "pode_autorizar": possui_acao_financeiro(request.user, "APROVAR"),
        "pode_reprocessar": possui_acao_financeiro(request.user, "EDITAR_TITULOS"),
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


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def liberacao_reprocessar(request, pk):
    from financeiro.services.solicitacoes_recebimentos import reprocessar_solicitacao_recebimento

    registro = get_object_or_404(
        recorte_liberacoes({}), pk=pk, recebimento__isnull=False, valor_esperado__isnull=False,
    )
    try:
        resultado = reprocessar_solicitacao_recebimento(registro.recebimento, usuario=request.user)
        if resultado.status == LiberacaoFinanceiraPedido.Status.DIVERGENTE:
            messages.warning(request, resultado.divergencia)
        elif resultado.titulo_id:
            messages.success(request, "Solicitação financeira gerada para o recebimento.")
        else:
            messages.success(request, "Recebimento integralmente compensado pela antecipação.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(reverse("financeiro:liberacoes", query={"pedido": registro.pedido_id}))
