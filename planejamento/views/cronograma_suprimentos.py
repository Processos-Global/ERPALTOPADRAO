from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from planejamento.models import ImportacaoCronogramaSuprimentos, ItemCronogramaSuprimento
from planejamento.services.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentosError,
    importar_cronograma_suprimentos,
    montar_painel_cronograma_suprimentos,
    montar_kanban_cronograma_suprimentos,
)


@login_required
def painel_cronograma_suprimentos(request):
    contexto = montar_painel_cronograma_suprimentos(
        obra_id=request.GET.get("obra") or None,
        categoria=(request.GET.get("categoria") or "").strip(),
        etapa=(request.GET.get("etapa") or request.GET.get("situacao") or "").strip(),
        busca=(request.GET.get("busca") or "").strip(),
        suprimento=(request.GET.get("suprimento") or "").strip(),
    )

    return render(
        request,
        "planejamento/cronograma_suprimentos.html",
        contexto,
    )


@login_required
def kanban_cronograma_suprimentos(request):
    contexto = montar_kanban_cronograma_suprimentos(
        obra_id=request.GET.get("obra") or None,
        busca=(request.GET.get("busca") or "").strip(),
    )

    return render(
        request,
        "planejamento/kanban_cronograma_suprimentos.html",
        contexto,
    )


@login_required
@require_POST
def atualizar_cronograma_suprimentos(request):
    if not request.user.is_superuser:
        messages.error(
            request,
            "Você não tem permissão para atualizar o cronograma de suprimentos.",
        )
        return redirect("planejamento:painel_cronograma_suprimentos")

    try:
        resultado = importar_cronograma_suprimentos(
            usuario=request.user,
            forcar=request.POST.get("forcar") == "1",
        )

        if resultado.importado:
            messages.success(request, resultado.mensagem)
        else:
            messages.info(request, resultado.mensagem)

    except ImportacaoCronogramaSuprimentosError as exc:
        messages.error(
            request,
            f"Não foi possível atualizar o cronograma de suprimentos: {exc}",
        )

    obra_id = (request.POST.get("obra") or "").strip()
    if obra_id:
        destino = reverse("planejamento:painel_cronograma_suprimentos")
        return redirect(f"{destino}?{urlencode({'obra': obra_id})}")

    return redirect("planejamento:painel_cronograma_suprimentos")


DATAS_REALIZADAS_SUPRIMENTOS = (
    "data_real_cotacao",
    "data_real_compatibilizacao",
    "data_real_negociacao",
    "data_real_contratacao",
)


def _data_post(request, campo):
    valor = (request.POST.get(campo) or "").strip()
    if not valor:
        return None
    data = parse_date(valor)
    if data is None:
        raise ValueError(f"Data inválida no campo {campo}.")
    return data


@login_required
@require_POST
def salvar_datas_item_cronograma_suprimentos(request, item_id):
    """
    Edita somente datas realizadas.

    As datas planejadas/base são importadas da planilha e ficam congeladas na
    interface. No futuro esta mesma camada poderá ser atualizada pelo módulo de
    Compras sem alterar a regra de cálculo do cronograma.
    """
    item = get_object_or_404(
        ItemCronogramaSuprimento.objects.select_related(
            "cronograma_obra",
            "cronograma_obra__importacao",
        ),
        pk=item_id,
        cronograma_obra__importacao__ativa=True,
        cronograma_obra__importacao__status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
    )

    try:
        novas_datas = {
            campo: _data_post(request, campo)
            for campo in DATAS_REALIZADAS_SUPRIMENTOS
        }
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        for campo, valor in novas_datas.items():
            setattr(item, campo, valor)

        item.datas_editadas_manualmente = True
        item.datas_editadas_por = request.user
        item.datas_editadas_em = timezone.now()
        item.save(
            update_fields=[
                *DATAS_REALIZADAS_SUPRIMENTOS,
                "datas_editadas_manualmente",
                "datas_editadas_por",
                "datas_editadas_em",
            ]
        )
        messages.success(
            request,
            f"Andamento de '{item.item}' atualizado para {item.percentual_andamento}%.",
        )

    parametros = {}
    for nome in ("obra", "categoria", "etapa", "busca", "suprimento"):
        valor = (request.POST.get(nome) or "").strip()
        if valor:
            parametros[nome] = valor

    destino = reverse("planejamento:painel_cronograma_suprimentos")
    if parametros:
        destino = f"{destino}?{urlencode(parametros)}"
    return redirect(destino)


@login_required
def historico_importacoes_cronograma_suprimentos(request):
    importacoes = (
        ImportacaoCronogramaSuprimentos.objects
        .select_related("executado_por")
        .order_by("-criado_em")[:50]
    )

    return render(
        request,
        "planejamento/importacoes_cronograma_suprimentos.html",
        {"importacoes": importacoes},
    )
