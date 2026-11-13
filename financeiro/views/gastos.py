from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from financeiro.models import Pagamento
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def gastos(request):
    hoje = timezone.localdate()
    inicio = request.GET.get("inicio") or hoje.replace(day=1).isoformat()
    fim = request.GET.get("fim") or hoje.isoformat()
    obra_id = request.GET.get("obra") or ""

    qs = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__range=(inicio, fim),
    ).select_related("titulo", "titulo__fornecedor", "titulo__obra", "titulo__plano_financeiro").order_by("-data_pagamento", "-id")
    if obra_id:
        qs = qs.filter(titulo__obra_id=obra_id)

    total = qs.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_compras = qs.filter(titulo__origem="COMPRA").aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_mao_obra = qs.filter(titulo__origem="MAO_OBRA").aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_gf = qs.filter(titulo__origem="GRANDE_FORNECEDOR").aggregate(total=Sum("valor"))["total"] or Decimal("0")

    pagos_mes = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, data_pagamento__year=hoje.year, data_pagamento__month=hoje.month).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    pagos_ano = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, data_pagamento__year=hoje.year).aggregate(total=Sum("valor"))["total"] or Decimal("0")

    por_fornecedor = list(qs.values("titulo__beneficiario_nome").annotate(total=Sum("valor")).order_by("-total")[:15])
    por_obra = list(qs.values("titulo__obra__nome").annotate(total=Sum("valor")).order_by("-total")[:15])
    por_categoria = list(qs.values("titulo__plano_financeiro__nome").annotate(total=Sum("valor")).order_by("-total")[:15])

    fluxo_mensal = list(qs.annotate(mes=TruncMonth("data_pagamento")).values("mes").annotate(total=Sum("valor")).order_by("mes"))
    pagamentos = list(qs[:100])
    return render(request, "financeiro/gastos.html", {
        "pagamentos": pagamentos, "total": total, "pagos_mes": pagos_mes, "pagos_ano": pagos_ano,
        "total_compras": total_compras, "total_mao_obra": total_mao_obra, "total_gf": total_gf,
        "por_fornecedor": [(x["titulo__beneficiario_nome"] or "Não definido", x["total"]) for x in por_fornecedor],
        "por_obra": [(x["titulo__obra__nome"] or "Sem obra", x["total"]) for x in por_obra],
        "por_categoria": [(x["titulo__plano_financeiro__nome"] or "Não classificado", x["total"]) for x in por_categoria],
        "fluxo_mensal": fluxo_mensal,
        "obras": Obra.objects.all().order_by("id"), "inicio": inicio, "fim": fim, "obra_id": str(obra_id),
    })

