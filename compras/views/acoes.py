from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from usuarios.models import NivelPermissao

from compras.forms import (
    AdjudicacaoForm,
    AnaliseTecnicaLoteForm,
    AprovacaoForm,
    CompatibilizacaoForm,
    DocumentoContratacaoForm,
    CotacaoFornecedorForm,
    CotacaoItemForm,
    DecisaoComercialLoteForm,
    FornecedorCompraForm,
    NecessidadeCompraForm,
    NegociacaoForm,
    PropostaCompletaForm,
)
from compras.models import (
    AdjudicacaoCompra,
    AprovacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    PedidoCompra,
    ProcessoCompra,
)
from compras.services.adjudicacoes import adjudicar, cancelar_adjudicacao
from compras.services.compatibilizacao import registrar_compatibilizacao
from compras.services.contratacao import anexar_documento_fornecedor
from compras.services.cotacoes import criar_fornecedor, excluir_cotacao, incluir_cotacao, incluir_item_cotacao
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
def acao_salvar_proposta_completa(request, pk):
    """Salva cabeçalho e todos os itens preenchidos de uma proposta em um único POST."""
    processo = _processo(pk)
    if request.method != "POST":
        return _voltar(processo)

    cotacao = None
    cotacao_id = request.POST.get("cotacao_id")
    if cotacao_id:
        cotacao = get_object_or_404(
            CotacaoFornecedor.objects.select_related("fornecedor"),
            pk=cotacao_id,
            processo=processo,
        )

    form = PropostaCompletaForm(
        request.POST,
        request.FILES,
        processo=processo,
        cotacao=cotacao,
    )
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect(f"{_voltar(processo).url}#cotacao")

    try:
        with transaction.atomic():
            cabecalho = {
                "data_proposta": form.cleaned_data.get("data_proposta"),
                "prazo_entrega_dias": form.cleaned_data.get("prazo_entrega_dias"),
                "condicao_pagamento": form.cleaned_data.get("condicao_pagamento", ""),
                "frete": form.cleaned_data.get("frete"),
                "validade": form.cleaned_data.get("validade"),
                "observacoes": form.cleaned_data.get("observacoes", ""),
            }
            if form.cleaned_data.get("documento"):
                cabecalho["documento"] = form.cleaned_data["documento"]

            cotacao_salva = incluir_cotacao(
                processo=processo,
                fornecedor=form.cleaned_data["fornecedor"],
                usuario=request.user,
                **cabecalho,
            )

            quantidade_itens = 0
            for dados in form.itens_para_salvar():
                necessidade = dados.pop("necessidade")
                quantidade = dados.pop("quantidade")
                valor_unitario = dados.pop("valor_unitario")
                incluir_item_cotacao(
                    cotacao=cotacao_salva,
                    necessidade=necessidade,
                    quantidade=quantidade,
                    valor_unitario=valor_unitario,
                    usuario=request.user,
                    **dados,
                )
                quantidade_itens += 1

            if processo.status in [processo.Status.RASCUNHO, processo.Status.AGUARDANDO_COTACAO]:
                processo.status = processo.Status.EM_COTACAO
                processo.save(update_fields=["status", "atualizado_em"])

        messages.success(
            request,
            f"Proposta de {cotacao_salva.fornecedor.nome} salva com {quantidade_itens} item(ns).",
        )
    except ValidationError as exc:
        _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] = resposta["Location"] + "#cotacao"
    return resposta


@compras_permission_required(NivelPermissao.EDICAO)
def acao_excluir_cotacao(request, pk, cotacao_id):
    processo = _processo(pk)

    if request.method != "POST":
        return _voltar(processo)

    cotacao = get_object_or_404(
        CotacaoFornecedor.objects.select_related("processo", "fornecedor"),
        pk=cotacao_id,
        processo=processo,
    )

    try:
        fornecedor_nome = excluir_cotacao(cotacao=cotacao, usuario=request.user)
        messages.success(request, f"Proposta de {fornecedor_nome} excluída.")
    except ValidationError as exc:
        _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] = resposta["Location"] + "#cotacao"
    return resposta


@compras_permission_required(NivelPermissao.EDICAO)
def acao_analise_tecnica_lote(request, pk):
    """Salva a análise técnica em lote e conclui a etapa conforme o resultado."""
    processo = _processo(pk)
    if request.method != "POST":
        return _voltar(processo)

    avancar = request.POST.get("acao") == "salvar_avancar"
    form = AnaliseTecnicaLoteForm(request.POST, processo=processo)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    salvas = 0
    try:
        # As decisões válidas são persistidas primeiro. Se ainda houver pendências
        # técnicas, elas permanecem salvas e o processo continua na análise técnica.
        with transaction.atomic():
            for dados in form.decisoes():
                item = dados.pop("item")
                atual = item.compatibilizacoes.first()
                decisao_do_ciclo_atual = (
                    atual
                    and processo.data_cotacao_concluida
                    and atual.data >= processo.data_cotacao_concluida
                )
                if decisao_do_ciclo_atual and (
                    atual.resultado == dados["resultado"]
                    and (atual.observacao or "") == (dados.get("observacao") or "")
                    and (atual.ressalva_motivo or "") == (dados.get("ressalva_motivo") or "")
                ):
                    continue
                registrar_compatibilizacao(
                    item_cotado=item,
                    usuario=request.user,
                    **dados,
                )
                salvas += 1
    except ValidationError as exc:
        _erro(request, exc)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    if not avancar:
        messages.success(
            request,
            f"Análise técnica atualizada: {salvas} decisão(ões) registrada(s).",
        )
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    try:
        processo_atualizado = concluir_compatibilizacao(processo, request.user)

        if processo_atualizado.etapa_atual == processo_atualizado.Etapa.COTACAO:
            prefixo = f"{salvas} decisão(ões) salva(s). " if salvas else ""
            messages.warning(
                request,
                prefixo
                + "Análise técnica concluída, mas um ou mais itens ficaram sem proposta aprovada. "
                "O processo retornou para Cotação. Inclua ou corrija as propostas desses itens e conclua a cotação novamente.",
            )
            resposta = _voltar(processo_atualizado)
            resposta["Location"] += "#cotacao"
            return resposta

        if salvas:
            messages.success(
                request,
                f"{salvas} decisão(ões) salva(s). Análise técnica concluída e processo enviado para negociação.",
            )
        else:
            messages.success(
                request,
                "Análise técnica concluída e processo enviado para negociação.",
            )

        resposta = _voltar(processo_atualizado)
        resposta["Location"] += "#comparacao"
        return resposta

    except ValidationError as exc:
        # As decisões registradas acima permanecem salvas. O erro aqui representa,
        # por exemplo, alguma oferta que ainda não recebeu decisão técnica.
        if salvas:
            messages.success(request, f"{salvas} decisão(ões) técnica(s) foram salvas.")
        _erro(request, exc)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta


@compras_permission_required(NivelPermissao.EDICAO)
def acao_decisao_comercial_lote(request, pk):
    """Salva negociação/quantidades e, quando solicitado, avança para aprovação."""
    processo = _processo(pk)
    if request.method != "POST":
        return _voltar(processo)

    avancar = request.POST.get("acao") == "salvar_avancar"
    form = DecisaoComercialLoteForm(request.POST, processo=processo)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    try:
        with transaction.atomic():
            linhas = list(form.dados_linhas())

            # 1) Condições negociadas: só cria histórico quando algo realmente mudou.
            for dados in linhas:
                item = dados["item"]
                try:
                    atual = item.negociacao
                except Exception:
                    atual = None

                negociacao_nova = {
                    "valor_unitario_negociado": dados["valor_unitario_negociado"],
                    "frete_negociado": dados["frete_negociado"],
                    "prazo_entrega_dias_negociado": dados["prazo_entrega_dias_negociado"],
                    "condicao_pagamento_negociada": dados["condicao_pagamento_negociada"],
                    "observacoes": dados["observacoes"],
                }
                if atual:
                    igual = (
                        atual.valor_unitario_negociado == negociacao_nova["valor_unitario_negociado"]
                        and atual.frete_negociado == negociacao_nova["frete_negociado"]
                        and atual.prazo_entrega_dias_negociado == negociacao_nova["prazo_entrega_dias_negociado"]
                        and (atual.condicao_pagamento_negociada or "") == (negociacao_nova["condicao_pagamento_negociada"] or "")
                        and (atual.observacoes or "") == (negociacao_nova["observacoes"] or "")
                    )
                    if igual:
                        continue
                elif not any(
                    value not in (None, "")
                    for value in negociacao_nova.values()
                ):
                    continue

                registrar_negociacao(
                    item_cotado=item,
                    usuario=request.user,
                    **negociacao_nova,
                )

            # 2) Quantidades: reconcilia por necessidade apenas quando a matriz mudou.
            por_necessidade = {}
            for dados in linhas:
                item = dados["item"]
                por_necessidade.setdefault(item.necessidade_id, []).append(dados)

            for necessidade_id, linhas_necessidade in por_necessidade.items():
                atuais = list(
                    processo.adjudicacoes.filter(
                        cancelada=False, necessidade_id=necessidade_id
                    ).select_related("item_cotado")
                )
                atual_por_item = {}
                for adj in atuais:
                    atual_por_item[adj.item_cotado_id] = (
                        atual_por_item.get(adj.item_cotado_id, 0) + adj.quantidade
                    )
                desejado_por_item = {
                    d["item"].pk: d["quantidade"] for d in linhas_necessidade
                    if d["quantidade"] > 0
                }
                normalizado_atual = {k: v for k, v in atual_por_item.items() if v > 0}
                if normalizado_atual == desejado_por_item:
                    continue

                for adj in atuais:
                    cancelar_adjudicacao(
                        processo=processo,
                        adjudicacao=adj,
                        usuario=request.user,
                        motivo="Atualização da seleção pela matriz comercial.",
                    )
                for dados in linhas_necessidade:
                    if dados["quantidade"] <= 0:
                        continue
                    item_atualizado = CotacaoFornecedorItem.objects.select_related(
                        "cotacao", "necessidade", "negociacao"
                    ).get(pk=dados["item"].pk)
                    adjudicar(
                        processo=processo,
                        item_cotado=item_atualizado,
                        quantidade=dados["quantidade"],
                        usuario=request.user,
                    )

            # A ação principal da tela salva a matriz e conclui a negociação
            # dentro da mesma transação. Se a validação da conclusão falhar,
            # nenhuma alteração desta submissão é persistida pela metade.
            if avancar:
                concluir_negociacao(processo, request.user)

        if avancar:
            messages.success(request, "Escolhas salvas e processo enviado para aprovação.")
        else:
            messages.success(request, "Comparação comercial e quantidades selecionadas foram salvas.")
    except ValidationError as exc:
        _erro(request, exc)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    resposta = _voltar(processo)
    resposta["Location"] += "#aprovacao" if avancar else "#comparacao"
    return resposta


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
                decisao = form.cleaned_data["decisao"]
                decidir_aprovacao(
                    processo,
                    request.user,
                    decisao,
                    form.cleaned_data["observacao"],
                )

                if decisao == AprovacaoCompra.Decisao.AJUSTE_SOLICITADO:
                    messages.warning(
                        request,
                        "Ajuste solicitado. O processo retornou para Cotação. "
                        "O comprador deverá revisar as propostas e percorrer novamente "
                        "Cotação, Compatibilização, Comparação Comercial e Aprovação.",
                    )
                    processo_atualizado = ProcessoCompra.objects.get(pk=processo.pk)
                    resposta = _voltar(processo_atualizado)
                    resposta["Location"] += "#cotacao"
                    return resposta

                if decisao == AprovacaoCompra.Decisao.REPROVADO:
                    messages.error(
                        request,
                        "Compra reprovada pelo gestor. O processo foi encerrado definitivamente e nenhum pedido será gerado.",
                    )
                    processo_atualizado = ProcessoCompra.objects.get(pk=processo.pk)
                    resposta = _voltar(processo_atualizado)
                    resposta["Location"] += "#aprovacao"
                    return resposta

                messages.success(
                    request,
                    "Compra aprovada. Os pedidos foram gerados e o processo seguirá para contratação/entrega.",
                )
            except ValidationError as exc:
                _erro(request, exc)
    return _voltar(processo)


@compras_permission_required(NivelPermissao.EDICAO)
def acao_anexar_documento(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = DocumentoContratacaoForm(request.POST, request.FILES, processo=processo)
        if form.is_valid():
            try:
                anexar_documento_fornecedor(
                    processo=processo,
                    fornecedor=form.cleaned_data["fornecedor"],
                    usuario=request.user,
                    documento=form.cleaned_data["documento"],
                )
                messages.success(request, "Documento anexado com sucesso.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Selecione o fornecedor e o documento que deseja anexar.")
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
