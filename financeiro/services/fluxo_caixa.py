from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar


STATUS_ABERTOS = {
    TituloPagar.Status.PREVISTA,
    TituloPagar.Status.AGUARDANDO_APROVACAO,
    TituloPagar.Status.APROVADO,
}


def serie_desembolsos(*, inicio=None, dias=90, obra_id=None, obra_ids=None,
                     classe=None, apropriacao=None, fornecedor=None):
    """Saídas futuras conhecidas + previsões ainda não formalizadas."""
    inicio = inicio or timezone.localdate()
    fim = inicio + timedelta(days=dias)
    eventos = defaultdict(lambda: {"contas": Decimal("0"), "previsoes": Decimal("0")})

    # saldo_aberto acessa a relação OneToOne pagamento. Sem select_related,
    # cada título poderia gerar uma consulta adicional ao banco.
    titulos = TituloPagar.objects.filter(
        status__in=STATUS_ABERTOS,
        vencimento__range=(inicio, fim),
    ).select_related("pagamento")
    from financeiro.services.indicadores_gerenciais import _filtros

    obras_filtro = list(obra_ids or [])
    if obra_id and obra_id not in obras_filtro:
        obras_filtro.append(obra_id)
    titulos = _filtros(titulos, obra_ids=obras_filtro, classe=classe,
                       apropriacao=apropriacao, fornecedor=fornecedor)
    for titulo in titulos:
        eventos[titulo.vencimento]["contas"] += titulo.saldo_aberto

    previsoes = PrevisaoFinanceira.objects.filter(
        ativa=True,
        data_prevista__range=(inicio, fim),
    ).exclude(origem=PrevisaoFinanceira.Origem.COMPRA)
    previsoes = _filtros(previsoes, obra_ids=obras_filtro, classe=classe,
                         apropriacao=apropriacao, fornecedor=fornecedor)
    for previsao in previsoes:
        eventos[previsao.data_prevista]["previsoes"] += previsao.valor_previsto

    serie = []
    cursor = inicio
    total = Decimal("0")
    while cursor <= fim:
        contas = eventos[cursor]["contas"]
        previsto = eventos[cursor]["previsoes"]
        saida = contas + previsto
        total += saida
        serie.append({
            "data": cursor,
            "contas": contas,
            "previsoes": previsto,
            "saida": saida,
            "acumulado": total,
        })
        cursor += timedelta(days=1)
    return {"serie": serie, "total": total}


def resumo_por_obra(*, inicio=None, fim=None):
    """Resumo financeiro por obra sem consultas dentro do loop de obras."""
    from obras.models import Obra

    obras = list(Obra.objects.all().order_by("id"))

    pagamentos = Pagamento.objects.filter(
        status=Pagamento.Status.EFETIVADO,
        titulo__obra_id__isnull=False,
    )
    if inicio:
        pagamentos = pagamentos.filter(data_pagamento__gte=inicio)
    if fim:
        pagamentos = pagamentos.filter(data_pagamento__lte=fim)
    pagos_por_obra = {
        item["titulo__obra_id"]: item["total"] or Decimal("0")
        for item in (
            pagamentos
            .values("titulo__obra_id")
            .annotate(total=Sum("valor"))
        )
    }

    abertos_por_obra = defaultdict(lambda: Decimal("0"))
    titulos_abertos = (
        TituloPagar.objects.filter(
            status__in=STATUS_ABERTOS,
            obra_id__isnull=False,
        )
        .select_related("pagamento")
    )
    if inicio:
        titulos_abertos = titulos_abertos.filter(vencimento__gte=inicio)
    if fim:
        titulos_abertos = titulos_abertos.filter(vencimento__lte=fim)
    for titulo in titulos_abertos:
        abertos_por_obra[titulo.obra_id] += titulo.saldo_aberto

    previsoes = PrevisaoFinanceira.objects.filter(ativa=True, obra_id__isnull=False).exclude(
        origem=PrevisaoFinanceira.Origem.COMPRA
    )
    if inicio:
        previsoes = previsoes.filter(data_prevista__gte=inicio)
    if fim:
        previsoes = previsoes.filter(data_prevista__lte=fim)
    previstos_por_obra = {
        item["obra_id"]: item["total"] or Decimal("0")
        for item in (
            previsoes
            .values("obra_id")
            .annotate(total=Sum("valor_previsto"))
        )
    }

    linhas = []
    for obra in obras:
        pago = pagos_por_obra.get(obra.pk, Decimal("0"))
        aberto = abertos_por_obra.get(obra.pk, Decimal("0"))
        previsto_extra = previstos_por_obra.get(obra.pk, Decimal("0"))
        if pago or aberto or previsto_extra:
            linhas.append({
                "obra": obra,
                "pago": pago,
                "aberto": aberto,
                "previsto": previsto_extra,
                "total": pago + aberto + previsto_extra,
            })
    return linhas
