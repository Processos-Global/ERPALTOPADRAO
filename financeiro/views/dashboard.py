from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, resumo_por_obra, serie_desembolsos
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro


def _resumo_titulos_abertos(abertos, hoje, em_7, em_30):
    """Resume os títulos uma vez, mantendo o saldo calculado pelo modelo."""
    origens = dict(TituloPagar.Origem.choices[:4])
    por_origem = {codigo: {"codigo": codigo, "rotulo": rotulo, "total": Decimal("0"), "quantidade": 0}
                  for codigo, rotulo in origens.items()}
    resumo = {
        "valor_vencidos": Decimal("0"), "qtd_vencidos": 0,
        "valor_7": Decimal("0"), "qtd_7": 0,
        "valor_aprovacao": Decimal("0"), "qtd_aprovacao": 0,
        "valor_30": Decimal("0"),
    }
    for titulo in abertos.select_related("pagamento").iterator(chunk_size=1000):
        saldo = titulo.saldo_aberto
        vencimento = titulo.vencimento
        if vencimento is not None:
            if vencimento < hoje:
                resumo["valor_vencidos"] += saldo
                resumo["qtd_vencidos"] += 1
            elif vencimento <= em_30:
                resumo["valor_30"] += saldo
                if vencimento <= em_7:
                    resumo["valor_7"] += saldo
                    resumo["qtd_7"] += 1
        if titulo.status == TituloPagar.Status.AGUARDANDO_APROVACAO:
            resumo["valor_aprovacao"] += saldo
            resumo["qtd_aprovacao"] += 1
        if titulo.origem in por_origem:
            linha = por_origem[titulo.origem]
            linha["total"] += saldo
            linha["quantidade"] += 1
    resumo["por_origem"] = [linha for linha in por_origem.values() if linha["total"]]
    return resumo


@financeiro_acao_required("VISUALIZAR")
def dashboard(request):
    hoje = timezone.localdate()
    em_7 = hoje + timedelta(days=7)
    em_30 = hoje + timedelta(days=30)

    abertos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS)
    resumo = _resumo_titulos_abertos(abertos, hoje, em_7, em_30)

    pagos_mes = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__year=hoje.year,
        data_pagamento__month=hoje.month,
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")

    previsoes_extras_30 = PrevisaoFinanceira.objects.filter(
        ativa=True,
        data_prevista__range=(hoje, em_30),
    ).exclude(origem=PrevisaoFinanceira.Origem.COMPRA).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

    desembolsos = serie_desembolsos(inicio=hoje, dias=84)
    pontos = []
    acumulado_semana = Decimal("0")
    for idx, item in enumerate(desembolsos["serie"]):
        acumulado_semana += item["saida"]
        if (idx + 1) % 7 == 0 or idx == len(desembolsos["serie"]) - 1:
            pontos.append({"rotulo": item["data"].strftime("%d/%m"), "saida": float(acumulado_semana)})
            acumulado_semana = Decimal("0")

    pagos_qs = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO).select_related("titulo__plano_financeiro__pai", "titulo__obra", "titulo__fornecedor")
    por_classe = list(
        pagos_qs.exclude(titulo__plano_financeiro__pai__isnull=True)
        .values("titulo__plano_financeiro__pai__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")[:8]
    )
    por_apropriacao = list(
        pagos_qs.exclude(titulo__plano_financeiro__isnull=True)
        .values("titulo__plano_financeiro__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")[:10]
    )
    por_obra_pago = list(
        pagos_qs.exclude(titulo__obra__isnull=True)
        .values("titulo__obra__nome")
        .annotate(total=Sum("valor"))
        .order_by("-total")[:8]
    )
    por_fornecedor = list(
        pagos_qs.exclude(titulo__fornecedor__isnull=True)
        .values("titulo__fornecedor__nome")
        .annotate(total=Sum("valor"))
        .order_by("-total")[:8]
    )
    por_mes = list(
        pagos_qs.values("data_pagamento__year", "data_pagamento__month")
        .annotate(total=Sum("valor"))
        .order_by("-total")[:8]
    )
    nomes_meses = ("", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
    for item in por_mes:
        mes = item.get("data_pagamento__month") or 0
        ano = item.get("data_pagamento__year") or ""
        item["rotulo"] = f"{nomes_meses[mes]}/{ano}" if mes else str(ano)

    return render(request, "financeiro/dashboard.html", {
        "valor_vencidos": resumo["valor_vencidos"],
        "qtd_vencidos": resumo["qtd_vencidos"],
        "valor_7": resumo["valor_7"],
        "qtd_7": resumo["qtd_7"],
        "valor_aprovacao": resumo["valor_aprovacao"],
        "qtd_aprovacao": resumo["qtd_aprovacao"],
        "pagos_mes": pagos_mes,
        "previsao_30": resumo["valor_30"] + previsoes_extras_30,
        "previsoes_extras_30": previsoes_extras_30,
        "pontos_desembolso": pontos,
        "obras_resumo": resumo_por_obra()[:8],
        "por_origem": resumo["por_origem"],
        "por_classe": por_classe,
        "por_apropriacao": por_apropriacao,
        "por_obra_pago": por_obra_pago,
        "por_fornecedor": por_fornecedor,
        "por_mes": por_mes,
        "proximos_titulos": abertos.filter(vencimento__isnull=False).select_related("fornecedor", "obra", "pagamento").order_by("vencimento", "id")[:10],
        "pode_lancar": possui_acao_financeiro(request.user, "LANCAR_TITULOS"),
        "pode_administrar": possui_acao_financeiro(request.user, "ADMINISTRAR"),
    })
