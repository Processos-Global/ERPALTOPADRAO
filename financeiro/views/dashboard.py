from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import resumo_por_obra, serie_desembolsos
from financeiro.services.permissoes import financeiro_acao_required


@financeiro_acao_required("VISUALIZAR")
def dashboard(request):
    hoje = timezone.localdate()
    em_7 = hoje + timedelta(days=7)
    em_30 = hoje + timedelta(days=30)

    abertos = TituloPagar.objects.exclude(
        status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO, TituloPagar.Status.REJEITADO]
    ).select_related("fornecedor", "obra")

    vencidos = [t for t in abertos.filter(vencimento__lt=hoje) if t.saldo_aberto > 0]
    proximos_7 = [t for t in abertos.filter(vencimento__range=(hoje, em_7)) if t.saldo_aberto > 0]
    proximos_30 = [t for t in abertos.filter(vencimento__range=(hoje, em_30)) if t.saldo_aberto > 0]
    aguardando = list(abertos.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO))

    pagos_mes = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__year=hoje.year,
        data_pagamento__month=hoje.month,
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")

    previstos_30 = PrevisaoFinanceira.objects.filter(
        ativa=True,
        data_prevista__range=(hoje, em_30),
        titulos_gerados__isnull=True,
    ).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

    desembolsos = serie_desembolsos(inicio=hoje, dias=84)
    pontos = []
    acumulado_semana = Decimal("0")
    for idx, item in enumerate(desembolsos["serie"]):
        acumulado_semana += item["saida"]
        if (idx + 1) % 7 == 0 or idx == len(desembolsos["serie"]) - 1:
            pontos.append({
                "rotulo": item["data"].strftime("%d/%m"),
                "saida": float(acumulado_semana),
            })
            acumulado_semana = Decimal("0")

    return render(request, "financeiro/dashboard.html", {
        "valor_vencidos": sum((t.saldo_aberto for t in vencidos), Decimal("0")),
        "qtd_vencidos": len(vencidos),
        "valor_7": sum((t.saldo_aberto for t in proximos_7), Decimal("0")),
        "valor_30": sum((t.saldo_aberto for t in proximos_30), Decimal("0")),
        "valor_aprovacao": sum((t.saldo_aberto for t in aguardando), Decimal("0")),
        "qtd_aprovacao": len(aguardando),
        "pagos_mes": pagos_mes,
        "previstos_30": previstos_30,
        "desembolso_30": sum((t.saldo_aberto for t in proximos_30), Decimal("0")) + previstos_30,
        "pontos_desembolso": pontos,
        "obras_resumo": resumo_por_obra()[:8],
        "proximos_titulos": abertos.filter(vencimento__isnull=False).order_by("vencimento", "id")[:8],
    })
