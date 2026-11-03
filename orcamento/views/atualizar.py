from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from orcamento.models import ImportacaoOrcamento
from orcamento.services.importar import ImportacaoOrcamentoError, atualizar_orcamento


@login_required
def painel_orcamento(request):
    ultima_importacao = ImportacaoOrcamento.objects.order_by("-criado_em").first()
    return render(
        request,
        "orcamento/atualizar.html",
        {"ultima_importacao": ultima_importacao},
    )


@login_required
@require_POST
def atualizar_orcamento_view(request):
    try:
        resultado = atualizar_orcamento(
            executado_por=request.user,
            forcar=request.POST.get("forcar") == "1",
        )
    except ImportacaoOrcamentoError as exc:
        messages.error(request, f"Não foi possível atualizar o orçamento: {exc}")
    else:
        if resultado.erros_por_arquivo:
            messages.warning(request, resultado.importacao.mensagem)
        else:
            messages.success(request, resultado.importacao.mensagem)

    return redirect("orcamento:atualizar")
