from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar


STATUS_ABERTOS = {
    TituloPagar.Status.DOCUMENTO_RECEBIDO,
    TituloPagar.Status.EM_CONFERENCIA,
    TituloPagar.Status.AGUARDANDO_APROVACAO,
    TituloPagar.Status.APROVADO,
    TituloPagar.Status.BLOQUEADO,
}


def serie_desembolsos(*, inicio=None, dias=90, obra_id=None):
    """Retorna somente saídas previstas; não calcula ou estima saldo bancário."""
    inicio = inicio or timezone.localdate()
    fim = inicio + timedelta(days=dias)
    eventos = defaultdict(lambda: {"contas": Decimal("0"), "previsoes": Decimal("0")})

    titulos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS, vencimento__range=(inicio, fim))
    if obra_id:
        titulos = titulos.filter(obra_id=obra_id)
    for titulo in titulos:
        eventos[titulo.vencimento]["contas"] += titulo.saldo_aberto

    previsoes = PrevisaoFinanceira.objects.filter(
        ativa=True,
        data_prevista__range=(inicio, fim),
        titulos_gerados__isnull=True,
    )
    if obra_id:
        previsoes = previsoes.filter(obra_id=obra_id)
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


def resumo_por_obra():
    from obras.models import Obra

    linhas = []
    for obra in Obra.objects.all().order_by("id"):
        pago = Pagamento.objects.filter(
            titulo__obra=obra,
            status=Pagamento.Status.EFETIVADO,
        ).aggregate(total=Sum("valor"))["total"] or Decimal("0")

        aberto = Decimal("0")
        for titulo in TituloPagar.objects.filter(obra=obra, status__in=STATUS_ABERTOS):
            aberto += titulo.saldo_aberto

        previsto = PrevisaoFinanceira.objects.filter(
            obra=obra,
            ativa=True,
            titulos_gerados__isnull=True,
        ).aggregate(total=Sum("valor_previsto"))["total"] or Decimal("0")

        if pago or aberto or previsto:
            linhas.append({
                "obra": obra,
                "pago": pago,
                "aberto": aberto,
                "previsto": previsto,
                "total": pago + aberto + previsto,
            })
    return linhas
