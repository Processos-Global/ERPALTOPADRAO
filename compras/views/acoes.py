from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from usuarios.models import AcaoCompra

from compras.forms import (
    AdjudicacaoForm,
    AnaliseTecnicaLoteForm,
    AprovacaoForm,
    CompatibilizacaoForm,
    DocumentoContratacaoForm,
    CotacaoFornecedorForm,
    CotacaoItemForm,
    DecisaoComercialLoteForm,
    NecessidadeCompraForm,
    NegociacaoForm,
    PropostaCompletaForm,
    SolicitacaoCotacaoEnvioForm,
)
from compras.models import (
    AdjudicacaoCompra,
    AprovacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    CompatibilizacaoItem,
    PedidoCompra,
    PedidoCompraAnexo,
    ProcessoCompra,
    SolicitacaoCotacaoFornecedor,
)
from compras.services.adjudicacoes import adjudicar, cancelar_adjudicacao
from compras.services.compatibilizacao import registrar_compatibilizacao
from compras.services.contratacao import anexar_documento_fornecedor
from compras.services.cotacoes import excluir_cotacao, incluir_cotacao, incluir_item_cotacao
from compras.services.etapas import (
    concluir_compatibilizacao,
    concluir_negociacao,
    decidir_aprovacao,
    devolver_cotacao_para_negociacao,
    enviar_cotacao_para_aprovacao,
    enviar_cotacao_para_compatibilizacao,
    enviar_cotacao_para_negociacao,
    retornar_processo_etapa_anterior,
)
from compras.services.negociacao import registrar_negociacao
from compras.services.comercial import processo_exige_compatibilizacao
from compras.services.pedidos import (
    atualizar_previsao_entrega, atualizar_status_pedido, cancelar_pedido,
    gerar_pedidos, registrar_recebimento,
)
from compras.services.permissoes import compras_acao_required, possui_acao_compras
from compras.services.processos import incluir_necessidade
from compras.services.solicitacoes_cotacao import criar_e_marcar_solicitacao_enviada, marcar_solicitacao_enviada


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


@compras_acao_required(AcaoCompra.SOLICITAR)
def acao_incluir_necessidade(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = NecessidadeCompraForm(request.POST, processo=processo)
        if form.is_valid():
            try:
                incluir_necessidade(
                    processo=processo,
                    material=form.cleaned_data["material"],
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


@compras_acao_required(AcaoCompra.COTAR)
def acao_enviar_solicitacao_fornecedor(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = SolicitacaoCotacaoEnvioForm(request.POST, processo=processo)
        if form.is_valid():
            try:
                solicitacao = criar_e_marcar_solicitacao_enviada(
                    processo=processo,
                    fornecedor=form.cleaned_data["fornecedor"],
                    usuario=request.user,
                    meio_envio=form.cleaned_data.get("meio_envio", ""),
                    observacao=form.cleaned_data.get("observacao_envio", ""),
                )
                messages.success(
                    request,
                    f"Envio para {solicitacao.fornecedor.nome} registrado. A proposta desse fornecedor já pode ser preenchida.",
                )
            except ValidationError as exc:
                _erro(request, exc)
        else:
            for erros in form.errors.values():
                for erro in erros:
                    messages.error(request, erro)
    resposta = _voltar(processo)
    resposta["Location"] += "#cotacao"
    return resposta


@compras_acao_required(AcaoCompra.COTAR)
def acao_marcar_solicitacao_enviada(request, pk, solicitacao_id):
    processo = _processo(pk)
    solicitacao = get_object_or_404(
        SolicitacaoCotacaoFornecedor.objects.select_related("fornecedor", "processo"),
        pk=solicitacao_id,
        processo=processo,
    )

    if request.method == "POST":
        try:
            marcar_solicitacao_enviada(
                solicitacao=solicitacao,
                usuario=request.user,
                meio_envio=request.POST.get("meio_envio", ""),
                observacao=request.POST.get("observacao_envio", ""),
            )
            messages.success(
                request,
                f"Envio para {solicitacao.fornecedor.nome} registrado. Agora estamos aguardando a proposta.",
            )
        except ValidationError as exc:
            _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] = resposta["Location"] + "#cotacao"
    return resposta


@compras_acao_required(AcaoCompra.COTAR)
def acao_incluir_cotacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = CotacaoFornecedorForm(request.POST, request.FILES, processo=processo)
        if form.is_valid():
            dados = dict(form.cleaned_data)
            fornecedor = dados.pop("fornecedor")
            try:
                incluir_cotacao(processo=processo, fornecedor=fornecedor, usuario=request.user, **dados)
                if processo.status in [
                    processo.Status.RASCUNHO,
                    processo.Status.PEDIDO_ENVIADO,
                    processo.Status.SOLICITACAO_COTACAO,
                    processo.Status.AGUARDANDO_COTACAO,
                ]:
                    processo.status = processo.Status.EM_COTACAO
                    processo.save(update_fields=["status", "atualizado_em"])
                messages.success(request, "Fornecedor incluído na cotação.")
            except ValidationError as exc:
                _erro(request, exc)
        else:
            messages.error(request, "Revise os dados da cotação.")
    return _voltar(processo)


@compras_acao_required(AcaoCompra.COTAR)
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




@compras_acao_required(AcaoCompra.COTAR)
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
        if cotacao.enviada_compatibilizacao_em or cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em:
            messages.error(request, "Esta proposta já avançou no fluxo e ficou congelada. Retorne a etapa antes de corrigir a proposta.")
            return redirect(f"{_voltar(processo).url}#cotacao")

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

            if processo.status in [
                processo.Status.RASCUNHO,
                processo.Status.PEDIDO_ENVIADO,
                processo.Status.SOLICITACAO_COTACAO,
                processo.Status.AGUARDANDO_COTACAO,
            ]:
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


@compras_acao_required(AcaoCompra.COTAR)
def acao_excluir_cotacao(request, pk, cotacao_id):
    processo = _processo(pk)

    if request.method != "POST":
        return _voltar(processo)

    cotacao = get_object_or_404(
        CotacaoFornecedor.objects.select_related("processo", "fornecedor"),
        pk=cotacao_id,
        processo=processo,
    )

    if cotacao.enviada_compatibilizacao_em or cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em:
        messages.error(request, "A proposta já avançou no fluxo e não pode ser excluída.")
        resposta = _voltar(processo)
        resposta["Location"] = resposta["Location"] + "#cotacao"
        return resposta

    try:
        fornecedor_nome = excluir_cotacao(cotacao=cotacao, usuario=request.user)
        messages.success(request, f"Proposta de {fornecedor_nome} excluída.")
    except ValidationError as exc:
        _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] = resposta["Location"] + "#cotacao"
    return resposta


@compras_acao_required(AcaoCompra.COTAR)
def acao_enviar_cotacao_compatibilizacao(request, pk, cotacao_id):
    processo = _processo(pk)
    cotacao = get_object_or_404(
        CotacaoFornecedor.objects.select_related("fornecedor"),
        pk=cotacao_id,
        processo=processo,
    )
    if request.method == "POST":
        try:
            enviar_cotacao_para_compatibilizacao(cotacao, request.user)
            destino = "compatibilização" if processo_exige_compatibilizacao(processo) else "negociação"
            messages.success(request, f"Proposta de {cotacao.fornecedor.nome} enviada para {destino}.")
        except ValidationError as exc:
            _erro(request, exc)
    resposta = _voltar(processo)
    resposta["Location"] += "#comparacao"
    return resposta


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
def acao_analise_tecnica_lote(request, pk):
    """Salva a compatibilização de um único fornecedor por vez."""
    processo = _processo(pk)
    if request.method != "POST":
        return _voltar(processo)

    cotacao_id = (request.POST.get("cotacao_id") or "").strip()
    if not cotacao_id:
        messages.error(request, "Informe o fornecedor que está sendo compatibilizado.")
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    cotacao = get_object_or_404(
        CotacaoFornecedor.objects.select_related("fornecedor"),
        pk=cotacao_id,
        processo=processo,
        enviada_compatibilizacao_em__isnull=False,
    )
    if cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em:
        messages.error(request, "Esta proposta já avançou da compatibilização.")
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    form = AnaliseTecnicaLoteForm(
        request.POST,
        processo=processo,
        cotacao=cotacao,
    )
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        resposta = _voltar(processo)
        resposta["Location"] += f"#compat-fornecedor-{cotacao.pk}"
        return resposta

    salvas = 0
    try:
        with transaction.atomic():
            for dados in form.decisoes():
                item = dados.pop("item")
                atual = item.compatibilizacoes.first()
                decisao_do_ciclo_atual = (
                    atual
                    and processo.data_cotacao_concluida
                    and atual.data >= processo.data_cotacao_concluida
                    and atual.data >= item.atualizado_em
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

            # Avança somente esta proposta. O service valida se todos os itens
            # deste fornecedor possuem resultado técnico aprovado/ressalva.
            cotacao.refresh_from_db()
            try:
                enviar_cotacao_para_negociacao(cotacao, request.user)
                avancou = True
            except ValidationError:
                avancou = False

        if avancou:
            messages.success(
                request,
                (
                    f"Compatibilização de {cotacao.fornecedor.nome} salva e "
                    "fornecedor liberado individualmente para negociação."
                ),
            )
        else:
            messages.success(
                request,
                (
                    f"Compatibilização de {cotacao.fornecedor.nome} salva: "
                    f"{salvas} decisão(ões) registrada(s). "
                    "Complete/aprove os itens deste fornecedor para avançá-lo."
                ),
            )
    except ValidationError as exc:
        _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] += f"#compat-fornecedor-{cotacao.pk}"
    return resposta


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
def acao_aprovar_toda_compatibilizacao(request, pk):
    """Aprova tecnicamente, de uma vez, todos os itens que aguardam compatibilização."""
    processo = _processo(pk)
    if request.method != "POST":
        return _voltar(processo)

    if not processo_exige_compatibilizacao(processo):
        messages.error(request, "Este suprimento não passa por compatibilização técnica.")
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    cotacoes = list(
        CotacaoFornecedor.objects
        .filter(
            processo=processo,
            enviada_compatibilizacao_em__isnull=False,
            enviada_negociacao_em__isnull=True,
            enviada_aprovacao_em__isnull=True,
        )
        .select_related("fornecedor")
        .prefetch_related("itens__compatibilizacoes")
    )
    if not cotacoes:
        messages.info(request, "Não há propostas aguardando compatibilização.")
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    itens_aprovados = 0
    fornecedores_liberados = 0
    try:
        with transaction.atomic():
            for cotacao in cotacoes:
                for item in cotacao.itens.all():
                    atual = item.compatibilizacoes.order_by("-data", "-id").first()
                    decisao_valida = (
                        atual
                        and atual.resultado == CompatibilizacaoItem.Resultado.APROVADO
                        and (not processo.data_cotacao_concluida or atual.data >= processo.data_cotacao_concluida)
                        and (not item.atualizado_em or atual.data >= item.atualizado_em)
                    )
                    if decisao_valida:
                        continue
                    registrar_compatibilizacao(
                        item_cotado=item,
                        resultado=CompatibilizacaoItem.Resultado.APROVADO,
                        usuario=request.user,
                        observacao="Aprovação técnica em lote.",
                        ressalva_motivo="",
                    )
                    itens_aprovados += 1

                cotacao.refresh_from_db()
                enviar_cotacao_para_negociacao(cotacao, request.user)
                fornecedores_liberados += 1

        messages.success(
            request,
            f"Compatibilização aprovada em lote: {itens_aprovados} item(ns) e {fornecedores_liberados} fornecedor(es) liberado(s) para negociação.",
        )
    except ValidationError as exc:
        _erro(request, exc)

    resposta = _voltar(processo)
    resposta["Location"] += "#comparacao"
    return resposta


@compras_acao_required(AcaoCompra.NEGOCIAR)
def acao_decisao_comercial_lote(request, pk):
    """Salva as condições negociadas e, quando solicitado, envia as alternativas ao gestor."""
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
                elif not any(value not in (None, "") for value in negociacao_nova.values()):
                    continue

                registrar_negociacao(item_cotado=item, usuario=request.user, **negociacao_nova)

        messages.success(request, "Negociações salvas. Envie cada fornecedor individualmente para aprovação quando estiver concluído.")
    except ValidationError as exc:
        _erro(request, exc)
        resposta = _voltar(processo)
        resposta["Location"] += "#comparacao"
        return resposta

    resposta = _voltar(processo)
    resposta["Location"] += "#comparacao"
    return resposta


@compras_acao_required(AcaoCompra.NEGOCIAR)
def acao_enviar_cotacao_aprovacao(request, pk, cotacao_id):
    processo = _processo(pk)
    cotacao = get_object_or_404(CotacaoFornecedor.objects.select_related("fornecedor"), pk=cotacao_id, processo=processo)
    if request.method == "POST":
        try:
            enviar_cotacao_para_aprovacao(cotacao, request.user)
            messages.success(request, f"Proposta de {cotacao.fornecedor.nome} enviada individualmente para aprovação.")
        except ValidationError as exc:
            _erro(request, exc)
    resposta = _voltar(processo); resposta["Location"] += "#comparacao"; return resposta


@compras_acao_required(AcaoCompra.APROVAR)
def acao_devolver_cotacao_negociacao(request, pk, cotacao_id):
    processo = _processo(pk)
    cotacao = get_object_or_404(CotacaoFornecedor.objects.select_related("fornecedor"), pk=cotacao_id, processo=processo)
    if request.method == "POST":
        try:
            devolver_cotacao_para_negociacao(cotacao, request.user)
            messages.warning(request, f"Proposta de {cotacao.fornecedor.nome} devolvida para negociação.")
        except ValidationError as exc:
            _erro(request, exc)
    resposta = _voltar(processo); resposta["Location"] += "#aprovacao"; return resposta


@login_required
def acao_retornar_etapa(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        gestor = possui_acao_compras(request.user, AcaoCompra.APROVAR)
        pode_operar = gestor or any(
            possui_acao_compras(request.user, acao)
            for acao in (AcaoCompra.COTAR, AcaoCompra.COMPATIBILIZAR, AcaoCompra.NEGOCIAR)
        )
        if not pode_operar:
            raise PermissionDenied("Você não possui permissão para retornar etapas deste processo.")
        try:
            retornar_processo_etapa_anterior(processo, request.user, gestor=gestor)
            messages.warning(request, "Processo retornado para a etapa anterior sem apagar os dados já preenchidos.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(ProcessoCompra.objects.get(pk=processo.pk))


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
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


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
def acao_concluir_compatibilizacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            concluir_compatibilizacao(processo, request.user)
            messages.success(request, "Negociação liberada para as ofertas tecnicamente aprovadas. O mapa continua aberto.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_acao_required(AcaoCompra.NEGOCIAR)
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


@compras_acao_required(AcaoCompra.NEGOCIAR)
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


@compras_acao_required(AcaoCompra.NEGOCIAR)
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


@compras_acao_required(AcaoCompra.NEGOCIAR)
def acao_concluir_negociacao(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            concluir_negociacao(processo, request.user)
            messages.success(request, "Mapa comercial fechado e enviado para aprovação.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_acao_required(AcaoCompra.APROVAR)
def acao_aprovar(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        form = AprovacaoForm(request.POST, processo=processo)
        if form.is_valid():
            try:
                decisao = form.cleaned_data["decisao"]
                selecoes = list(form.selecoes_aprovadas()) if decisao == AprovacaoCompra.Decisao.APROVADO else []
                decidir_aprovacao(
                    processo,
                    request.user,
                    decisao,
                    form.cleaned_data["observacao"],
                    selecoes=selecoes,
                )

                if decisao == AprovacaoCompra.Decisao.AJUSTE_SOLICITADO:
                    messages.warning(
                        request,
                        "Aprovado com ressalva. O processo retornou para Negociação para ajuste das condições comerciais.",
                    )
                    processo_atualizado = ProcessoCompra.objects.get(pk=processo.pk)
                    resposta = _voltar(processo_atualizado)
                    resposta["Location"] += "#comparacao"
                    return resposta

                if decisao == AprovacaoCompra.Decisao.REPROVADO:
                    messages.error(
                        request,
                        "Compra reprovada pelo gestor. O processo foi encerrado e nenhum pedido foi gerado.",
                    )
                    processo_atualizado = ProcessoCompra.objects.get(pk=processo.pk)
                    resposta = _voltar(processo_atualizado)
                    resposta["Location"] += "#aprovacao"
                    return resposta

                messages.success(
                    request,
                    "Proposta(s) aprovada(s). Os pedidos foram emitidos automaticamente e aguardam confirmação dos fornecedores.",
                )
            except ValidationError as exc:
                _erro(request, exc)
        else:
            for erros in form.errors.values():
                for erro in erros:
                    messages.error(request, erro)
    processo_atualizado = ProcessoCompra.objects.get(pk=processo.pk)
    resposta = _voltar(processo_atualizado)
    resposta["Location"] += "#pedido" if processo_atualizado.etapa_atual in {ProcessoCompra.Etapa.CONTRATACAO, ProcessoCompra.Etapa.CONTRATADO} else "#aprovacao"
    return resposta


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
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


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
def acao_gerar_pedidos(request, pk):
    processo = _processo(pk)
    if request.method == "POST":
        try:
            pedidos = gerar_pedidos(processo, request.user)
            messages.success(request, f"{len(pedidos)} pedido(s) emitido(s). A contratação será concluída após a confirmação dos fornecedores.")
        except ValidationError as exc:
            _erro(request, exc)
    return _voltar(processo)


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
def acao_anexar_arquivo_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra.objects.select_related("processo"), pk=pedido_id)
    if request.method == "POST":
        arquivos = request.FILES.getlist("arquivos")
        descricao = (request.POST.get("descricao") or "").strip()
        if not arquivos:
            messages.error(request, "Selecione ao menos um arquivo para anexar.")
        else:
            for arquivo in arquivos:
                PedidoCompraAnexo.objects.create(
                    pedido=pedido,
                    arquivo=arquivo,
                    descricao=descricao,
                    enviado_por=request.user,
                )
            messages.success(request, f"{len(arquivos)} arquivo(s) anexado(s) ao pedido {pedido.numero}.")
    origem = request.POST.get("origem")
    if origem == "processo":
        resposta = _voltar(pedido.processo)
        resposta["Location"] += "#pedido"
        return resposta
    return redirect("compras:lista_pedidos")


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
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


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
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


@compras_acao_required(AcaoCompra.RECEBER_PEDIDOS)
def acao_receber_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        quantidades = {}
        valores_itens = {}
        for item in pedido.itens.all():
            quantidade = request.POST.get(f"item_{item.pk}")
            valor_item = request.POST.get(f"valor_item_{item.pk}")
            if quantidade not in (None, ""):
                quantidades[item.pk] = quantidade
            if valor_item not in (None, ""):
                valores_itens[item.pk] = valor_item
        try:
            recebimento = registrar_recebimento(
                pedido=pedido,
                quantidades=quantidades,
                valores_itens=valores_itens,
                usuario=request.user,
                numero_nota_fiscal=request.POST.get("numero_nota_fiscal", ""),
                valor_total_nota=request.POST.get("valor_total_nota", ""),
                arquivo_nota_fiscal=request.FILES.get("arquivo_nota_fiscal"),
                observacao=request.POST.get("observacao", ""),
            )
            messages.success(
                request,
                f"Recebimento registrado com a NF {recebimento.numero_nota_fiscal}.",
            )
        except ValidationError as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")


@compras_acao_required(AcaoCompra.CANCELAR_PEDIDOS)
def acao_cancelar_pedido(request, pedido_id):
    pedido = get_object_or_404(PedidoCompra, pk=pedido_id)
    if request.method == "POST":
        try:
            cancelar_pedido(pedido=pedido, usuario=request.user, motivo=request.POST.get("motivo", ""))
            messages.success(request, "Pedido cancelado.")
        except ValidationError as exc:
            _erro(request, exc)
    return redirect("compras:lista_pedidos")
