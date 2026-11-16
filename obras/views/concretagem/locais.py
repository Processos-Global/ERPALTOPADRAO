"""Locais/estruturas de uso por obra (substitui a importação de EAP do sistema anterior)."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from obras.forms import LocalUsoForm
from obras.models import LocalUsoObra, Obra
from obras.services.concretagem.permissoes import contexto_permissoes, preencher_required, ver_required


def _local_json(local):
    return {
        "id": local.pk, "nome": local.nome, "descricao": local.descricao_completa,
        "tipo": local.tipo, "tipo_label": local.get_tipo_display(),
        "bloco": local.bloco, "pavimento": local.pavimento,
        "volume_estimado": str(local.volume_estimado) if local.volume_estimado is not None else "",
        "ativo": local.ativo,
    }


@ver_required
def locais(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    return render(request, "obras/concretagem/locais.html", {
        "obra": obra,
        "locais": obra.locais_concretagem.all().order_by("-ativo", "ordem", "nome"),
        "form": LocalUsoForm(obra=obra),
        "tipos": LocalUsoObra.Tipo.choices,
        **contexto_permissoes(request.user),
    })


@require_POST
@preencher_required
def local_salvar(request, obra_id, pk=None):
    """Cria ou edita um local. Responde JSON quando chamado pelo modal da solicitação."""
    obra = get_object_or_404(Obra, pk=obra_id)
    instancia = get_object_or_404(LocalUsoObra, pk=pk, obra=obra) if pk else None
    form = LocalUsoForm(request.POST, instance=instancia, obra=obra)
    quer_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if form.is_valid():
        local = form.save(commit=False)
        local.obra = obra
        if not local.pk:
            local.criado_por = request.user
        local.save()
        if quer_json:
            return JsonResponse({"ok": True, "local": _local_json(local)})
        messages.success(request, f"Local “{local.nome}” salvo.")
    else:
        erros = "; ".join(f"{e}" for lista in form.errors.values() for e in lista)
        if quer_json:
            return JsonResponse({"ok": False, "erro": erros}, status=400)
        messages.error(request, erros)
    return redirect("obras:concretagem_locais", obra_id=obra.pk)


@require_POST
@preencher_required
def local_alternar(request, obra_id, pk):
    local = get_object_or_404(LocalUsoObra, pk=pk, obra_id=obra_id)
    local.ativo = not local.ativo
    local.save(update_fields=["ativo", "atualizado_em"])
    messages.success(request, f"Local “{local.nome}” {'reativado' if local.ativo else 'desativado'}.")
    return redirect("obras:concretagem_locais", obra_id=obra_id)


@ver_required
def api_locais(request, obra_id):
    locais_qs = LocalUsoObra.objects.filter(obra_id=obra_id, ativo=True).order_by("ordem", "nome")
    return JsonResponse({"locais": [_local_json(l) for l in locais_qs]})
