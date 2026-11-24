from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.agenda import _inteiro_positivo, recorte_contas_a_pagar, saldo_titulo_sql
from financeiro.services.aprovacoes import decidir_titulo
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


@financeiro_acao_required("APROVAR")
def aprovacoes_lista(request):
    filtros = request.GET.copy()
    filtros["status"] = TituloPagar.Status.AGUARDANDO_APROVACAO
    filtros.pop("atalho", None)
    _, qs, *_ = recorte_contas_a_pagar(filtros, timezone.localdate())
    total = qs.aggregate(valor=Sum(saldo_titulo_sql()))["valor"] or Decimal("0")
    titulos = qs.select_related("fornecedor", "obra", "pedido", "plano_financeiro", "plano_financeiro__pai").order_by("vencimento", "id")
    pagina = Paginator(titulos, 40).get_page(request.GET.get("page"))
    return render(request, "financeiro/aprovacoes.html", {
        "titulos": pagina, "page_obj": pagina,
        "total": total.quantize(Decimal("0.01")),
        "obras": Obra.objects.order_by("nome"),
        "origem_choices": TituloPagar.Origem.choices,
        "filtros": filtros,
    })


@financeiro_acao_required("APROVAR")
@require_POST
def aprovacoes_lote(request):
    ids = {identificador for texto in request.POST.getlist("titulo") if (identificador := _inteiro_positivo(texto))}
    aprovados = 0
    erros = []
    for titulo in TituloPagar.objects.filter(pk__in=ids, status=TituloPagar.Status.AGUARDANDO_APROVACAO):
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
        messages.success(request, f"{aprovados} conta(s) aprovada(s).")
    if not ids:
        messages.warning(request, "Selecione ao menos uma conta.")
    for erro in erros[:5]:
        messages.error(request, erro)
    return redirect("financeiro:aprovacoes")
