from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from cadastros.forms import ItemModeloFVSFormSet, ModeloFVSForm
from cadastros.models import ModeloFVS
from cadastros.views.cadastros import cadastros_permissao_required, _permissoes_contexto


@cadastros_permissao_required("visualizar")
def modelos_fvs_lista(request):
    qs = ModeloFVS.objects.prefetch_related("itens")
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "ativos").strip()
    if q:
        qs = qs.filter(nome__icontains=q)
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    return render(request, "cadastros/fvs/lista.html", {
        "modelos": qs,
        "q": q,
        "status": status,
        **_permissoes_contexto(request.user),
    })


def _modelo_form(request, instance=None):
    form = ModeloFVSForm(request.POST or None, instance=instance)
    formset = ItemModeloFVSFormSet(request.POST or None, instance=instance, prefix="itens")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            modelo = form.save()
            formset.instance = modelo
            formset.save()
        messages.success(request, "Modelo de FVS salvo com sucesso.")
        return redirect("cadastros:modelos_fvs_lista")
    return render(request, "cadastros/fvs/form.html", {
        "form": form,
        "formset": formset,
        "modelo": instance,
        **_permissoes_contexto(request.user),
    })


@cadastros_permissao_required("criar")
def modelo_fvs_novo(request):
    return _modelo_form(request)


@cadastros_permissao_required("editar")
def modelo_fvs_editar(request, pk):
    modelo = get_object_or_404(ModeloFVS, pk=pk)
    return _modelo_form(request, modelo)
