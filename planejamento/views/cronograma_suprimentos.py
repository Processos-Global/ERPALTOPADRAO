from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.db.models import Avg, Count, Max, Min, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from planejamento.models import ImportacaoCronogramaSuprimentos, ItemCronogramaSuprimento
from usuarios.decorators import algum_modulo_required, modulo_required
from usuarios.models import ModuloSistema, NivelPermissao
from planejamento.services.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentosError,
    importar_cronograma_suprimentos,
    montar_painel_cronograma_suprimentos,
    montar_kanban_cronograma_suprimentos,
)


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
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


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
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


@modulo_required(ModuloSistema.SUPRIMENTOS, NivelPermissao.ADMINISTRADOR)
@require_POST
def atualizar_cronograma_suprimentos(request):
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


@modulo_required(ModuloSistema.SUPRIMENTOS, NivelPermissao.EDICAO)
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


def _formatar_moeda(valor):
    if valor is None:
        return "—"
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
def historico_item_cronograma_suprimentos(request, item_id):
    item = get_object_or_404(
        ItemCronogramaSuprimento.objects.select_related(
            "cronograma_obra",
            "cronograma_obra__importacao",
            "cronograma_obra__obra",
        ),
        pk=item_id,
        cronograma_obra__importacao__ativa=True,
        cronograma_obra__importacao__status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
    )

    from compras.models import HistoricoCompraSuprimento
    from compras.services.historico_suprimentos import normalizar_suprimento

    chave = normalizar_suprimento(item.item)

    historico = (
        HistoricoCompraSuprimento.objects
        .filter(
            Q(suprimentos_referencia__chave=chave)
            | Q(suprimento_chave=chave)
        )
        .select_related("obra", "fornecedor", "processo", "pedido")
        .prefetch_related("suprimentos_referencia")
        .distinct()
        .order_by("-data_fechamento", "-id")
    )

    resumo = historico.aggregate(
        total=Count("id"),
        media=Avg("valor"),
        menor=Min("valor"),
        maior=Max("valor"),
    )

    registros = []
    for registro in historico:
        registros.append({
            "id": registro.pk,
            "suprimento_historico": registro.suprimento,
            "suprimento_agrupado": registro.suprimentos_referencia.count() > 1,
            "obra": registro.obra_nome or (str(registro.obra) if registro.obra_id else registro.obra_codigo) or "—",
            "obra_codigo": registro.obra_codigo or "",
            "fornecedor": registro.fornecedor_nome or "—",
            "valor": str(registro.valor),
            "valor_formatado": _formatar_moeda(registro.valor),
            "data_fechamento": registro.data_fechamento.strftime("%d/%m/%Y") if registro.data_fechamento else "—",
            "origem": registro.get_origem_display(),
            "processo": registro.processo.numero if registro.processo_id else "",
            "pedido": registro.pedido.numero if registro.pedido_id else "",
        })

    ultima = (
        historico
        .filter(data_fechamento__isnull=False)
        .order_by("-data_fechamento", "-id")
        .first()
    )

    return JsonResponse({
        "suprimento": item.item,
        "total": resumo["total"] or 0,
        "media": _formatar_moeda(resumo["media"]),
        "menor": _formatar_moeda(resumo["menor"]),
        "maior": _formatar_moeda(resumo["maior"]),
        "ultima": {
            "valor": _formatar_moeda(ultima.valor),
            "data": ultima.data_fechamento.strftime("%d/%m/%Y"),
            "obra": ultima.obra_nome or (str(ultima.obra) if ultima.obra_id else ultima.obra_codigo) or "—",
            "fornecedor": ultima.fornecedor_nome or "—",
        } if ultima else None,
        "registros": registros,
    })


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
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
