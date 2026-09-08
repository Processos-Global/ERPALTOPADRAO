from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from financeiro.forms import PagamentoForm
from financeiro.models import Pagamento, TituloPagar
from financeiro.services.pagamentos import estornar_pagamento, registrar_pagamento
from financeiro.services.permissoes import financeiro_acao_required


@financeiro_acao_required("VISUALIZAR")
def pagamentos_lista(request):
    qs = Pagamento.objects.select_related(
        "titulo", "titulo__fornecedor", "titulo__obra", "titulo__plano_financeiro", "registrado_por"
    ).order_by("-data_pagamento", "-id")
    page_obj = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "financeiro/pagamentos.html", {"page_obj": page_obj})


@financeiro_acao_required("PAGAR")
def pagamento_novo(request, titulo_id):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related("fornecedor", "obra", "plano_financeiro"),
        pk=titulo_id,
    )

    pagamento_existente = Pagamento.objects.filter(titulo=titulo).first()
    if (pagamento_existente and pagamento_existente.status == Pagamento.Status.EFETIVADO) or titulo.status == TituloPagar.Status.PAGO:
        messages.warning(request, "Este título já possui pagamento registrado.")
        return redirect("financeiro:titulos")

    if titulo.status != TituloPagar.Status.APROVADO:
        messages.error(request, "O título precisa estar aprovado antes de registrar o pagamento.")
        return redirect("financeiro:titulos")

    if request.method == "POST":
        form = PagamentoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                pagamento = registrar_pagamento(
                    titulo=titulo,
                    data_pagamento=form.cleaned_data["data_pagamento"],
                    forma=form.cleaned_data["forma"],
                    comprovante=form.cleaned_data.get("comprovante"),
                    referencia_bancaria=form.cleaned_data.get("referencia_bancaria", ""),
                    observacao=form.cleaned_data.get("observacao", ""),
                    usuario=request.user,
                )
                messages.success(request, f"Pagamento de R$ {pagamento.valor:,.2f} confirmado.")
                return redirect("financeiro:titulos")
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
    else:
        form = PagamentoForm(initial={"data_pagamento": timezone.localdate()})

    return render(request, "financeiro/pagamento_form.html", {"form": form, "titulo": titulo})


@financeiro_acao_required("PAGAR")
@require_POST
def pagamento_estornar(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    estornar_pagamento(
        pagamento,
        usuario=request.user,
        motivo=(request.POST.get("motivo") or "").strip(),
    )
    messages.success(request, "Pagamento estornado. O título voltou para o status Aprovado.")
    return redirect("financeiro:pagamentos")
