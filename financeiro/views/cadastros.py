from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from financeiro.forms import DespesaRecorrenteForm, PlanoFinanceiroForm
from financeiro.models import DespesaRecorrente, PlanoFinanceiro
from financeiro.services.permissoes import financeiro_acao_required


def _crud(request, *, form_class, queryset, template, redirect_name, instance=None, usuario_field=None):
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if usuario_field and not getattr(obj, f"{usuario_field}_id", None):
                setattr(obj, usuario_field, request.user)
            obj.save()
            messages.success(request, "Registro salvo com sucesso.")
            return redirect(redirect_name)
    else:
        form = form_class(instance=instance)
    return render(request, template, {"form": form, "registros": queryset, "instance": instance})


@financeiro_acao_required("ADMINISTRAR")
def plano_financeiro(request, pk=None):
    instance = get_object_or_404(PlanoFinanceiro, pk=pk) if pk else None
    return _crud(
        request,
        form_class=PlanoFinanceiroForm,
        queryset=PlanoFinanceiro.objects.select_related("pai").all(),
        template="financeiro/plano_financeiro.html",
        redirect_name="financeiro:plano_financeiro",
        instance=instance,
    )


@financeiro_acao_required("ADMINISTRAR")
def despesas_recorrentes(request, pk=None):
    instance = get_object_or_404(DespesaRecorrente, pk=pk) if pk else None
    return _crud(
        request,
        form_class=DespesaRecorrenteForm,
        queryset=DespesaRecorrente.objects.select_related("fornecedor", "obra", "plano_financeiro").all(),
        template="financeiro/despesas_recorrentes.html",
        redirect_name="financeiro:despesas_recorrentes",
        instance=instance,
        usuario_field="criado_por",
    )
