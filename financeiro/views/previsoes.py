from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from financeiro.forms import PrevisaoFinanceiraForm
from financeiro.models import PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.services.previsoes import sincronizar_todas_integracoes


@financeiro_acao_required("VISUALIZAR")
def previsoes_lista(request):
    hoje = timezone.localdate()
    fim_7 = hoje + timedelta(days=7)
    fim_30 = hoje + timedelta(days=30)
    fim_90 = hoje + timedelta(days=90)
    origem = (request.GET.get("origem") or "").strip()
    obra = (request.GET.get("obra") or "").strip()

    contas = TituloPagar.objects.filter(status__in=STATUS_ABERTOS).select_related("obra", "fornecedor", "pedido")
    if origem:
        contas = contas.filter(origem=origem)
    if obra:
        contas = contas.filter(obra_id=obra)

    extras = PrevisaoFinanceira.objects.filter(
        ativa=True,
    ).exclude(origem=PrevisaoFinanceira.Origem.COMPRA).select_related("obra", "fornecedor", "plano_financeiro")
    # Solicitações avulsas são a única previsão fora de Contas a Pagar.
    # Compras, M.O. e GF entram pela própria parcela/Conta a Pagar.
    if origem:
        if origem == TituloPagar.Origem.MANUAL:
            extras = extras.filter(origem__in=[PrevisaoFinanceira.Origem.MANUAL, PrevisaoFinanceira.Origem.RECORRENTE])
        else:
            extras = extras.none()
    if obra:
        extras = extras.filter(obra_id=obra)

    def soma_contas_ate(data):
        return sum((x.saldo_aberto for x in contas.filter(vencimento__range=(hoje, data))), Decimal("0"))

    contas_vencidas = list(contas.filter(vencimento__lt=hoje))
    valor_vencidas = sum((x.saldo_aberto for x in contas_vencidas), Decimal("0"))

    def soma_extras_ate(data):
        return extras.filter(data_prevista__range=(hoje, data)).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

    linhas = []
    for conta in contas.filter(vencimento__isnull=False):
        linhas.append({
            "tipo": "CONTA",
            "data": conta.vencimento,
            "descricao": conta.descricao,
            "origem": conta.get_origem_display(),
            "beneficiario": conta.beneficiario_exibicao,
            "obra": conta.obra,
            "valor": conta.saldo_aberto,
            "status": conta.get_status_display(),
            "situacao_temporal": conta.situacao_temporal,
            "dias_atraso": conta.dias_em_atraso,
            "pk": conta.pk,
        })
    for previsao in extras.filter(data_prevista__isnull=False):
        linhas.append({
            "tipo": "PREVISAO",
            "data": previsao.data_prevista,
            "descricao": previsao.descricao,
            "origem": previsao.get_origem_display(),
            "beneficiario": getattr(previsao.fornecedor, "nome_exibicao", "") if previsao.fornecedor else "—",
            "obra": previsao.obra,
            "valor": previsao.valor_previsto,
            "status": "Solicitação avulsa",
            "situacao_temporal": "PREVISAO",
            "dias_atraso": 0,
            "pk": None,
        })
    linhas.sort(key=lambda item: (item["data"], item["tipo"], item["descricao"]))
    page_obj = Paginator(linhas, 40).get_page(request.GET.get("page"))

    from obras.models import Obra
    return render(request, "financeiro/previsoes.html", {
        "page_obj": page_obj,
        "origem_choices": TituloPagar.Origem.choices[:4],
        "origem": origem,
        "obra": obra,
        "obras": Obra.objects.all().order_by("id"),
        "valor_vencidas": valor_vencidas,
        "qtd_vencidas": len(contas_vencidas),
        "contas_7": soma_contas_ate(fim_7),
        "contas_30": soma_contas_ate(fim_30),
        "contas_90": soma_contas_ate(fim_90),
        "extras_30": soma_extras_ate(fim_30),
        "total_30": soma_contas_ate(fim_30) + soma_extras_ate(fim_30),
        "necessidade_caixa_30": valor_vencidas + soma_contas_ate(fim_30) + soma_extras_ate(fim_30),
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
