from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import QueryDict
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import Fornecedor
from financeiro.models import Pagamento, PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import _inteiro_positivo, filtrar_por_vencimento, filtrar_titulos_base, periodo_vencimento
from financeiro.services.fluxo_caixa import STATUS_ABERTOS, serie_desembolsos
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.views.liberacoes import recorte_liberacoes
from obras.models import Obra


def _resumo_titulos_abertos(abertos, hoje, em_7, em_30):
    """Resume os títulos uma vez, mantendo o saldo calculado pelo modelo."""
    origens = dict(TituloPagar.Origem.choices[:4])
    por_origem = {codigo: {"codigo": codigo, "rotulo": rotulo, "total": Decimal("0"), "quantidade": 0}
                  for codigo, rotulo in origens.items()}
    resumo = {
        "valor_vencidos": Decimal("0"), "qtd_vencidos": 0,
        "valor_7": Decimal("0"), "qtd_7": 0,
        "valor_aprovacao": Decimal("0"), "qtd_aprovacao": 0,
        "valor_30": Decimal("0"),
        "valor_hoje": Decimal("0"), "qtd_hoje": 0,
        "valor_disponivel": Decimal("0"), "qtd_disponivel": 0,
    }
    for titulo in abertos.select_related("pagamento").only(
        "status", "origem", "vencimento", "valor_original", "juros", "multa", "outros_acrescimos", "desconto",
        "pagamento__status", "pagamento__valor",
    ).iterator(chunk_size=1000):
        saldo = titulo.saldo_aberto
        vencimento = titulo.vencimento
        if vencimento is not None:
            if vencimento == hoje:
                resumo["valor_hoje"] += saldo
                resumo["qtd_hoje"] += 1
            if (vencimento <= hoje and titulo.status == TituloPagar.Status.APROVADO
                    and not titulo.esta_pago and saldo > 0):
                resumo["valor_disponivel"] += saldo
                resumo["qtd_disponivel"] += 1
            if vencimento < hoje:
                resumo["valor_vencidos"] += saldo
                resumo["qtd_vencidos"] += 1
            elif vencimento <= em_30:
                resumo["valor_30"] += saldo
                if vencimento <= em_7:
                    resumo["valor_7"] += saldo
                    resumo["qtd_7"] += 1
        if titulo.status == TituloPagar.Status.AGUARDANDO_APROVACAO:
            resumo["valor_aprovacao"] += saldo
            resumo["qtd_aprovacao"] += 1
        if titulo.origem in por_origem:
            linha = por_origem[titulo.origem]
            linha["total"] += saldo
            linha["quantidade"] += 1
    resumo["por_origem"] = [linha for linha in por_origem.values() if linha["total"]]
    return resumo


@financeiro_acao_required("VISUALIZAR")
def dashboard(request):
    hoje = timezone.localdate()
    em_7 = hoje + timedelta(days=7)
    em_30 = hoje + timedelta(days=30)

    dimensoes = {campo: _inteiro_positivo(request.GET.get(campo)) for campo in ("obra", "fornecedor", "classe", "apropriacao")}
    origem = request.GET.get("origem", "")
    dimensoes["origem"] = origem if origem in TituloPagar.Origem.values else ""
    filtros_links = QueryDict(mutable=True)
    filtros_links.update({chave: str(valor) for chave, valor in dimensoes.items() if valor})
    titulos = filtrar_titulos_base(filtros_links)
    abertos = titulos.filter(status__in=STATUS_ABERTOS)
    resumo = _resumo_titulos_abertos(abertos.filter(vencimento__lte=hoje), hoje, em_7, em_30)

    periodo = request.GET.get("periodo", "hoje")
    if periodo not in {"hoje", "vencidas", "7", "intervalo"}:
        periodo = "hoje"
    parametros = request.GET.copy()
    parametros["periodo"] = periodo
    _, inicio, fim = periodo_vencimento(parametros, hoje)
    intervalo = periodo == "intervalo"
    intervalo_invalido = intervalo and (not inicio or not fim or inicio > fim)
    _, inicio_mes, fim_mes = periodo_vencimento({"periodo": "este_mes"}, hoje)
    pagamentos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO)
    if filtros_links:
        pagamentos = pagamentos.filter(titulo__in=titulos)
    pagos_mes = Decimal("0")
    if not intervalo_invalido:
        datas_pagas = (inicio, fim) if intervalo else (inicio_mes, fim_mes)
        pagos_mes = pagamentos.filter(data_pagamento__range=datas_pagas).aggregate(total=Sum("valor"))["total"] or pagos_mes

    desembolsos = serie_desembolsos(
        inicio=hoje, dias=27, obra_id=dimensoes["obra"], fornecedor=dimensoes["fornecedor"],
        classe=dimensoes["classe"], apropriacao=dimensoes["apropriacao"], origem=dimensoes["origem"],
    )
    pontos = []
    acumulado_semana = Decimal("0")
    for idx, item in enumerate(desembolsos["serie"]):
        acumulado_semana += item["saida"]
        if (idx + 1) % 7 == 0 or idx == len(desembolsos["serie"]) - 1:
            pontos.append({"fim": item["data"], "saida": acumulado_semana})
            acumulado_semana = Decimal("0")

    agenda = abertos.none() if intervalo_invalido else filtrar_por_vencimento(abertos, inicio, fim)
    pode_aprovar = possui_acao_financeiro(request.user, "APROVAR")
    pode_pagar = possui_acao_financeiro(request.user, "PAGAR")

    return render(request, "financeiro/dashboard.html", {
        "total_hoje": resumo["valor_hoje"],
        "qtd_hoje": resumo["qtd_hoje"],
        "total_disponivel": resumo["valor_disponivel"],
        "qtd_disponivel": resumo["qtd_disponivel"],
        "total_vencido": resumo["valor_vencidos"],
        "qtd_vencidos": resumo["qtd_vencidos"],
        "pagos_mes": pagos_mes,
        "pagos_intervalo": intervalo and not intervalo_invalido,
        "mes_pago": hoje.strftime("%Y-%m"),
        "agenda": agenda.select_related("fornecedor", "obra", "pagamento").order_by("vencimento", "id")[:12],
        "periodo": periodo, "inicio": inicio, "fim": fim, "intervalo_invalido": intervalo_invalido,
        "inicio_iso": inicio.isoformat() if inicio else "", "fim_iso": fim.isoformat() if fim else "",
        "dimensoes": dimensoes, "filtros_links": filtros_links,
        "obras": Obra.objects.order_by("nome"), "origens": TituloPagar.Origem.choices,
        "fornecedor_selecionado": Fornecedor.objects.filter(pk=dimensoes["fornecedor"]).first(),
        "classes_financeiras": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=True),
        "apropriacoes": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=False).select_related("pai"),
        "desembolsos": pontos, "maior_desembolso": max(ponto["saida"] for ponto in pontos) or Decimal("1"),
        "pode_aprovar": pode_aprovar, "pode_pagar": pode_pagar,
        "liberacoes_pendentes": recorte_liberacoes({**filtros_links.dict(), "pendencias": "1"}).count() if pode_aprovar else 0,
    })
