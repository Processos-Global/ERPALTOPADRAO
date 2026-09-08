from collections import defaultdict
from decimal import Decimal

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
    ).select_related(
        "titulo", "titulo__fornecedor", "titulo__obra", "titulo__plano_financeiro"
    ).order_by("-data_pagamento", "-id")

    if obra_id:
        qs = qs.filter(titulo__obra_id=obra_id)

    pagamentos = list(qs[:500])
    total = sum((p.valor for p in pagamentos), Decimal("0"))
    fornecedor_totais = defaultdict(lambda: Decimal("0"))
    obra_totais = defaultdict(lambda: Decimal("0"))
    categoria_totais = defaultdict(lambda: Decimal("0"))

    for pagamento in pagamentos:
        titulo = pagamento.titulo
        fornecedor_totais[
            titulo.fornecedor.nome_exibicao if titulo.fornecedor else "Sem fornecedor"
        ] += pagamento.valor
        obra_totais[str(titulo.obra) if titulo.obra else "Sem obra"] += pagamento.valor
        categoria_totais[
            titulo.plano_financeiro.caminho if titulo.plano_financeiro else "Não classificado"
        ] += pagamento.valor

    por_fornecedor = sorted(fornecedor_totais.items(), key=lambda x: x[1], reverse=True)[:15]
    por_obra = sorted(obra_totais.items(), key=lambda x: x[1], reverse=True)[:15]
    por_categoria = sorted(categoria_totais.items(), key=lambda x: x[1], reverse=True)[:15]

    return render(request, "financeiro/gastos.html", {
        "pagamentos": pagamentos[:100],
        "total": total,
        "por_fornecedor": por_fornecedor,
        "por_obra": por_obra,
        "por_categoria": por_categoria,
        "obras": Obra.objects.all().order_by("id"),
        "inicio": inicio,
        "fim": fim,
        "obra_id": str(obra_id),
    })
