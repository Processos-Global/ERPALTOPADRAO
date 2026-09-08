from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.aprovacoes import decidir_titulo
from financeiro.services.permissoes import financeiro_acao_required


@financeiro_acao_required("APROVAR")
def aprovacoes_lista(request):
    titulos = list(
        TituloPagar.objects.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO)
        .select_related("fornecedor", "obra", "pedido", "recebimento")
        .order_by("vencimento", "id")
    )
    return render(request, "financeiro/aprovacoes.html", {
        "titulos": titulos,
        "total": sum((titulo.saldo_aberto for titulo in titulos), Decimal("0")),
    })


@financeiro_acao_required("APROVAR")
@require_POST
def aprovacoes_lote(request):
    ids = request.POST.getlist("titulo")
    aprovados = 0
    erros = []

    for titulo in TituloPagar.objects.filter(
        pk__in=ids,
        status=TituloPagar.Status.AGUARDANDO_APROVACAO,
    ):
        try:
            decidir_titulo(
                titulo,
                usuario=request.user,
                decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,
                observacao="Aprovação em lote.",
            )
            aprovados += 1
        except ValidationError as exc:
            erros.append(f"{titulo.numero}: {'; '.join(exc.messages)}")

    if aprovados:
        messages.success(request, f"{aprovados} título(s) aprovado(s).")
    if not ids:
        messages.warning(request, "Selecione ao menos um título.")
    for erro in erros[:5]:
        messages.error(request, erro)
    return redirect("financeiro:aprovacoes")
