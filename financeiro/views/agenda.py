from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import Fornecedor
from financeiro.models import PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import (
    PERIODOS, _inteiro_positivo, indicadores_agenda, recorte_contas_a_pagar,
)
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def agenda_pagamentos(request):
    return render(request, "financeiro/titulos_lista.html", contexto_contas_a_pagar(request, timezone.localdate(), agenda=True))


def contexto_contas_a_pagar(request, hoje, *, agenda=False):
    base, titulos, periodo, inicio, fim, invalido, filtros = recorte_contas_a_pagar(request.GET, hoje)
    indicadores = indicadores_agenda(base, titulos, hoje, inicio, fim) if not invalido else None
    page_obj = Paginator(
        titulos.select_related("obra", "fornecedor", "plano_financeiro", "pagamento")
        .order_by("vencimento", "numero"), 40
    ).get_page(request.GET.get("page"))
    filtros_paginacao = request.GET.copy()
    filtros_paginacao.pop("page", None)
    return {
        "agenda": agenda,
        "page_obj": page_obj,
        "indicadores": indicadores,
        "kpi_vencidos": indicadores["vencido"] if indicadores else 0,
        "periodos": PERIODOS,
        "periodo": periodo,
        "periodo_invalido": invalido,
        "mes_entrada": inicio.strftime("%Y-%m") if periodo == "mes" and inicio else "",
        "filtros": filtros,
        "status_choices": TituloPagar.Status.choices,
        "origem_choices": TituloPagar.Origem.choices,
        "conferencia_choices": TituloPagar.Conferencia.choices,
        "obras": Obra.objects.order_by("id"),
        "fornecedor_selecionado": Fornecedor.objects.filter(pk=_inteiro_positivo(filtros.get("fornecedor"))).first(),
        "classes_financeiras": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=True).order_by("codigo", "nome"),
        "apropriacoes": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=False)
        .select_related("pai").order_by("pai__codigo", "codigo", "nome"),
        "query_string": filtros_paginacao.urlencode(),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    }
