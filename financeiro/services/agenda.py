"""Consultas e indicadores da agenda de pagamentos.

Datas dos títulos são de vencimento; pagamentos usam data_pagamento.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils.dateparse import parse_date

from financeiro.models import Pagamento, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS


PERIODOS = (
    ("todos", "Todos os vencimentos"), ("vencidas", "Vencidas"),
    ("hoje", "Hoje"), ("amanha", "Amanhã"),
    ("7", "Próximos 7 dias"), ("30", "Próximos 30 dias"),
    ("data", "Data específica"), ("intervalo", "Intervalo de datas"),
    ("mes", "Mês e ano"),
)


def _inteiro_positivo(valor):
    return int(valor) if str(valor).isdigit() and int(valor) > 0 else None


def _data(valor):
    try:
        return parse_date(valor or "")
    except ValueError:
        return None


def periodo_vencimento(parametros, hoje):
    codigo = parametros.get("periodo") or "todos"
    if codigo == "vencidas":
        return codigo, None, hoje - timedelta(days=1)
    if codigo == "hoje":
        return codigo, hoje, hoje
    if codigo == "amanha":
        amanha = hoje + timedelta(days=1)
        return codigo, amanha, amanha
    if codigo in {"7", "30"}:
        return codigo, hoje, hoje + timedelta(days=int(codigo))
    if codigo == "data":
        data = _data(parametros.get("data"))
        return codigo, data, data
    if codigo == "intervalo":
        return codigo, _data(parametros.get("inicio")), _data(parametros.get("fim"))
    if codigo == "mes":
        ano = _inteiro_positivo(parametros.get("ano"))
        mes = _inteiro_positivo(parametros.get("mes"))
        if ano and 1 <= ano <= 9998 and mes and 1 <= mes <= 12:
            inicio = date(ano, mes, 1)
            fim = date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)
            return codigo, inicio, fim
        return codigo, None, None
    return "todos", None, None


def filtrar_titulos_base(parametros):
    qs = TituloPagar.objects.all()
    for parametro, campo in (("obra", "obra_id"), ("fornecedor", "fornecedor_id"),
                             ("apropriacao", "plano_financeiro_id")):
        identificador = _inteiro_positivo(parametros.get(parametro))
        if identificador:
            qs = qs.filter(**{campo: identificador})
    status = parametros.get("status") or ""
    if status in TituloPagar.Status.values:
        qs = qs.filter(status=status)
    return qs


def filtrar_por_vencimento(qs, inicio, fim):
    if inicio and fim and inicio > fim:
        return qs.none()
    if inicio:
        qs = qs.filter(vencimento__gte=inicio)
    if fim:
        qs = qs.filter(vencimento__lte=fim)
    return qs


def indicadores_agenda(base, titulos_periodo, hoje, inicio, fim):
    """Cada título contribui uma vez por indicador, pelo saldo do modelo."""
    totais = {chave: Decimal("0") for chave in (
        "vencido", "hoje", "aprovado_hoje", "sete_dias", "em_aberto"
    )}
    for titulo in titulos_periodo.select_related("pagamento").iterator(chunk_size=1000):
        if titulo.status not in STATUS_ABERTOS:
            continue
        saldo = titulo.saldo_aberto
        vencimento = titulo.vencimento
        if vencimento is None:
            continue
        totais["em_aberto"] += saldo
        if vencimento < hoje:
            totais["vencido"] += saldo
        if vencimento == hoje:
            totais["hoje"] += saldo
            if titulo.status == TituloPagar.Status.APROVADO:
                totais["aprovado_hoje"] += saldo
        if hoje <= vencimento <= hoje + timedelta(days=7):
            totais["sete_dias"] += saldo

    pagamentos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, titulo__in=base)
    if inicio:
        pagamentos = pagamentos.filter(data_pagamento__gte=inicio)
    if fim:
        pagamentos = pagamentos.filter(data_pagamento__lte=fim)
    totais["pago"] = pagamentos.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    return totais
