from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from compras.models import PedidoCompra
from financeiro.forms import PrevisaoFinanceiraForm
from financeiro.models import PrevisaoFinanceira, TituloPagar
from financeiro.services.permissoes import financeiro_acao_required
from financeiro.services.previsoes import gerar_previsoes_recorrentes, sincronizar_previsoes_pedido


@financeiro_acao_required("VISUALIZAR")
def previsoes_lista(request):
    hoje = timezone.localdate()
    fim_7 = hoje + timedelta(days=7)
    fim_30 = hoje + timedelta(days=30)
    fim_90 = hoje + timedelta(days=90)

    previsoes = PrevisaoFinanceira.objects.filter(
        ativa=True,
        titulos_gerados__isnull=True,
    ).select_related("obra", "fornecedor", "pedido", "plano_financeiro")

    origem = request.GET.get("origem") or ""
    obra = request.GET.get("obra") or ""
    if origem:
        previsoes = previsoes.filter(origem=origem)
    if obra:
        previsoes = previsoes.filter(obra_id=obra)

    contas_abertas = TituloPagar.objects.exclude(
        status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO, TituloPagar.Status.REJEITADO]
    )

    def total_previsoes_ate(data):
        return previsoes.filter(data_prevista__range=(hoje, data)).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

    total_contas_30 = sum(
        (titulo.saldo_aberto for titulo in contas_abertas.filter(vencimento__range=(hoje, fim_30))),
        Decimal("0"),
    )

    page_obj = Paginator(previsoes.order_by("data_prevista", "id"), 30).get_page(request.GET.get("page"))

    from obras.models import Obra
    return render(request, "financeiro/previsoes.html", {
        "page_obj": page_obj,
        "origem_choices": PrevisaoFinanceira.Origem.choices,
        "origem": origem,
        "obra": obra,
        "obras": Obra.objects.all().order_by("id"),
        "total_7": total_previsoes_ate(fim_7),
        "total_30": total_previsoes_ate(fim_30),
        "total_90": total_previsoes_ate(fim_90),
        "contas_30": total_contas_30,
        "total_desembolso_30": total_previsoes_ate(fim_30) + total_contas_30,
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
            messages.success(request, "Previsão de gasto criada com sucesso.")
            return redirect("financeiro:previsoes")
    else:
        form = PrevisaoFinanceiraForm()
    return render(request, "financeiro/previsao_form.html", {"form": form})


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def sincronizar_compras(request):
    total = 0
    for pedido in PedidoCompra.objects.exclude(status=PedidoCompra.Status.CANCELADO).prefetch_related("parcelas_previstas"):
        total += sincronizar_previsoes_pedido(pedido).count()
    hoje = timezone.localdate()
    recorrentes = gerar_previsoes_recorrentes(hoje, hoje + timedelta(days=180), request.user)
    messages.success(request, f"Previsões atualizadas: {total} de compras e {recorrentes} recorrentes novas.")
    return redirect("financeiro:previsoes")
