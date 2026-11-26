"""Leitura mensal das origens financeiras, com cada camada em sua própria data."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import BooleanField, CharField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf, TruncDate, TruncMonth
from django.utils import timezone

from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, PrevisaoFinanceira, TituloPagar
from financeiro.services.agenda import _inteiro_positivo, periodo_vencimento, saldo_titulo_sql
from financeiro.services.compromissos import compromissos_datados, contratos_assinados_separados, pedidos_comprometidos
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, previsoes_independentes, titulos_com_data_desembolso


CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")
TIPOS_PLANEJAMENTO = {
    "PREVISAO": "Previsto",
    "PEDIDO": "Contratado em pedidos",
    "CONTRATO": "Contratos assinados",
    "LIBERACAO": "Liberado",
    "PAGO": "Pago",
    "SALDO": "Saldo em aberto",
}
ORIGENS_PLANEJAMENTO = dict(TituloPagar.Origem.choices) | dict(PrevisaoFinanceira.Origem.choices)
ORIGENS_PLANEJAMENTO.update({TituloPagar.Origem.MANUAL: "Lançamento manual", TituloPagar.Origem.COMPRA: "Compras"})


def _texto(texto=""):
    return Value(texto, output_field=CharField())


def _meses_de_analise(mes):
    primeiro = max(12, mes.year * 12 + mes.month - 1 - 2)
    ultimo = min(9999 * 12 + 10, mes.year * 12 + mes.month - 1 + 3)
    return [date(indice // 12, indice % 12 + 1, 1) for indice in range(primeiro, ultimo + 1)]


def _fontes(filtros):
    """Constrói um conjunto por fonte, com os mesmos filtros e sem cruzar valores."""
    campos = {campo: filtros[nome] for nome, campo in (
        ("obra", "obra_id"), ("fornecedor", "fornecedor_id"), ("apropriacao", "plano_financeiro_id"),
        ("origem", "origem"),
    ) if filtros[nome]}
    origem = filtros["origem"]
    certeza = filtros["certeza"]
    if origem != PrevisaoFinanceira.Origem.COMPRA:
        previsto = previsoes_independentes().filter(**campos)
        if certeza:
            previsto = previsto.filter(certeza=certeza)
        yield "PREVISAO", previsto.annotate(mov_data=F("data_prevista"), mov_valor=F("valor_previsto")), "", "", F("descricao"), F("origem")

    # O nível de certeza só existe na previsão. Nenhum outro registro recebe um nível implícito.
    if certeza:
        return

    if not origem or origem in TituloPagar.Origem.values:
        titulos = TituloPagar.objects.filter(**campos)
        abertos = titulos_com_data_desembolso(titulos.filter(status__in=STATUS_ABERTOS)).annotate(
            mov_data=F("data_desembolso"), mov_valor=saldo_titulo_sql(),
        ).filter(mov_valor__gt=0)
        yield "SALDO", abertos, "", "", F("descricao"), F("origem")
        pagos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, titulo__in=titulos).annotate(
            mov_data=F("data_pagamento"), mov_valor=F("valor"),
        )
        yield "PAGO", pagos, "titulo__", "", F("titulo__descricao"), F("titulo__origem")

    compra_filtros = {"obra_id": filtros["obra"], "fornecedor_id": filtros["fornecedor"]}
    apropriacao = filtros["apropriacao"]
    if not origem or origem == TituloPagar.Origem.COMPRA:
        pedidos = pedidos_comprometidos(**compra_filtros).annotate(
            mov_data=F("data"), mov_valor=F("valor_vigente"),
        ).filter(mov_valor__gt=0)
        liberacoes = LiberacaoFinanceiraPedido.objects.filter(status=LiberacaoFinanceiraPedido.Status.AUTORIZADA)
        liberacoes = liberacoes.filter(**{f"pedido__{campo}": valor for campo, valor in compra_filtros.items() if valor})
        if apropriacao:
            pedidos = pedidos.filter(processo__apropriacao_id=apropriacao)
            liberacoes = liberacoes.filter(pedido__processo__apropriacao_id=apropriacao)
        yield "PEDIDO", pedidos, "", "processo__apropriacao", F("numero"), _texto(TituloPagar.Origem.COMPRA)
        yield "LIBERACAO", liberacoes.annotate(
            mov_data=TruncDate("autorizado_em"), mov_valor=F("valor"),
        ), "pedido__", "pedido__processo__apropriacao", F("pedido__numero"), _texto(TituloPagar.Origem.COMPRA)

    if not origem or origem == TituloPagar.Origem.CONTRATO:
        contratos = contratos_assinados_separados(**compra_filtros)
        if apropriacao:
            contratos = contratos.filter(processo__apropriacao_id=apropriacao)
        yield "CONTRATO", contratos.annotate(
            mov_data=TruncDate("assinado_em"), mov_valor=F("valor_total"),
        ), "", "processo__apropriacao", F("objeto_contrato"), _texto(TituloPagar.Origem.CONTRATO)


def _projetar(fonte):
    tipo, qs, prefixo, apropriacao, descricao, origem = fonte
    nome_fornecedor = [
        NullIf(F(f"{prefixo}fornecedor__nome_fantasia"), _texto()),
        F(f"{prefixo}fornecedor__nome"),
    ]
    if tipo in {"SALDO", "PAGO"}:
        nome_fornecedor.insert(0, NullIf(F(f"{prefixo}beneficiario_nome"), _texto()))
    if tipo == "CONTRATO":
        nome_fornecedor.insert(0, NullIf(F("contratado_razao_social"), _texto()))
    if not apropriacao:
        apropriacao = f"{prefixo}plano_financeiro"
    return qs.order_by().values("pk").values(
        data=F("mov_data"), tipo=_texto(tipo),
        referencia_id=F("titulo_id" if tipo == "PAGO" else "pk"),
        descricao=descricao, origem=origem,
        beneficiario=Coalesce(*nome_fornecedor, _texto()),
        obra=Coalesce(F(f"{prefixo}obra__nome"), _texto()),
        apropriacao=Coalesce(F(f"{apropriacao}__codigo"), _texto()),
        certeza=F("certeza") if tipo == "PREVISAO" else _texto(),
        previsao_origem=Coalesce(F(f"{prefixo}previsao_origem__descricao"), _texto()) if tipo in {"SALDO", "PAGO"} else _texto(),
        valor=F("mov_valor"),
        programado=Q(data_programada_vigente__isnull=False) if tipo == "SALDO" else Value(False, output_field=BooleanField()),
    )


def _linhas_periodo(fontes, inicio, fim, sem_data):
    linhas = []
    for tipo, qs, *campos in fontes:
        recortado = qs.filter(mov_data__isnull=True) if sem_data else qs.filter(mov_data__range=(inicio, fim))
        linhas.append(_projetar((tipo, recortado, *campos)))
    if not linhas:
        # O filtro de certeza pode descartar a única origem selecionada.
        return _projetar(("PREVISAO", PrevisaoFinanceira.objects.none().annotate(
            mov_data=F("data_prevista"), mov_valor=F("valor_previsto"),
        ), "", "", F("descricao"), F("origem")))
    return linhas[0].union(*linhas[1:], all=True).order_by("data", "tipo", "referencia_id")


def recorte_planejamento(parametros, hoje=None):
    hoje = hoje or timezone.localdate()
    mes = (parametros.get("mes") or "").strip()
    sem_data = parametros.get("sem_data") == "1"
    _, inicio, fim = periodo_vencimento({"periodo": "mes", "mes": mes}, hoje)
    if inicio is None:
        _, inicio, fim = periodo_vencimento({"periodo": "este_mes"}, hoje)
    filtros = {campo: _inteiro_positivo(parametros.get(campo)) for campo in ("obra", "fornecedor", "apropriacao")}
    for campo, escolhas in (("origem", ORIGENS_PLANEJAMENTO), ("certeza", PrevisaoFinanceira.Certeza.values)):
        valor = parametros.get(campo)
        filtros[campo] = valor if valor in escolhas else ""
    fontes = list(_fontes(filtros))
    return {
        "mes": f"{inicio.year:04d}-{inicio.month:02d}", "inicio": inicio, "fim": fim, "filtros": filtros,
        "sem_data": sem_data, "fontes": fontes, "linhas": _linhas_periodo(fontes, inicio, fim, sem_data),
    }


def rotular_linha_planejamento(linha):
    tipo = linha["tipo"]
    return {
        **linha,
        "tipo_rotulo": "Saldo programado" if linha["programado"] else TIPOS_PLANEJAMENTO[tipo],
        "origem_rotulo": ORIGENS_PLANEJAMENTO.get(linha["origem"], linha["origem"]),
        "certeza_rotulo": dict(PrevisaoFinanceira.Certeza.choices).get(linha["certeza"], linha["certeza"]),
    }


def resumo_planejamento(recorte):
    inicio, fim, sem_data = (recorte[campo] for campo in ("inicio", "fim", "sem_data"))
    meses = _meses_de_analise(inicio)
    ultimo = meses[-1]
    fim_tendencia = date(ultimo.year + (ultimo.month == 12), ultimo.month % 12 + 1, 1) - timedelta(days=1)
    totais = dict.fromkeys((*TIPOS_PLANEJAMENTO, "PROGRAMADO", "COMPROMISSO_FUTURO"), ZERO)
    por_mes = {mes: dict.fromkeys(("PREVISAO", "SALDO", "PAGO", "COMPROMISSO_FUTURO"), ZERO) for mes in meses}
    por_obra = []
    filtros = recorte["filtros"]
    if not sem_data and not filtros["certeza"] and filtros["origem"] in ("", TituloPagar.Origem.COMPRA):
        por_data = compromissos_datados(
            meses[0], fim_tendencia, obra_ids=[filtros["obra"]] if filtros["obra"] else None,
            apropriacao=filtros["apropriacao"], fornecedor=filtros["fornecedor"],
        )
        for data, valor in por_data.items():
            por_mes[data.replace(day=1)]["COMPROMISSO_FUTURO"] += valor
        totais["COMPROMISSO_FUTURO"] = por_mes[inicio]["COMPROMISSO_FUTURO"]
    for tipo, qs, *_ in recorte["fontes"]:
        periodo = qs.filter(mov_data__isnull=True) if sem_data else qs.filter(mov_data__range=(inicio, fim))
        if tipo in {"PREVISAO", "SALDO", "PAGO"} and not sem_data:
            mensal = qs.filter(mov_data__range=(meses[0], fim_tendencia)).order_by().annotate(
                mes=TruncMonth("mov_data"),
            ).values("mes")
            acumuladores = {"total": Sum("mov_valor")}
            if tipo == "SALDO":
                acumuladores["programado"] = Sum("mov_valor", filter=Q(data_programada_vigente__isnull=False))
            for linha in mensal.annotate(**acumuladores):
                mes, valor = linha["mes"], (linha["total"] or ZERO).quantize(CENTAVO)
                por_mes[mes][tipo] = valor
                if mes == inicio:
                    totais[tipo] = valor
                    if tipo == "SALDO":
                        totais["PROGRAMADO"] = (linha["programado"] or ZERO).quantize(CENTAVO)
        else:
            totais[tipo] = (periodo.aggregate(total=Sum("mov_valor"))["total"] or ZERO).quantize(CENTAVO)
        if tipo == "PAGO" and not sem_data:
            por_obra = list(periodo.order_by().values("titulo__obra_id", "titulo__obra__nome").annotate(
                total=Sum("mov_valor"),
            ).order_by("-total", "titulo__obra_id")[:10])
    return {"totais": totais, "por_mes": por_mes if not sem_data else {}, "por_obra": por_obra}
