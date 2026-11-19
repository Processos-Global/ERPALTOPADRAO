from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import Fornecedor
from financeiro.models import PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import (
    PERIODOS, filtrar_por_vencimento, filtrar_titulos_base,
    indicadores_agenda, periodo_vencimento,
)
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def agenda_pagamentos(request):
    hoje = timezone.localdate()
    codigo, inicio, fim = periodo_vencimento(request.GET, hoje)
    base = filtrar_titulos_base(request.GET)
    titulos = filtrar_por_vencimento(base, inicio, fim)
    periodo_invalido = (
        (codigo == "data" and inicio is None)
        or (codigo == "intervalo" and (inicio is None or fim is None or inicio > fim))
        or (codigo == "mes" and inicio is None)
    )
    if periodo_invalido:
        titulos = base.none()
    indicadores = indicadores_agenda(base, titulos, hoje, inicio, fim) if not periodo_invalido else None
    page_obj = Paginator(
        titulos.select_related("obra", "fornecedor", "plano_financeiro", "pagamento")
        .order_by("vencimento", "numero"), 40
    ).get_page(request.GET.get("page"))
    filtros_paginacao = request.GET.copy()
    filtros_paginacao.pop("page", None)
    return render(request, "financeiro/agenda.html", {
        "page_obj": page_obj,
        "indicadores": indicadores,
        "periodos": PERIODOS,
        "periodo": codigo,
        "periodo_invalido": periodo_invalido,
        "filtros": request.GET,
        "status_choices": TituloPagar.Status.choices,
        "obras": Obra.objects.order_by("id"),
        "fornecedores": Fornecedor.objects.filter(ativo=True).order_by("nome"),
        "apropriacoes": PlanoFinanceiro.objects.filter(ativo=True, pai__isnull=False)
        .select_related("pai").order_by("pai__codigo", "codigo", "nome"),
        "query_string": filtros_paginacao.urlencode(),
    })
