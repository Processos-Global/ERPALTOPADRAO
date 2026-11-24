from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cadastros.models import Fornecedor
from financeiro.forms import PrevisaoFinanceiraForm
from financeiro.models import PlanoFinanceiro, PrevisaoFinanceira
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.services.planejamento_financeiro import (
    ORIGENS_PLANEJAMENTO, recorte_planejamento, resumo_planejamento, rotular_linha_planejamento,
)
from financeiro.services.previsoes import sincronizar_todas_integracoes
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def previsoes_lista(request):
    recorte = recorte_planejamento(request.GET)
    resumo = resumo_planejamento(recorte)
    limite_grafico = max((valor for mes in resumo["por_mes"].values() for valor in mes.values()), default=Decimal("0"))
    page_obj = Paginator(recorte["linhas"], 40).get_page(request.GET.get("page"))
    page_obj.object_list = [rotular_linha_planejamento(linha) for linha in page_obj]

    fornecedor_id = recorte["filtros"]["fornecedor"]
    fornecedor = Fornecedor.objects.only("nome", "nome_fantasia").filter(pk=fornecedor_id).first() if fornecedor_id else None
    return render(request, "financeiro/previsoes.html", {
        "mes": recorte["mes"],
        "sem_data": recorte["sem_data"],
        "filtros": recorte["filtros"],
        "page_obj": page_obj,
        "origem_choices": ORIGENS_PLANEJAMENTO.items(),
        "certeza_choices": PrevisaoFinanceira.Certeza.choices,
        "obras": Obra.objects.order_by("nome", "pk").values("pk", "nome"),
        "planos": PlanoFinanceiro.objects.order_by("codigo", "pk").values("pk", "codigo", "nome"),
        "fornecedor": fornecedor,
        **resumo,
        "limite_grafico": max(Decimal("1"), limite_grafico),
        "pode_lancar": possui_acao_financeiro(request.user, "LANCAR_TITULOS"),
        "pode_editar": possui_acao_financeiro(request.user, "EDITAR_TITULOS"),
    })


@financeiro_acao_required("LANCAR_TITULOS")
def previsao_nova(request):
    if request.method == "POST":
        form = PrevisaoFinanceiraForm(request.POST)
        if form.is_valid():
            previsao = form.save(commit=False)
            previsao.origem = PrevisaoFinanceira.Origem.MANUAL
            previsao.certeza = PrevisaoFinanceira.Certeza.PREVISTO
            previsao.criado_por = request.user
            previsao.save()
            messages.success(request, "Solicitação avulsa de previsão criada. Ela não é uma Conta a Pagar até ser formalizada.")
            return redirect("financeiro:previsoes")
    else:
        form = PrevisaoFinanceiraForm()
    return render(request, "financeiro/previsao_form.html", {"form": form})


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def sincronizar_compras(request):
    resultado = sincronizar_todas_integracoes()
    messages.success(
        request,
        f"Financeiro sincronizado: {resultado['compras']} conta(s) de Compras e "
        f"{resultado['grandes_fornecedores']} de Grandes Fornecedores e {resultado.get('recorrentes', 0)} recorrência(s) gerada(s).",
    )
    return redirect("financeiro:previsoes")
