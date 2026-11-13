from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cadastros.forms import ChecklistProjetoGrupoForm, ChecklistProjetoItemForm
from cadastros.models import ChecklistProjetoGrupo, ChecklistProjetoItem
from cadastros.views.cadastros import cadastros_permissao_required, _permissoes_contexto


@cadastros_permissao_required("visualizar")
def checklist_projetos_lista(request):
    q = (request.GET.get("q") or "").strip()
    grupo_id = (request.GET.get("grupo") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip().upper()
    if tipo not in dict(ChecklistProjetoGrupo.TIPO_CHOICES):
        tipo = ""

    grupos_filtro = (
        ChecklistProjetoGrupo.objects
        .annotate(total_itens=Count("itens", filter=Q(itens__ativo=True)))
        .order_by("tipo", "ordem", "nome", "id")
    )

    itens = (
        ChecklistProjetoItem.objects
        .select_related("grupo")
        .order_by("grupo__ordem", "grupo__nome", "ordem", "id")
    )

    if tipo:
        grupos_filtro = grupos_filtro.filter(tipo=tipo)
        itens = itens.filter(grupo__tipo=tipo)
    if grupo_id.isdigit():
        itens = itens.filter(grupo_id=int(grupo_id), **({"grupo__tipo": tipo} if tipo else {}))

    if q:
        itens = itens.filter(
            Q(grupo__nome__icontains=q)
            | Q(etapa__icontains=q)
            | Q(codigo__icontains=q)
            | Q(entrega_atividade__icontains=q)
        )

    return render(request, "cadastros/checklist_projetos/lista.html", {
        "grupos_filtro": grupos_filtro,
        "itens": itens,
        "q": q,
        "grupo_id": grupo_id,
        "tipo": tipo,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def checklist_grupo_novo(request):
    form = ChecklistProjetoGrupoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Macro checklist cadastrado com sucesso.")
        return redirect("cadastros:checklist_projetos_lista")
    return render(request, "cadastros/checklist_projetos/form.html", {
        "form": form,
        "titulo": "Novo macro checklist",
        "voltar": "cadastros:checklist_projetos_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def checklist_grupo_editar(request, pk):
    obj = get_object_or_404(ChecklistProjetoGrupo, pk=pk)
    form = ChecklistProjetoGrupoForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Macro checklist atualizado com sucesso.")
        return redirect("cadastros:checklist_projetos_lista")
    return render(request, "cadastros/checklist_projetos/form.html", {
        "form": form,
        "titulo": "Editar macro checklist",
        "voltar": "cadastros:checklist_projetos_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def checklist_item_novo(request):
    initial = {}
    grupo_id = (request.GET.get("grupo") or "").strip()
    if grupo_id.isdigit():
        initial["grupo"] = int(grupo_id)
    form = ChecklistProjetoItemForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Item do checklist cadastrado com sucesso.")
        return redirect("cadastros:checklist_projetos_lista")
    return render(request, "cadastros/checklist_projetos/form.html", {
        "form": form,
        "titulo": "Novo item do checklist",
        "voltar": "cadastros:checklist_projetos_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("editar")
def checklist_item_editar(request, pk):
    obj = get_object_or_404(ChecklistProjetoItem, pk=pk)
    form = ChecklistProjetoItemForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Item do checklist atualizado com sucesso.")
        return redirect("cadastros:checklist_projetos_lista")
    return render(request, "cadastros/checklist_projetos/form.html", {
        "form": form,
        "titulo": "Editar item do checklist",
        "voltar": "cadastros:checklist_projetos_lista",
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("excluir")
@require_POST
def checklist_item_excluir(request, pk):
    obj = get_object_or_404(ChecklistProjetoItem, pk=pk)
    obj.ativo = False
    obj.save(update_fields=["ativo"])
    messages.success(request, "Item desativado. O histórico existente foi preservado.")
    return redirect("cadastros:checklist_projetos_lista")
