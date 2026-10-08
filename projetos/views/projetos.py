import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from cadastros.models import ChecklistProjetoGrupo, ChecklistProjetoItem
from obras.models import Obra
from projetos.forms import AlteracaoProjetoForm
from projetos.models import (
    AlteracaoProjeto,
    ChecklistProjetoHistorico,
    ChecklistProjetoResposta,
    StatusChecklistProjeto,
)


def _obra_label(obra):
    if not obra:
        return ""

    codigo = (getattr(obra, "codigo", "") or "").strip()
    nome = (getattr(obra, "nome", "") or "").strip()

    # Exibe somente o nome amigável da obra. O código fica apenas como
    # fallback quando o nome não estiver preenchido. Isso evita duplicidade
    # visual em obras cujo código e nome representam a mesma identificação.
    return nome or codigo or str(obra)


def _checklist_contexto(request, tipo):
    obras = list(Obra.objects.filter(ativa=True).order_by("codigo", "nome"))
    obra_id = (request.GET.get("obra") or "").strip()
    obra = None
    if obra_id.isdigit():
        obra = next((o for o in obras if o.pk == int(obra_id)), None)
    if obra is None and obras:
        obra = obras[0]

    grupos = list(
        ChecklistProjetoGrupo.objects
        .filter(tipo=tipo, ativo=True)
        .prefetch_related("itens")
        .order_by("ordem", "nome", "id")
    )
    grupo_slug = (request.GET.get("grupo") or "").strip()
    grupo = next((g for g in grupos if g.slug == grupo_slug), None) if grupo_slug else None
    if grupo is None and grupos:
        grupo = grupos[0]

    itens = []
    respostas = {}
    if grupo and obra:
        itens = list(grupo.itens.filter(ativo=True).order_by("ordem", "id"))
        respostas = {
            r.item_id: r
            for r in ChecklistProjetoResposta.objects.filter(
                obra=obra,
                item_id__in=[i.id for i in itens],
            ).select_related("atualizado_por")
        }

    linhas = []
    for item in itens:
        resposta = respostas.get(item.id)
        linhas.append({
            "item": item,
            "resposta": resposta,
            "status": resposta.status if resposta else StatusChecklistProjeto.NAO_RECEBIDO,
            "observacao": resposta.observacao if resposta else "",
        })

    obra_opcoes = [{"id": o.pk, "label": _obra_label(o)} for o in obras]

    return {
        "tipo_checklist": tipo,
        "tipo_titulo": dict(ChecklistProjetoGrupo.TIPO_CHOICES).get(tipo, tipo),
        "obras": obras,
        "obra_opcoes": obra_opcoes,
        "obra": obra,
        "obra_label": _obra_label(obra) if obra else "",
        "grupos": grupos,
        "grupo": grupo,
        "linhas": linhas,
        "status_choices": StatusChecklistProjeto.choices,
    }


@login_required
def checklist_compatibilizacao(request):
    return render(
        request,
        "projetos/checklist.html",
        _checklist_contexto(request, ChecklistProjetoGrupo.TIPO_COMPATIBILIZACAO),
    )


@login_required
def checklist_documental(request):
    return render(
        request,
        "projetos/checklist.html",
        _checklist_contexto(request, ChecklistProjetoGrupo.TIPO_DOCUMENTAL),
    )


@login_required
@require_POST
@transaction.atomic
def checklist_salvar_celula(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "erro": "Dados inválidos."}, status=400)

    obra = get_object_or_404(Obra, pk=payload.get("obra_id"), ativa=True)
    item = get_object_or_404(ChecklistProjetoItem, pk=payload.get("item_id"), ativo=True)
    campo = (payload.get("campo") or "").strip().lower()
    valor = payload.get("valor")
    if valor is None:
        valor = ""
    valor = str(valor).strip()

    resposta, _ = ChecklistProjetoResposta.objects.select_for_update().get_or_create(
        obra=obra,
        item=item,
        defaults={
            "status": StatusChecklistProjeto.NAO_RECEBIDO,
            "observacao": "",
            "atualizado_por": request.user,
        },
    )

    if campo == "status":
        permitidos = {k for k, _ in StatusChecklistProjeto.choices}
        if valor not in permitidos:
            return JsonResponse({"ok": False, "erro": "Status inválido."}, status=400)
        anterior = resposta.status
        novo = valor
        historico_campo = ChecklistProjetoHistorico.CAMPO_STATUS
        resposta.status = novo
    elif campo == "observacao":
        anterior = resposta.observacao or ""
        novo = valor
        historico_campo = ChecklistProjetoHistorico.CAMPO_OBSERVACAO
        resposta.observacao = novo
    else:
        return JsonResponse({"ok": False, "erro": "Campo inválido."}, status=400)

    if anterior != novo:
        resposta.atualizado_por = request.user
        resposta.save()
        ChecklistProjetoHistorico.objects.create(
            resposta=resposta,
            campo=historico_campo,
            valor_anterior=anterior,
            valor_novo=novo,
            alterado_por=request.user,
        )

    return JsonResponse({
        "ok": True,
        "status": resposta.status,
        "status_label": resposta.get_status_display(),
        "observacao": resposta.observacao,
        "historico": resposta.historico.count(),
    })


@login_required
@require_GET
def checklist_historico(request, obra_id, item_id):
    resposta = (
        ChecklistProjetoResposta.objects
        .filter(obra_id=obra_id, item_id=item_id)
        .select_related("obra", "item")
        .first()
    )
    if not resposta:
        return JsonResponse({"ok": True, "historico": [], "titulo": "Sem alterações registradas."})

    historico = []
    for h in resposta.historico.select_related("alterado_por").all()[:100]:
        usuario = "-"
        if h.alterado_por:
            usuario = h.alterado_por.get_full_name() or h.alterado_por.get_username()
        historico.append({
            "campo": h.get_campo_display(),
            "anterior": h.valor_anterior,
            "novo": h.valor_novo,
            "usuario": usuario,
            "data": h.alterado_em.strftime("%d/%m/%Y %H:%M"),
        })

    return JsonResponse({
        "ok": True,
        "titulo": resposta.item.entrega_atividade,
        "historico": historico,
    })


@login_required
def alteracoes_projeto(request):
    form = AlteracaoProjetoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        registro = form.save(commit=False)
        registro.criado_por = request.user
        registro.save()
        return redirect("projetos:alteracoes")

    obra_id = (request.GET.get("obra") or "").strip()
    obras = list(Obra.objects.filter(ativa=True).order_by("codigo", "nome"))
    qs = AlteracaoProjeto.objects.select_related("obra", "criado_por")
    if obra_id.isdigit():
        qs = qs.filter(obra_id=int(obra_id))

    alteracoes = []
    for registro in qs[:300]:
        alteracoes.append({
            "obj": registro,
            "obra_label": _obra_label(registro.obra),
        })

    return render(request, "projetos/alteracoes.html", {
        "form": form,
        "alteracoes": alteracoes,
        "obra_opcoes": [{"id": o.pk, "label": _obra_label(o)} for o in obras],
        "obra_id": obra_id,
    })
