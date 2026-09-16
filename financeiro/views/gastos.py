from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
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

    pagamentos = list(qs[:500])
    total = sum((p.valor for p in pagamentos), Decimal("0"))

    pagos_mes = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__year=hoje.year,
        data_pagamento__month=hoje.month,
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    pagos_ano = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__year=hoje.year,
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_compras = sum((p.valor for p in pagamentos if p.titulo.origem == p.titulo.Origem.COMPRA), Decimal("0"))
    total_mao_obra = sum((p.valor for p in pagamentos if p.titulo.origem == p.titulo.Origem.MAO_OBRA), Decimal("0"))
    total_gf = sum((p.valor for p in pagamentos if p.titulo.origem == p.titulo.Origem.GRANDE_FORNECEDOR), Decimal("0"))
    beneficiario_totais = defaultdict(lambda: Decimal("0"))
    obra_totais = defaultdict(lambda: Decimal("0"))
    categoria_totais = defaultdict(lambda: Decimal("0"))

    for pagamento in pagamentos:
        titulo = pagamento.titulo
        beneficiario_totais[titulo.beneficiario_exibicao] += pagamento.valor
        obra_totais[str(titulo.obra) if titulo.obra else "Sem obra"] += pagamento.valor
        categoria_totais[titulo.plano_financeiro.caminho if titulo.plano_financeiro else "Não classificado"] += pagamento.valor

    return render(request, "financeiro/gastos.html", {
        "pagamentos": pagamentos[:100],
        "total": total,
        "pagos_mes": pagos_mes,
        "pagos_ano": pagos_ano,
        "total_compras": total_compras,
        "total_mao_obra": total_mao_obra,
        "total_gf": total_gf,
        "por_fornecedor": sorted(beneficiario_totais.items(), key=lambda x: x[1], reverse=True)[:15],
        "por_obra": sorted(obra_totais.items(), key=lambda x: x[1], reverse=True)[:15],
        "por_categoria": sorted(categoria_totais.items(), key=lambda x: x[1], reverse=True)[:15],
        "obras": Obra.objects.all().order_by("id"),
        "inicio": inicio,
        "fim": fim,
        "obra_id": str(obra_id),
    })
