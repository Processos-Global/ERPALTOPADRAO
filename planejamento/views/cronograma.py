from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from planejamento.models import ImportacaoCronograma
from planejamento.services.cronograma import (
    ImportacaoCronogramaError,
    importar_cronograma,
    montar_painel_cronograma,
)
from planejamento.services.cronograma.consultas import CronogramaBaseError


@login_required
def painel_cronograma(request):
    projeto = (request.GET.get("projeto") or "").strip()
    semana_texto = (request.GET.get("semana") or "").strip()

    try:
        semana = int(semana_texto) if semana_texto else None
    except (TypeError, ValueError):
        semana = None

    try:
        contexto = montar_painel_cronograma(
            projeto=projeto or None,
            semana=semana,
        )
    except CronogramaBaseError as exc:
        contexto = {
            "projetos": [],
            "projeto_selecionado": None,
            "semanas": [],
            "semana_selecionada": None,
            "semana_solicitada": semana,
            "possui_dados": False,
            "resumo": None,
            "serie": [],
            "avancos": [],
            "medias": None,
            "prazos": None,
            "marcos": [],
            "contadores_atividades": {},
            "atividades_prioritarias": [],
            "programacao_semana": {},
            "resumo_prioridades": {},
            "disciplinas": [],
            "checklists": {"habitese": {}, "pos_habitese": {}},
            "alertas_painel": [],
            "erro_base": str(exc),
            "importacao_ativa": None,
        }

    return render(request, "planejamento/painel_cronograma.html", contexto)


@login_required
def historico_importacoes_cronograma(request):
    importacoes = (
        ImportacaoCronograma.objects
        .select_related("executado_por")
        .order_by("-criado_em")[:50]
    )
    return render(
        request,
        "planejamento/importacoes_cronograma.html",
        {"importacoes": importacoes},
    )


@login_required
@require_POST
def atualizar_cronograma(request):
    if not request.user.is_superuser:
        messages.error(request, "Você não tem permissão para atualizar o cronograma.")
        return redirect("planejamento:painel_cronograma")

    try:
        resultado = importar_cronograma(
            executado_por=request.user,
            forcar=request.POST.get("forcar") == "1",
        )
    except ImportacaoCronogramaError as exc:
        messages.error(request, f"Não foi possível atualizar o cronograma: {exc}")
    else:
        if resultado.importado:
            messages.success(request, resultado.mensagem)
        else:
            messages.info(request, resultado.mensagem)

    return redirect("planejamento:painel_cronograma")
