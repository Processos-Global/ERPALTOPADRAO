from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, DateField, Exists, F, OuterRef, Q, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar


STATUS_ABERTOS = {
    TituloPagar.Status.PREVISTA,
    TituloPagar.Status.AGUARDANDO_APROVACAO,
    TituloPagar.Status.CORRECAO_SOLICITADA,
    TituloPagar.Status.APROVADO,
}


def previsoes_independentes():
    """Mantém só previsões ativas cuja obrigação ainda não está em um título."""
    titulos_cobertos = TituloPagar.objects.filter(
        previsao_origem_id=OuterRef("pk"),
        status__in=STATUS_ABERTOS | {TituloPagar.Status.PAGO},
    )
    return PrevisaoFinanceira.objects.filter(ativa=True).exclude(
        origem=PrevisaoFinanceira.Origem.COMPRA,
    ).filter(~Exists(titulos_cobertos))


def titulos_com_data_desembolso(titulos):
    """Uma programação perde efeito quando o título sai do ciclo aprovado."""
    return titulos.annotate(
        data_programada_vigente=Case(
            When(
                ~Q(pagamento__status=Pagamento.Status.EFETIVADO),
                status=TituloPagar.Status.APROVADO,
                programacao_pagamento__ativa=True,
                programacao_pagamento__ciclo_aprovacao=F("ciclo_aprovacao"),
                then=F("programacao_pagamento__data_programada"),
            ),
            output_field=DateField(),
        ),
    ).annotate(data_desembolso=Coalesce("data_programada_vigente", "vencimento"))


def serie_desembolsos(*, inicio=None, dias=90, obra_id=None, obra_ids=None,
                     classe=None, apropriacao=None, fornecedor=None, origem=None):
    """Saídas futuras conhecidas + previsões ainda não formalizadas."""
    inicio = inicio or timezone.localdate()
    fim = inicio + timedelta(days=dias)
    from financeiro.services.agenda import saldo_titulo_sql
    from financeiro.services.compromissos import compromissos_datados
    from financeiro.services.indicadores_gerenciais import _filtros

    titulos = titulos_com_data_desembolso(TituloPagar.objects.filter(status__in=STATUS_ABERTOS))
    titulos = titulos.filter(data_desembolso__range=(inicio, fim))
    previsoes = previsoes_independentes().filter(data_prevista__range=(inicio, fim))
    obras_filtro = list(obra_ids or [])
    if obra_id and obra_id not in obras_filtro:
        obras_filtro.append(obra_id)
    if origem:
        titulos = titulos.filter(origem=origem)
        previsoes = previsoes.filter(origem=origem)
    titulos = _filtros(titulos, obra_ids=obras_filtro, classe=classe,
                       apropriacao=apropriacao, fornecedor=fornecedor)
    previsoes = _filtros(previsoes, obra_ids=obras_filtro, classe=classe,
                         apropriacao=apropriacao, fornecedor=fornecedor)

    valores_contas = dict(titulos.order_by().values_list("data_desembolso").annotate(total=Sum(saldo_titulo_sql())))
    valores_previsoes = dict(previsoes.order_by().values_list("data_prevista").annotate(total=Sum("valor_previsto")))
    valores_compromissos = (
        compromissos_datados(inicio, fim, obra_ids=obras_filtro, classe=classe,
                            apropriacao=apropriacao, fornecedor=fornecedor)
        if not origem or origem == TituloPagar.Origem.COMPRA else {}
    )

    serie = []
    cursor = inicio
    zero = Decimal("0.00")
    total = zero
    while cursor <= fim:
        contas = (valores_contas.get(cursor) or zero).quantize(zero)
        previsto = ((valores_previsoes.get(cursor) or zero) + valores_compromissos.get(cursor, zero)).quantize(zero)
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

    previsoes = previsoes_independentes().filter(obra_id__isnull=False)
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
