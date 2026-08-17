from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect

from usuarios.models import NivelPermissao

from compras.forms import (
    AdjudicacaoForm,
    AprovacaoForm,
    CompatibilizacaoForm,
    ContratacaoForm,
    CotacaoFornecedorForm,
    CotacaoItemForm,
    FornecedorCompraForm,
    NecessidadeCompraForm,
    NegociacaoForm,
)
from compras.models import AdjudicacaoCompra, PedidoCompra, ProcessoCompra
from compras.services.adjudicacoes import adjudicar, cancelar_adjudicacao
from compras.services.compatibilizacao import registrar_compatibilizacao
from compras.services.contratacao import formalizar_fornecedor
from compras.services.cotacoes import criar_fornecedor, incluir_cotacao, incluir_item_cotacao
from compras.services.etapas import (
    concluir_compatibilizacao,
    concluir_cotacao,
    concluir_negociacao,
    decidir_aprovacao,
)
from compras.services.negociacao import registrar_negociacao
from compras.services.pedidos import (
    atualizar_previsao_entrega, atualizar_status_pedido, cancelar_pedido,
    gerar_pedidos, registrar_recebimento,
)
from compras.services.permissoes import compras_permission_required
from compras.services.processos import incluir_necessidade


def _processo(pk):
    return get_object_or_404(ProcessoCompra, pk=pk)


def _voltar(processo):
    return redirect("compras:detalhe_processo", pk=processo.pk)


def _erro(request, exc):
    if hasattr(exc, "messages"):
        for texto in exc.messages:
            messages.error(request, texto)
    else:
        messages.error(request, str(exc))


@compras_permission_required(NivelPermissao.EDICAO)
def acao_incluir_necessidade(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = NecessidadeCompraForm(request.POST, processo=processo)
        if form.is_valid():
            try:
                incluir_necessidade(
                    processo=processo,
                    descricao=form.cleaned_data["descricao"],
                    especificacao=form.cleaned_data["especificacao"],
                    unidade=form.cleaned_data["unidade"],
                    quantidade=form.cleaned_data["quantidade"],
                    observacao=form.cleaned_data["observacao"],
                    usuario=request.user,
                )
                messages.success(request, "Item incluído na compra.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados da necessidade.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_criar_fornecedor(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = FornecedorCompraForm(request.POST)
        if form.is_valid():
            try:
                fornecedor = criar_fornecedor(**form.cleaned_data)
                messages.success(request, f"Fornecedor {fornecedor.nome} cadastrado.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados do fornecedor.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_incluir_cotacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = CotacaoFornecedorForm(request.POST, request.FILES, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            fornecedor = dados.pop("fornecedor")
            try:
                incluir_cotacao(processo=processo, fornecedor=fornecedor, usuario=request.user, **dados)
                if processo.status in [processo.Status.RASCUNHO, processo.Status.AGUARDANDO_COTACAO]:
                    processo.status = processo.Status.EM_COTACAO
                    processo.save(update_fields=["status", "atualizado_em"])
                messages.success(request, "Fornecedor incluído na cotação.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados da cotação.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_incluir_item_cotacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = CotacaoItemForm(request.POST, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            cotacao = dados.pop("cotacao")
            necessidade = dados.pop("necessidade")
            quantidade = dados.pop("quantidade")
            valor = dados.pop("valor_unitario_cotado")
            try:
                incluir_item_cotacao(
                    cotacao=cotacao,
                    necessidade=necessidade,
                    quantidade=quantidade,
                    valor_unitario=valor,
                    usuario=request.user,
                    **dados,
                )
                messages.success(request, "Item da proposta salvo.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados do item cotado.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_concluir_cotacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            concluir_cotacao(processo, request.user)
            messages.success(request, "Cotação concluída e enviada para compatibilização.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_compatibilizar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = CompatibilizacaoForm(request.POST, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            item = dados.pop("item_cotado")
            try:
                registrar_compatibilizacao(item_cotado=item, usuario=request.user, **dados)
                messages.success(request, "Decisão técnica registrada.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise a compatibilização.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_concluir_compatibilizacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            concluir_compatibilizacao(processo, request.user)
            messages.success(request, "Compatibilização concluída.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_negociar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = NegociacaoForm(request.POST, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            item = dados.pop("item_cotado")
            registrar_negociacao(item_cotado=item, usuario=request.user, **dados)
            messages.success(request, "Negociação registrada sem alterar a proposta original.")
        else:
            messages.error(request, "Revise os dados da negociação.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_adjudicar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = AdjudicacaoForm(request.POST, processo=processo)
        if form.is_valid():
            try:
                adjudicar(
                    processo=processo,
                    item_cotado=form.cleaned_data["item_cotado"],
                    quantidade=form.cleaned_data["quantidade"],
                    usuario=request.user,
                )
                messages.success(request, "Adjudicação registrada.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise a adjudicação.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_cancelar_adjudicacao(request, pk, adjudicacao_id):
    processo = _processo(pk)
    adjudicacao = get_object_or_404(
        AdjudicacaoCompra,
        pk=adjudicacao_id,
        processo=processo,
    )

    if request.method == "POST":
        try:
            cancelar_adjudicacao(
                processo=processo,
                adjudicacao=adjudicacao,
                usuario=request.user,
                motivo=request.POST.get("motivo"),
            )
            messages.success(
                request,
                "Adjudicação cancelada. O saldo do item foi recalculado.",
            )
        except ValidationError as exc:
            _erro(request, exc)

    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_concluir_negociacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            concluir_negociacao(processo, request.user)
            messages.success(request, "Negociação concluída e enviada para aprovação.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.APROVACAO)
def acao_aprovar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = AprovacaoForm(request.POST)
        if form.is_valid():
            try:
                decidir_aprovacao(
                    processo,
                    request.user,
                    form.cleaned_data["decisao"],
                    form.cleaned_data["observacao"],
                )
                messages.success(request, "Decisão registrada.")
            except ValidationError as exc:
                _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_formalizar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = ContratacaoForm(request.POST, request.FILES, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            fornecedor = dados.pop("fornecedor")
            try:
                formalizar_fornecedor(processo=processo, fornecedor=fornecedor, usuario=request.user, **dados)
                messages.success(request, "Formalização registrada.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados da formalização.")
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_gerar_pedidos(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            pedidos = gerar_pedidos(processo, request.user)
            messages.success(request, f"{len(pedidos)} pedido(s) gerado(s) e contratação concluída.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_atualizar_status_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        try:
            atualizar_status_pedido(
                pedido=pedido, novo_status=request.POST.get("status"),
                usuario=request.user, observacao=request.POST.get("observacao", ""),
            )
            messages.success(request, "Status do pedido atualizado.")
        except ValidationError as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")


@compras_permission_required(NivelPermissao.EDICAO)
def acao_atualizar_previsao_pedido(request, pedido_id):
    from datetime import date
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        try:
            valor = request.POST.get("previsao_entrega")
            previsao = date.fromisoformat(valor) if valor else None
            atualizar_previsao_entrega(
                pedido=pedido, previsao_nova=previsao, usuario=request.user,
                motivo=request.POST.get("motivo", ""),
            )
            messages.success(request, "Previsão de entrega atualizada.")
        except (ValidationError, ValueError) as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")


@compras_permission_required(NivelPermissao.EDICAO)
def acao_receber_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        quantidades = {}
        for item in pedido.itens.all():
            valor = request.POST.get(f"item_{item.pk}")
            if valor not in (None, ""):
                quantidades[item.pk] = valor
        try:
            registrar_recebimento(
                pedido=pedido, quantidades=quantidades, usuario=request.user,
                observacao=request.POST.get("observacao", ""),
            )
            messages.success(request, "Recebimento registrado.")
        except ValidationError as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")


@compras_permission_required(NivelPermissao.EDICAO)
def acao_cancelar_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        try:
            cancelar_pedido(pedido=pedido, usuario=request.user, motivo=request.POST.get("motivo", ""))
            messages.success(request, "Pedido cancelado.")
        except ValidationError as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")
