from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, resumo_por_obra, serie_desembolsos
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro


@financeiro_acao_required("VISUALIZAR")
def dashboard(request):
    hoje = timezone.localdate()
    em_7 = hoje + timedelta(days=7)
    em_30 = hoje + timedelta(days=30)

    abertos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS).select_related("fornecedor", "obra")
    vencidos = list(abertos.filter(vencimento__lt=hoje))
    proximos_7 = list(abertos.filter(vencimento__range=(hoje, em_7)))
    proximos_30 = list(abertos.filter(vencimento__range=(hoje, em_30)))
    aguardando = list(abertos.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO))

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

    por_origem = []
    for valor, rotulo in TituloPagar.Origem.choices[:4]:
        itens = list(abertos.filter(origem=valor))
        total = sum((x.saldo_aberto for x in itens), Decimal("0"))
        if total:
            por_origem.append({"codigo": valor, "rotulo": rotulo, "total": total, "quantidade": len(itens)})

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
        "valor_vencidos": sum((t.saldo_aberto for t in vencidos), Decimal("0")),
        "qtd_vencidos": len(vencidos),
        "valor_7": sum((t.saldo_aberto for t in proximos_7), Decimal("0")),
        "qtd_7": len(proximos_7),
        "valor_aprovacao": sum((t.saldo_aberto for t in aguardando), Decimal("0")),
        "qtd_aprovacao": len(aguardando),
        "pagos_mes": pagos_mes,
        "previsao_30": sum((t.saldo_aberto for t in proximos_30), Decimal("0")) + previsoes_extras_30,
        "previsoes_extras_30": previsoes_extras_30,
        "pontos_desembolso": pontos,
        "obras_resumo": resumo_por_obra()[:8],
        "por_origem": por_origem,
        "por_classe": por_classe,
        "por_apropriacao": por_apropriacao,
        "por_obra_pago": por_obra_pago,
        "por_fornecedor": por_fornecedor,
        "por_mes": por_mes,
        "proximos_titulos": abertos.filter(vencimento__isnull=False).order_by("vencimento", "id")[:10],
        "pode_lancar": possui_acao_financeiro(request.user, "LANCAR_TITULOS"),
        "pode_administrar": possui_acao_financeiro(request.user, "ADMINISTRAR"),
    })
