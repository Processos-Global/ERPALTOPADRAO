from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cadastros.models import Fornecedor
from financeiro.forms import TituloPagarForm
from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.aprovacoes import decidir_titulo, enviar_para_aprovacao
from financeiro.services.notificacoes import notificar_aprovadores
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.services.titulos import atualizar_titulo, cancelar_titulo, criar_titulos_manuais
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def titulos_lista(request):
    hoje = timezone.localdate()
    qs = TituloPagar.objects.select_related("fornecedor", "obra", "plano_financeiro", "pedido").all()
    busca = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    origem = (request.GET.get("origem") or "").strip()
    obra = (request.GET.get("obra") or "").strip()
    fornecedor = (request.GET.get("fornecedor") or "").strip()
    periodo = (request.GET.get("periodo") or "90").strip()
    atalho = (request.GET.get("atalho") or "").strip()

    if busca:
        qs = qs.filter(
            Q(numero__icontains=busca)
            | Q(documento_numero__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(beneficiario_nome__icontains=busca)
            | Q(fornecedor__nome__icontains=busca)
            | Q(fornecedor__nome_fantasia__icontains=busca)
            | Q(origem_detalhe__icontains=busca)
        )
    if status:
        qs = qs.filter(status=status)
    if origem:
        qs = qs.filter(origem=origem)
    if obra:
        qs = qs.filter(obra_id=obra)
    if fornecedor:
        qs = qs.filter(fornecedor_id=fornecedor)

    if atalho == "vencidos":
        qs = qs.filter(vencimento__lt=hoje).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    elif atalho == "aprovacao":
        qs = qs.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO)
    elif atalho == "sem_data":
        qs = qs.filter(vencimento__isnull=True).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    elif atalho in {"7", "30", "90"}:
        dias = int(atalho)
        qs = qs.filter(vencimento__range=(hoje, hoje + timedelta(days=dias))).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    elif periodo.isdigit() and int(periodo) > 0:
        qs = qs.filter(Q(vencimento__lte=hoje + timedelta(days=int(periodo))) | Q(vencimento__isnull=True))

    page_obj = Paginator(qs.order_by("vencimento", "numero"), 40).get_page(request.GET.get("page"))

    base_abertos = TituloPagar.objects.exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    vencidos = list(base_abertos.filter(vencimento__lt=hoje))
    sete = list(base_abertos.filter(vencimento__range=(hoje, hoje + timedelta(days=7))))
    aprovacao = list(base_abertos.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO))
    sem_data = list(base_abertos.filter(vencimento__isnull=True))

    return render(request, "financeiro/titulos_lista.html", {
        "page_obj": page_obj,
        "status_choices": TituloPagar.Status.choices,
        "origem_choices": TituloPagar.Origem.choices[:4],
        "obras": Obra.objects.all().order_by("id"),
        "fornecedores": Fornecedor.objects.filter(ativo=True).order_by("nome"),
        "filtros": {"q": busca, "status": status, "origem": origem, "obra": obra, "fornecedor": fornecedor, "periodo": periodo, "atalho": atalho},
        "kpi_vencidos": sum((x.saldo_aberto for x in vencidos), Decimal("0")),
        "kpi_7": sum((x.saldo_aberto for x in sete), Decimal("0")),
        "kpi_aprovacao": sum((x.saldo_aberto for x in aprovacao), Decimal("0")),
        "kpi_sem_data": sum((x.saldo_aberto for x in sem_data), Decimal("0")),
        "pode_lancar": possui_acao_financeiro(request.user, "LANCAR_TITULOS"),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    })


@financeiro_acao_required("LANCAR_TITULOS")
def titulo_novo(request):
    if request.method == "POST":
        form = TituloPagarForm(request.POST, request.FILES)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            quantidade = dados.pop("quantidade_parcelas", 1) or 1
            intervalo = dados.pop("intervalo_dias", 30) or 30
            titulos = criar_titulos_manuais(
                usuario=request.user,
                quantidade_parcelas=quantidade,
                intervalo_dias=intervalo,
                **dados,
            )
            for titulo in titulos:
                notificar_aprovadores(titulo)
            if len(titulos) == 1:
                messages.success(request, f"Conta {titulos[0].numero} criada e enviada para aprovação.")
                return redirect("financeiro:titulo_detalhe", pk=titulos[0].pk)
            messages.success(request, f"{len(titulos)} parcelas criadas e enviadas para aprovação.")
            return redirect("financeiro:titulos")
    else:
        form = TituloPagarForm()
    return render(request, "financeiro/titulo_form.html", {"form": form, "modo": "novo"})


@financeiro_acao_required("VISUALIZAR")
def titulo_detalhe(request, pk):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related(
            "fornecedor", "obra", "plano_financeiro", "pedido", "recebimento", "previsao_origem", "pagamento"
        ).prefetch_related("aprovacoes__usuario", "historico__usuario"),
        pk=pk,
    )
    recebimentos = []
    valor_documentado = Decimal("0")
    if titulo.pedido_id:
        recebimentos = list(titulo.pedido.recebimentos.prefetch_related("itens").all())
        valor_documentado = sum((r.valor_total_nota or Decimal("0") for r in recebimentos), Decimal("0"))

    return render(request, "financeiro/titulo_detalhe.html", {
        "titulo": titulo,
        "recebimentos": recebimentos,
        "valor_documentado_pedido": valor_documentado,
        "pode_editar": possui_acao_financeiro(request.user, "EDITAR_TITULOS"),
        "pode_aprovar": possui_acao_financeiro(request.user, "APROVAR"),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    })


@financeiro_acao_required("EDITAR_TITULOS")
def titulo_editar(request, pk):
    titulo = get_object_or_404(TituloPagar.objects.select_related("fornecedor"), pk=pk)
    if titulo.status == TituloPagar.Status.PAGO:
        messages.error(request, "Conta paga não pode ser editada. Estorne o pagamento primeiro.")
        return redirect("financeiro:titulo_detalhe", pk=pk)

    if request.method == "POST":
        form = TituloPagarForm(request.POST, request.FILES, instance=titulo, titulo_integrado=titulo)
        if form.is_valid():
            atualizar_titulo(titulo, usuario=request.user, dados=form.cleaned_data)
            messages.success(request, "Conta a Pagar atualizada.")
            return redirect("financeiro:titulo_detalhe", pk=titulo.pk)
    else:
        form = TituloPagarForm(instance=titulo, titulo_integrado=titulo)
    return render(request, "financeiro/titulo_form.html", {"form": form, "modo": "editar", "titulo": titulo})


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_enviar_aprovacao(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    try:
        enviar_para_aprovacao(titulo, usuario=request.user)
        notificar_aprovadores(titulo)
        messages.success(request, "Conta enviada para aprovação.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:titulo_detalhe", pk=pk)


@financeiro_acao_required("APROVAR")
@require_POST
def titulo_decidir(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    decisao = request.POST.get("decisao")
    observacao = (request.POST.get("observacao") or "").strip()
    if decisao not in {AprovacaoTituloFinanceiro.Decisao.APROVADO, AprovacaoTituloFinanceiro.Decisao.REJEITADO}:
        messages.error(request, "Decisão inválida.")
        return redirect("financeiro:titulo_detalhe", pk=pk)
    try:
        decidir_titulo(titulo, usuario=request.user, decisao=decisao, observacao=observacao)
        messages.success(request, "Decisão registrada.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:titulo_detalhe", pk=pk)


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_cancelar(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    try:
        cancelar_titulo(titulo, usuario=request.user, motivo=(request.POST.get("motivo") or "").strip())
        messages.success(request, "Conta cancelada.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("financeiro:titulo_detalhe", pk=pk)
