from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cadastros.models import Fornecedor
from financeiro.forms import TituloPagarForm
from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.aprovacoes import decidir_titulo, enviar_para_aprovacao
from financeiro.services.notificacoes import notificar_aprovadores
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.services.titulos import atualizar_titulo, cancelar_titulo, criar_titulo_manual
from obras.models import Obra


@financeiro_acao_required("VISUALIZAR")
def titulos_lista(request):
    hoje = timezone.localdate()
    qs = TituloPagar.objects.select_related("fornecedor", "obra", "plano_financeiro", "pedido").all()
    busca = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    obra = (request.GET.get("obra") or "").strip()
    fornecedor = (request.GET.get("fornecedor") or "").strip()
    periodo = (request.GET.get("periodo") or "30").strip()
    atalho = (request.GET.get("atalho") or "").strip()

    if busca:
        qs = qs.filter(
            Q(numero__icontains=busca)
            | Q(documento_numero__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(fornecedor__nome__icontains=busca)
            | Q(fornecedor__nome_fantasia__icontains=busca)
        )
    if status:
        qs = qs.filter(status=status)
    if obra:
        qs = qs.filter(obra_id=obra)
    if fornecedor:
        qs = qs.filter(fornecedor_id=fornecedor)

    if atalho == "vencidos":
        qs = qs.filter(vencimento__lt=hoje).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    elif atalho == "aprovacao":
        qs = qs.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO)
    elif atalho in {"7", "30"}:
        dias = int(atalho)
        qs = qs.filter(vencimento__range=(hoje, hoje + timedelta(days=dias))).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO])
    elif periodo.isdigit() and int(periodo) > 0:
        qs = qs.filter(vencimento__lte=hoje + timedelta(days=int(periodo)))

    paginator = Paginator(qs.order_by("vencimento", "numero"), 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    base_abertos = TituloPagar.objects.exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO, TituloPagar.Status.REJEITADO])
    vencidos = list(base_abertos.filter(vencimento__lt=hoje))
    sete = list(base_abertos.filter(vencimento__range=(hoje, hoje + timedelta(days=7))))
    trinta = list(base_abertos.filter(vencimento__range=(hoje, hoje + timedelta(days=30))))
    aprovacao = list(base_abertos.filter(status=TituloPagar.Status.AGUARDANDO_APROVACAO))

    return render(request, "financeiro/titulos_lista.html", {
        "page_obj": page_obj,
        "status_choices": TituloPagar.Status.choices,
        "obras": Obra.objects.all().order_by("id"),
        "fornecedores": Fornecedor.objects.filter(ativo=True).order_by("nome"),
        "filtros": {"q": busca, "status": status, "obra": obra, "fornecedor": fornecedor, "periodo": periodo, "atalho": atalho},
        "kpi_vencidos": sum((x.saldo_aberto for x in vencidos), 0),
        "kpi_7": sum((x.saldo_aberto for x in sete), 0),
        "kpi_30": sum((x.saldo_aberto for x in trinta), 0),
        "kpi_aprovacao": sum((x.saldo_aberto for x in aprovacao), 0),
        "pode_lancar": possui_acao_financeiro(request.user, "LANCAR_TITULOS"),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    })


@financeiro_acao_required("LANCAR_TITULOS")
def titulo_novo(request):
    if request.method == "POST":
        form = TituloPagarForm(request.POST, request.FILES)
        if form.is_valid():
            dados = form.cleaned_data.copy()
            titulo = criar_titulo_manual(usuario=request.user, **dados)
            messages.success(request, f"Título {titulo.numero} criado com sucesso.")
            return redirect("financeiro:titulo_detalhe", pk=titulo.pk)
    else:
        form = TituloPagarForm()
    return render(request, "financeiro/titulo_form.html", {"form": form, "modo": "novo"})


@financeiro_acao_required("VISUALIZAR")
def titulo_detalhe(request, pk):
    titulo = get_object_or_404(
        TituloPagar.objects.select_related(
            "fornecedor", "obra", "plano_financeiro", "pedido", "recebimento", "previsao_origem"
        ).select_related("pagamento").prefetch_related("aprovacoes__usuario", "historico__usuario"),
        pk=pk,
    )
    return render(request, "financeiro/titulo_detalhe.html", {
        "titulo": titulo,
        "pode_editar": possui_acao_financeiro(request.user, "EDITAR_TITULOS"),
        "pode_aprovar": possui_acao_financeiro(request.user, "APROVAR"),
        "pode_pagar": possui_acao_financeiro(request.user, "PAGAR"),
    })


@financeiro_acao_required("EDITAR_TITULOS")
def titulo_editar(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    if request.method == "POST":
        form = TituloPagarForm(request.POST, request.FILES, instance=titulo, titulo_integrado=titulo)
        if form.is_valid():
            dados = {campo: form.cleaned_data[campo] for campo in form.cleaned_data}
            atualizar_titulo(titulo, usuario=request.user, dados=dados)
            messages.success(request, "Título atualizado com sucesso.")
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
        messages.success(request, "Título enviado para aprovação financeira.")
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
        messages.success(request, "Decisão registrada com sucesso.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("financeiro:titulo_detalhe", pk=pk)


@financeiro_acao_required("EDITAR_TITULOS")
@require_POST
def titulo_cancelar(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    try:
        cancelar_titulo(titulo, usuario=request.user, motivo=(request.POST.get("motivo") or "").strip())
        messages.success(request, "Título cancelado.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("financeiro:titulo_detalhe", pk=pk)
