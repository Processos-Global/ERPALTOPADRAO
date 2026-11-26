"""Consultas e indicadores da agenda de pagamentos.

Datas dos títulos são de vencimento; pagamentos usam data_pagamento.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Case, DecimalField, Exists, F, OuterRef, Q, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.utils.dateparse import parse_date

from financeiro.models import AprovacaoTituloFinanceiro, Pagamento, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS


PERIODOS = (
    ("todos", "Todos os vencimentos"), ("vencidas", "Vencidas"),
    ("hoje", "Hoje"), ("amanha", "Amanhã"),
    ("7", "Próximos 7 dias"), ("30", "Próximos 30 dias"),
    ("data", "Data específica"), ("intervalo", "Intervalo de datas"),
    ("este_mes", "Este mês"), ("mes", "Mês específico"),
)

MOEDA = DecimalField(max_digits=18, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MOEDA)


def _inteiro_positivo(valor):
    texto = str(valor or "").strip().lstrip("0")
    if not texto.isascii() or not texto.isdecimal() or len(texto) > 19:
        return None
    numero = int(texto)
    return numero if numero <= 2**63 - 1 else None


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
    if codigo in {"mes", "este_mes"}:
        ano, mes = hoje.year, hoje.month
        if codigo == "mes":
            mes_campo = parametros.get("mes") or ""
            if "-" in mes_campo:
                ano_txt, mes_txt = mes_campo.split("-", 1)
            else:
                ano_txt, mes_txt = parametros.get("ano"), mes_campo
            ano, mes = _inteiro_positivo(ano_txt), _inteiro_positivo(mes_txt)
        if ano and 1 <= ano <= 9998 and mes and 1 <= mes <= 12:
            inicio = date(ano, mes, 1)
            fim = date(ano + (mes == 12), (mes % 12) + 1, 1) - timedelta(days=1)
            return codigo, inicio, fim
        return codigo, None, None
    if codigo == "90":
        return codigo, hoje, hoje + timedelta(days=90)
    return "todos", None, None


def filtrar_titulos_base(parametros):
    from financeiro.services.indicadores_gerenciais import _filtros

    qs = TituloPagar.objects.all()
    for parametro, campo in (("obra", "obra_id"), ("fornecedor", "fornecedor_id"),
                             ("apropriacao", "plano_financeiro_id"),
                             ("solicitacao", "solicitacao_avulsa_id")):
        identificador = _inteiro_positivo(parametros.get(parametro))
        if identificador:
            qs = qs.filter(**{campo: identificador})
    if classe := _inteiro_positivo(parametros.get("classe")):
        qs = _filtros(qs, classe=classe)
    for campo, choices in (("status", TituloPagar.Status), ("origem", TituloPagar.Origem), ("conferencia", TituloPagar.Conferencia)):
        valor = parametros.get(campo)
        if valor in choices.values:
            qs = qs.filter(**{campo: valor})
    busca = (parametros.get("q") or "").strip()[:150]
    if busca:
        qs = qs.filter(
            Q(numero__icontains=busca) | Q(documento_numero__icontains=busca) | Q(descricao__icontains=busca)
            | Q(beneficiario_nome__icontains=busca) | Q(fornecedor__nome__icontains=busca)
            | Q(fornecedor__nome_fantasia__icontains=busca) | Q(pedido__numero__icontains=busca)
            | Q(origem_detalhe__icontains=busca)
        )
    if parametros.get("excluir_cancelados") == "1":
        qs = qs.exclude(status=TituloPagar.Status.CANCELADO)
    return qs


def saldo_titulo_sql():
    pago = Case(
        When(pagamento__status=Pagamento.Status.EFETIVADO, then=F("pagamento__valor")),
        default=ZERO, output_field=MOEDA,
    )
    liquido = F("valor_original") + F("juros") + F("multa") + F("outros_acrescimos") - F("desconto")
    return Greatest(liquido - pago, ZERO, output_field=MOEDA)


def titulos_disponiveis_pagamento(qs):
    aprovacao_vigente = AprovacaoTituloFinanceiro.objects.filter(
        titulo_id=OuterRef("pk"), ciclo=OuterRef("ciclo_aprovacao"),
        decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,
    )
    return qs.filter(
        Q(ciclo_aprovacao=0) | Exists(aprovacao_vigente), status=TituloPagar.Status.APROVADO,
    ).exclude(
        pagamento__status=Pagamento.Status.EFETIVADO,
    ).alias(saldo_disponivel=saldo_titulo_sql()).filter(saldo_disponivel__gt=0)


def recorte_contas_a_pagar(parametros, hoje):
    filtros = parametros.copy()
    atalho = filtros.get("atalho")
    if atalho == "aprovacao":
        filtros["status"] = TituloPagar.Status.AGUARDANDO_APROVACAO
    elif atalho in {"vencidos", "7", "30", "90"}:
        filtros["periodo"] = "vencidas" if atalho == "vencidos" else atalho
        filtros["abertas"] = "1"
    base = filtrar_titulos_base(filtros)
    if filtros.get("abertas") == "1" or atalho == "sem_data":
        base = base.filter(status__in=STATUS_ABERTOS)
    if atalho == "sem_data":
        base = base.filter(vencimento__isnull=True)
    periodo, inicio, fim = periodo_vencimento(filtros, hoje)
    invalido = periodo in {"data", "intervalo", "mes"} and (not inicio or not fim or inicio > fim)
    qs = base.none() if invalido else filtrar_por_vencimento(base, inicio, fim)
    return base, qs, periodo, inicio, fim, invalido, filtros


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
    saldo = saldo_titulo_sql()
    totais = titulos_periodo.filter(status__in=STATUS_ABERTOS).aggregate(
        vencido=Sum(saldo, filter=Q(vencimento__lt=hoje)),
        hoje=Sum(saldo, filter=Q(vencimento=hoje)),
        aprovado_hoje=Sum(saldo, filter=Q(vencimento=hoje, status=TituloPagar.Status.APROVADO)),
        sete_dias=Sum(saldo, filter=Q(vencimento__range=(hoje, hoje + timedelta(days=7)))),
        em_aberto=Sum(saldo, filter=Q(vencimento__isnull=False)),
    )

    pagamentos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, titulo__in=base)
    if inicio:
        pagamentos = pagamentos.filter(data_pagamento__gte=inicio)
    if fim:
        pagamentos = pagamentos.filter(data_pagamento__lte=fim)
    totais["pago"] = pagamentos.aggregate(total=Sum("valor"))["total"]
    return {campo: (valor or Decimal("0")).quantize(Decimal("0.01")) for campo, valor in totais.items()}
