from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import PedidoCompra
from financeiro.models import Pagamento, PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import _data, _inteiro_positivo, saldo_titulo_sql
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, previsoes_independentes, serie_desembolsos
from financeiro.services.indicadores_gerenciais import _filtros
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


ABAS_INDICADORES = (
    ("geral", "Geral"), ("obras", "Obras"), ("custos", "Custos"), ("fornecedores", "Fornecedores"),
)
ZERO = Decimal("0.00")


def _centavos(valor):
    return (valor or ZERO).quantize(Decimal("0.01"))


def _agrupado(qs, campos, valor):
    linhas = qs.order_by().values(*campos).annotate(total=Sum(valor), quantidade=Count("pk")).order_by("-total", *campos)
    return [{**linha, "total": _centavos(linha["total"])} for linha in linhas]


def _por_entidade(pagos, abertos, pedidos, nome, rotulo_vazio):
    linhas = {}
    for qs, prefixo, chave, valor in (
        (pagos, "titulo__", "pago", "valor"),
        (abertos, "", "aberto", saldo_titulo_sql()),
        (pedidos, "", "contratado", "valor_total"),
    ):
        if qs is None:
            continue
        id_campo = f"{prefixo}{nome}_id"
        titulo_campo = f"{prefixo}{nome}__nome"
        for resultado in _agrupado(qs, (id_campo, titulo_campo), valor):
            identificador = resultado[id_campo]
            linha = linhas.setdefault(identificador, {
                "id": identificador, "nome": resultado[titulo_campo] or rotulo_vazio,
                "pago": ZERO, "aberto": ZERO, "contratado": ZERO if pedidos is not None else None,
            })
            linha[chave] = resultado["total"]
    return sorted(linhas.values(), key=lambda x: (-x["pago"], -x["aberto"], x["nome"]))


def contexto_indicadores(parametros, hoje):
    inicio = _data(parametros.get("inicio")) or date(hoje.year, 1, 1)
    fim = _data(parametros.get("fim")) or hoje
    obra_ids = {i for v in parametros.getlist("obras") if (i := _inteiro_positivo(v))}
    obra = _inteiro_positivo(parametros.get("obra"))
    if obra:
        obra_ids.add(obra)
    escopo = {"obra_ids": sorted(obra_ids)}
    for campo in ("classe", "apropriacao", "fornecedor"):
        escopo[campo] = _inteiro_positivo(parametros.get(campo))
    origem = parametros.get("origem", "")
    origem = origem if origem in TituloPagar.Origem.values else ""
    aba = parametros.get("aba")
    aba = aba if aba in dict(ABAS_INDICADORES) else "geral"
    pagos = _filtros(
        Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO, data_pagamento__range=(inicio, fim)),
        prefixo="titulo__", **escopo,
    )
    abertos = _filtros(TituloPagar.objects.filter(status__in=STATUS_ABERTOS), **escopo)
    if origem:
        pagos = pagos.filter(titulo__origem=origem)
        abertos = abertos.filter(origem=origem)
    abertos_periodo = abertos.filter(vencimento__range=(inicio, fim))
    pedidos = None
    if not (escopo["classe"] or escopo["apropriacao"]) and origem in {"", "COMPRA", "GRANDE_FORNECEDOR"}:
        pedidos = PedidoCompra.objects.filter(data__range=(inicio, fim)).exclude(status=PedidoCompra.Status.CANCELADO)
        if obra_ids:
            pedidos = pedidos.filter(obra_id__in=obra_ids)
        if escopo["fornecedor"]:
            pedidos = pedidos.filter(fornecedor_id=escopo["fornecedor"])
        if origem:
            pedidos = pedidos.filter(processo__fluxo_grande_fornecedor=(origem == "GRANDE_FORNECEDOR"))

    contexto = {
        "inicio": inicio, "fim": fim, "aba": aba, "abas": ABAS_INDICADORES, "obras_ids": escopo["obra_ids"],
        "filtros": {"obra": obra, "origem": origem, **escopo},
        "origens": TituloPagar.Origem.choices,
    }
    if aba == "obras":
        linhas = _por_entidade(pagos, abertos_periodo, pedidos, "obra", "Sem obra")
        areas = dict(Obra.objects.filter(pk__in=[l["id"] for l in linhas if l["id"]], area_construida__gt=0).values_list("pk", "area_construida"))
        for linha in linhas:
            area = areas.get(linha["id"])
            linha["custo_m2"] = _centavos(linha["pago"] / area) if area else None
        contexto["por_obra"] = linhas
        contexto["por_entidade"] = linhas
    elif aba == "custos":
        contexto["por_classe"] = _agrupado(pagos, ("titulo__plano_financeiro__pai__nome",), "valor")
        contexto["por_apropriacao"] = _agrupado(pagos, ("titulo__plano_financeiro__codigo", "titulo__plano_financeiro__nome"), "valor")
    elif aba == "fornecedores":
        contexto["por_fornecedor"] = _por_entidade(pagos, abertos_periodo, pedidos, "fornecedor", "Sem fornecedor cadastrado")
        contexto["por_entidade"] = contexto["por_fornecedor"]
    else:
        pagamento = pagos.aggregate(total=Sum("valor"), quantidade=Count("pk"))
        origens = dict(TituloPagar.Origem.choices)
        por_origem = [
            {"codigo": linha["origem"], "rotulo": origens.get(linha["origem"], linha["origem"] or "Sem origem"),
             "total": linha["total"], "quantidade": linha["quantidade"]}
            for linha in _agrupado(abertos_periodo, ("origem",), saldo_titulo_sql())
        ]
        extras = _filtros(previsoes_independentes(), **escopo)
        if origem:
            extras = extras.filter(origem=origem)

        serie = serie_desembolsos(inicio=hoje, dias=84, origem=origem, **escopo)["serie"]
        pontos = [
            {"rotulo": grupo[-1]["data"].strftime("%d/%m"), "saida": sum((x["saida"] for x in grupo), ZERO)}
            for indice in range(0, len(serie), 7) if (grupo := serie[indice:indice + 7])
        ]
        contexto.update(
            total_pago=_centavos(pagamento["total"]), quantidade_pagamentos=pagamento["quantidade"],
            total_aberto=sum((linha["total"] for linha in por_origem), ZERO),
            total_previsto=_centavos(extras.filter(data_prevista__range=(inicio, fim)).aggregate(total=Sum("valor_previsto"))["total"]),
            total_contratado=_centavos(pedidos.aggregate(total=Sum("valor_total"))["total"]) if pedidos is not None else None,
            por_origem=por_origem,
            por_mes=sorted(_agrupado(pagos.annotate(mes=TruncMonth("data_pagamento")), ("mes",), "valor"), key=lambda x: x["mes"]),
            previsao_30=sum((x["saida"] for x in serie[:31]), ZERO),
            pontos_desembolso=pontos,
            max_pontos_desembolso=max((ponto["saida"] for ponto in pontos), default=ZERO) or Decimal("1"),
        )
    return contexto


@financeiro_acao_required("VISUALIZAR")
def indicadores(request):
    contexto = contexto_indicadores(request.GET, timezone.localdate())
    contexto.update(
        obras=Obra.objects.order_by("nome"),
        fornecedor_selecionado=Fornecedor.objects.filter(pk=contexto["filtros"]["fornecedor"]).first(),
        classes_financeiras=PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=True),
        apropriacoes=PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=False).select_related("pai"),
    )
    return render(request, "financeiro/indicadores.html", contexto)
