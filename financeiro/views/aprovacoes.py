from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.aprovacoes import decidir_titulo
from financeiro.services.permissoes import financeiro_acao_required


@financeiro_acao_required("APROVAR")
def aprovacoes_lista(request):
    qs = (
        TituloPagar.objects.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO)
        .select_related("fornecedor", "obra", "pedido", "plano_financeiro", "plano_financeiro__pai")
        .prefetch_related("pedido__itens")
    )
    busca = (request.GET.get("q") or "").strip()
    obra = (request.GET.get("obra") or "").strip()
    origem = (request.GET.get("origem") or "").strip()
    if busca:
        qs = qs.filter(Q(numero__icontains=busca) | Q(beneficiario_nome__icontains=busca) | Q(fornecedor__nome__icontains=busca) | Q(descricao__icontains=busca))
    if obra:
        qs = qs.filter(obra_id=obra)
    if origem:
        qs = qs.filter(origem=origem)
    titulos = list(qs.order_by("vencimento", "id"))
    return render(request, "financeiro/aprovacoes.html", {
        "titulos": titulos,
        "total": sum((titulo.saldo_aberto for titulo in titulos), Decimal("0")),
        "obras": __import__("obras.models", fromlist=["Obra"]).Obra.objects.all().order_by("nome"),
        "origem_choices": TituloPagar.Origem.choices[:4],
        "filtros": {"q": busca, "obra": obra, "origem": origem},
    })


@financeiro_acao_required("APROVAR")
@require_POST
def aprovacoes_lote(request):
    ids = request.POST.getlist("titulo")
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
