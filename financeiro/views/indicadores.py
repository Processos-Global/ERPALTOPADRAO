from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from cadastros.models import Fornecedor
from financeiro.models import Pagamento, PlanoFinanceiro, PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, resumo_por_obra, serie_desembolsos
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


def _max_total(lista, chave="total"):
    valores = [item.get(chave) or Decimal("0") for item in lista]
    maior = max(valores, default=Decimal("0"))
    return maior or Decimal("1")


@financeiro_acao_required("VISUALIZAR")
def indicadores(request):
    hoje = timezone.localdate()
    em_30 = hoje + timedelta(days=30)

    inicio = parse_date((request.GET.get("inicio") or "").strip()) or date(hoje.year, 1, 1)
    fim = parse_date((request.GET.get("fim") or "").strip()) or hoje
    obra = (request.GET.get("obra") or "").strip()
    classe = (request.GET.get("classe") or "").strip()
    apropriacao = (request.GET.get("apropriacao") or "").strip()
    fornecedor = (request.GET.get("fornecedor") or "").strip()

    pagos = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        data_pagamento__range=(inicio, fim),
    ).select_related(
        "titulo__obra", "titulo__fornecedor", "titulo__plano_financeiro", "titulo__plano_financeiro__pai"
    )
    titulos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS).select_related(
        "obra", "fornecedor", "plano_financeiro", "plano_financeiro__pai"
    )

    def aplicar_filtros(qs, prefixo=""):
        if obra:
            qs = qs.filter(**{f"{prefixo}obra_id": obra})
        if fornecedor:
            qs = qs.filter(**{f"{prefixo}fornecedor_id": fornecedor})
        if apropriacao:
            qs = qs.filter(**{f"{prefixo}plano_financeiro_id": apropriacao})
        elif classe:
            qs = qs.filter(**{f"{prefixo}plano_financeiro__pai_id": classe})
        return qs

    pagos = aplicar_filtros(pagos, "titulo__")
    titulos = aplicar_filtros(titulos)

    total_pago = pagos.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    quantidade_pagamentos = pagos.aggregate(total=Count("id"))["total"] or 0
    total_aberto = sum((titulo.saldo_aberto for titulo in titulos), Decimal("0"))
    media_pagamento = (total_pago / quantidade_pagamentos) if quantidade_pagamentos else Decimal("0")

    por_classe = list(
        pagos.exclude(titulo__plano_financeiro__pai__isnull=True)
        .values("titulo__plano_financeiro__pai__codigo", "titulo__plano_financeiro__pai__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    por_apropriacao = list(
        pagos.exclude(titulo__plano_financeiro__isnull=True)
        .values("titulo__plano_financeiro__codigo", "titulo__plano_financeiro__nome", "titulo__plano_financeiro__pai__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    por_obra = list(
        pagos.exclude(titulo__obra__isnull=True)
        .values("titulo__obra__id", "titulo__obra__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    por_fornecedor = list(
        pagos.exclude(titulo__fornecedor__isnull=True)
        .values("titulo__fornecedor__id", "titulo__fornecedor__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")
    )
    por_mes = list(
        pagos.annotate(mes=TruncMonth("data_pagamento"))
        .values("mes")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("mes")
    )

    previsoes_extras_30 = PrevisaoFinanceira.objects.filter(
        ativa=True,
        data_prevista__range=(hoje, em_30),
    ).exclude(origem=PrevisaoFinanceira.Origem.COMPRA).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

    previsao_30 = sum(
        (titulo.saldo_aberto for titulo in titulos.filter(vencimento__isnull=False, vencimento__range=(hoje, em_30))),
        Decimal("0"),
    ) + previsoes_extras_30

    por_origem = []
    for valor, rotulo in TituloPagar.Origem.choices[:4]:
        itens = list(titulos.filter(origem=valor))
        total = sum((x.saldo_aberto for x in itens), Decimal("0"))
        if total:
            por_origem.append({
                "codigo": valor,
                "rotulo": rotulo,
                "total": total,
                "quantidade": len(itens),
            })

    desembolsos = serie_desembolsos(inicio=hoje, dias=84)
    pontos_desembolso = []
    acumulado_semana = Decimal("0")
    for idx, item in enumerate(desembolsos["serie"]):
        acumulado_semana += item["saida"]
        if (idx + 1) % 7 == 0 or idx == len(desembolsos["serie"]) - 1:
            pontos_desembolso.append({
                "rotulo": item["data"].strftime("%d/%m"),
                "saida": float(acumulado_semana),
            })
            acumulado_semana = Decimal("0")

    return render(request, "financeiro/indicadores.html", {
        "inicio": inicio,
        "fim": fim,
        "filtros": {"obra": obra, "classe": classe, "apropriacao": apropriacao, "fornecedor": fornecedor},
        "obras": Obra.objects.all().order_by("id"),
        "fornecedores": Fornecedor.objects.filter(ativo=True).order_by("nome"),
        "classes_financeiras": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=True).order_by("codigo", "nome"),
        "apropriacoes": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=False).select_related("pai").order_by("pai__codigo", "codigo", "nome"),
        "total_pago": total_pago,
        "quantidade_pagamentos": quantidade_pagamentos,
        "total_aberto": total_aberto,
        "media_pagamento": media_pagamento,
        "previsao_30": previsao_30,
        "previsoes_extras_30": previsoes_extras_30,
        "por_classe": por_classe,
        "por_apropriacao": por_apropriacao,
        "por_obra": por_obra,
        "por_fornecedor": por_fornecedor,
        "por_mes": por_mes,
        "por_origem": por_origem,
        "obras_resumo": resumo_por_obra()[:8],
        "pontos_desembolso": pontos_desembolso,
        "max_por_mes": _max_total(por_mes),
        "max_por_classe": _max_total(por_classe),
        "max_por_obra": _max_total(por_obra),
        "max_por_fornecedor": _max_total(por_fornecedor),
        "max_por_origem": _max_total(por_origem),
        "max_pontos_desembolso": _max_total(pontos_desembolso, "saida"),
    })
