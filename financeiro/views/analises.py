from decimal import Decimal
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone
from financeiro.models import Pagamento, TituloPagar
from financeiro.services.permissoes import financeiro_acao_required
from financeiro.services.fluxo_caixa import STATUS_ABERTOS
from obras.models import Obra

@financeiro_acao_required("VISUALIZAR")
def analises(request):
    hoje = timezone.localdate()
    obra_id = request.GET.get("obra") or ""
    pagos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO).select_related("titulo")
    abertos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS, vencimento__isnull=False)
    if obra_id:
        pagos = pagos.filter(titulo__obra_id=obra_id)
        abertos = abertos.filter(obra_id=obra_id)

    realizado_mes = list(pagos.annotate(mes=TruncMonth("data_pagamento")).values("mes").annotate(total=Sum("valor")).order_by("mes"))
    previsto_mes = list(abertos.annotate(mes=TruncMonth("vencimento")).values("mes").annotate(total=Sum("valor_original")).order_by("mes"))
    por_obra = list(pagos.values("titulo__obra__nome").annotate(total=Sum("valor")).order_by("-total")[:12])
    por_apropriacao = list(pagos.values("titulo__plano_financeiro__nome").annotate(total=Sum("valor")).order_by("-total")[:12])
    por_origem = list(pagos.values("titulo__origem").annotate(total=Sum("valor")).order_by("-total"))
    total_realizado = pagos.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_aberto = abertos.aggregate(total=Sum("valor_original"))["total"] or Decimal("0")
    return render(request, "financeiro/analises.html", {
        "realizado_mes": realizado_mes, "previsto_mes": previsto_mes, "por_obra": por_obra,
        "por_apropriacao": por_apropriacao, "por_origem": por_origem, "total_realizado": total_realizado,
        "total_aberto": total_aberto, "obras": Obra.objects.all().order_by("id"), "obra_id": str(obra_id), "hoje": hoje,
    })
