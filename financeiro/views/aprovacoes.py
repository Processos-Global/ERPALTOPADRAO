from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Case, F, Q, Sum, When
from django.db.models.functions import Greatest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from cadastros.models import Fornecedor
from financeiro.models import AprovacaoTituloFinanceiro, PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import MOEDA, ZERO, _data, _inteiro_positivo, recorte_contas_a_pagar
from financeiro.services.aprovacoes import decidir_titulo, interpretar_ciclo
from financeiro.services.permissoes import financeiro_acao_required
from obras.models import Obra


def recorte_aprovacoes(parametros, hoje):
    filtros = parametros.copy()
    filtros.pop("atalho", None)
    status = filtros.get("status")
    if status not in {*TituloPagar.Status.values, "todos"}:
        filtros["status"] = "fila"
    _, qs, *_ = recorte_contas_a_pagar(filtros, hoje)
    if filtros["status"] == "fila":
        qs = qs.filter(
            Q(status=TituloPagar.Status.AGUARDANDO_APROVACAO)
            | Q(status=TituloPagar.Status.PREVISTA, recebimento__pedido_id=F("pedido_id")),
        )
    for parametro, campo in (
        ("solicitada_de", "criado_em__date__gte"), ("solicitada_ate", "criado_em__date__lte"),
        ("vencimento_de", "vencimento__gte"), ("vencimento_ate", "vencimento__lte"),
    ):
        if filtros.get(parametro):
            data = _data(filtros[parametro])
            qs = qs.filter(**{campo: data}) if data else qs.none()
    if filtros.get("classificacao") in TituloPagar.Classificacao.values:
        qs = qs.filter(classificacao=filtros["classificacao"])
    qs = qs.annotate(divergente=Case(When(
        Q(conferencia=TituloPagar.Conferencia.DIVERGENCIA) | (
            Q(recebimento__liberacao_financeira__pedido_id=F("pedido_id"))
            & ~Q(recebimento__liberacao_financeira__divergencias_comerciais=[])
        ), then=True,
    ), default=False))
    if filtros.get("divergencia") in {"sim", "nao"}:
        qs = qs.filter(divergente=filtros["divergencia"] == "sim")
    return qs, filtros


@financeiro_acao_required("APROVAR")
@require_safe
def aprovacoes_lista(request):
    qs, filtros = recorte_aprovacoes(request.GET, timezone.localdate())
    valor_liquido = F("valor_original") + F("juros") + F("multa") + F("outros_acrescimos") - F("desconto")
    total = qs.aggregate(valor=Sum(Greatest(valor_liquido, ZERO, output_field=MOEDA)))["valor"] or Decimal("0")
    titulos = qs.select_related(
        "fornecedor", "obra", "pedido__processo", "plano_financeiro__pai", "recebimento", "criado_por",
    ).order_by("vencimento", "id")
    pagina = Paginator(titulos, 40).get_page(request.GET.get("page"))
    return render(request, "financeiro/aprovacoes.html", {
        "titulos": pagina, "page_obj": pagina,
        "total": total.quantize(Decimal("0.01")),
        "obras": Obra.objects.order_by("nome"),
        "fornecedores": Fornecedor.objects.filter(titulos_financeiros__isnull=False).distinct().order_by("nome", "pk"),
        "apropriacoes": PlanoFinanceiro.objects.filter(titulos__isnull=False).select_related("pai").distinct().order_by("codigo"),
        "origem_choices": TituloPagar.Origem.choices,
        "status_choices": TituloPagar.Status.choices,
        "classificacao_choices": TituloPagar.Classificacao.choices,
        "conferencia_choices": TituloPagar.Conferencia.choices,
        "pode_aprovar_lote": any(t.status == TituloPagar.Status.AGUARDANDO_APROVACAO and not t.divergente for t in pagina),
        "filtros": filtros,
    })


@financeiro_acao_required("APROVAR")
@require_POST
def aprovacoes_lote(request):
    ciclos = {}
    for selecao in request.POST.getlist("titulo"):
        pk, _, ciclo_txt = selecao.partition(":")
        identificador, ciclo = _inteiro_positivo(pk), interpretar_ciclo(ciclo_txt)
        if not identificador or ciclo is None or ciclos.get(identificador, ciclo) != ciclo:
            messages.error(request, "Seleção desatualizada. Atualize a lista e selecione novamente as contas.")
            return redirect("financeiro:aprovacoes")
        ciclos[identificador] = ciclo
    if not ciclos:
        messages.warning(request, "Selecione ao menos uma conta.")
        return redirect("financeiro:aprovacoes")

    aprovados = 0
    erros = []
    titulos = TituloPagar.objects.filter(pk__in=ciclos).only("pk", "numero").order_by("pk")
    for titulo in titulos:
        try:
            decidir_titulo(
                titulo,
                usuario=request.user,
                decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,
                ciclo_esperado=ciclos[titulo.pk],
                observacao="Aprovação em lote.",
                em_lote=True,
            )
            aprovados += 1
        except ValidationError as exc:
            erros.append(f"{titulo.numero}: {'; '.join(exc.messages)}")
    if aprovados:
        messages.success(request, f"{aprovados} conta(s) aprovada(s).")
    if len(ciclos) > len(titulos):
        messages.error(request, "Uma ou mais contas da seleção não estão disponíveis.")
    for erro in erros[:5]:
        messages.error(request, erro)
    if len(erros) > 5:
        messages.error(request, f"Outras {len(erros) - 5} conta(s) não foram aprovadas. Consulte a fila para revisar.")
    return redirect("financeiro:aprovacoes")
