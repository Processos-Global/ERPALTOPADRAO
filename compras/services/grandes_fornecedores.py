from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import (
    AdjudicacaoCompra,
    AprovacaoCompra,
    CompatibilizacaoItem,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    GrandeFornecedorItem,
    GrandeFornecedorOferta,
    GrandeFornecedorParticipante,
    GrandeFornecedorProcesso,
    HistoricoValorGrandeFornecedor,
    NecessidadeCompra,
    NegociacaoItem,
    ParcelaGrandeFornecedor,
    RateioParcelaGrandeFornecedor,
)
from .auditoria import registrar_evento
from .grande_fornecedor_status import STATUS_DERIVADOS_RECEBIMENTO, transicoes_manuais
from .integracao_planejamento import limpar_data_real, sincronizar_data_real
from .pedidos import gerar_pedidos

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")


def _decimal_2(valor, *, nome="Valor", permitir_zero=True):
    if valor is None:
        raise ValidationError(f"{nome} inválido.")
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        raise ValidationError(f"{nome} inválido.")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto).quantize(CENTAVO)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"{nome} inválido.")
    if numero < 0 or (not permitir_zero and numero <= 0):
        if permitir_zero:
            raise ValidationError(f"{nome} não pode ser negativo.")
        raise ValidationError(f"{nome} deve ser maior que zero.")
    return numero


def _validar_fluxo(processo):
    if not processo.fluxo_grande_fornecedor:
        raise ValidationError("Este processo não utiliza o fluxo de Grande Fornecedor.")


def _matriz_editavel(processo):
    return processo.etapa_atual in {
        processo.Etapa.COMPATIBILIZACAO,
        processo.Etapa.NEGOCIACAO,
    } and processo.status not in {
        processo.Status.CANCELADO,
        processo.Status.REPROVADO,
        processo.Status.CONTRATADO,
    }


def obter_ou_criar_fluxo(processo):
    _validar_fluxo(processo)
    fluxo, _ = GrandeFornecedorProcesso.objects.get_or_create(processo=processo)
    return fluxo


def _obter_participante(*, fluxo, fornecedor, usuario=None):
    participante, criada = GrandeFornecedorParticipante.objects.get_or_create(
        fluxo=fluxo,
        fornecedor=fornecedor,
    )
    if criada and usuario is not None:
        registrar_evento(
            fluxo.processo,
            "GF_FORNECEDOR_INCLUIDO",
            usuario,
            f"{fornecedor.nome} vinculado a um item da matriz.",
        )
    return participante


def _salvar_oferta(*, micro_item, participante, valor, usuario):
    novo = _decimal_2(valor, nome="Valor unitário", permitir_zero=False)
    oferta, _ = GrandeFornecedorOferta.objects.select_for_update().get_or_create(
        item=micro_item,
        participante=participante,
    )
    anterior = oferta.valor_atual
    if oferta.valor_inicial is None:
        oferta.valor_inicial = novo
    oferta.valor_atual = novo
    oferta.atualizado_por = usuario
    oferta.save(update_fields=["valor_inicial", "valor_atual", "atualizado_por", "atualizado_em"])
    if anterior != novo:
        HistoricoValorGrandeFornecedor.objects.create(
            oferta=oferta,
            valor_anterior=anterior,
            valor_novo=novo,
            usuario=usuario,
        )
    return oferta


@transaction.atomic
def adicionar_participante(*, processo, fornecedor, usuario):
    """Compatibilidade com chamadas legadas; a nova tela vincula fornecedor por item."""
    fluxo = obter_ou_criar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está fechada para alterações.")
    return _obter_participante(fluxo=fluxo, fornecedor=fornecedor, usuario=usuario)


@transaction.atomic
def adicionar_item(
    *,
    processo,
    material,
    quantidade,
    usuario,
    fornecedor=None,
    valor_unitario=None,
    pavimento="",
    local="",
):
    fluxo = obter_ou_criar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está fechada para inclusão de itens.")
    if material is None or not material.ativo:
        raise ValidationError("Selecione um material ativo do cadastro.")

    quantidade = _decimal_2(quantidade, nome="Quantidade", permitir_zero=False)
    ordem = (fluxo.itens.order_by("-ordem").values_list("ordem", flat=True).first() or 0) + 1

    micro = GrandeFornecedorItem.objects.create(
        fluxo=fluxo,
        material=material,
        pavimento=(pavimento or "").strip(),
        local=(local or "").strip(),
        item=material.descricao_completa,
        unidade=material.unidade.sigla,
        quantidade=quantidade,
        ordem=ordem,
    )
    fornecedor_id = None
    if fornecedor is not None:
        if not fornecedor.ativo:
            raise ValidationError("Selecione um fornecedor ativo.")
        participante = _obter_participante(fluxo=fluxo, fornecedor=fornecedor, usuario=usuario)
        _salvar_oferta(
            micro_item=micro,
            participante=participante,
            valor=valor_unitario,
            usuario=usuario,
        )
        micro.participante_aprovado = participante
        micro.save(update_fields=["participante_aprovado", "atualizado_em"])
        fornecedor_id = fornecedor.pk

    registrar_evento(
        processo,
        "GF_ITEM_INCLUIDO",
        usuario,
        f"Item incluído: {material.descricao_completa}.",
        {"item_id": micro.pk, "material_id": material.pk, "fornecedor_id": fornecedor_id},
    )
    return micro


@transaction.atomic
def atualizar_linha(
    *,
    micro_item,
    material,
    quantidade,
    usuario,
    pavimento=None,
    local=None,
):
    """Atualiza apenas os dados comuns do material.

    Fornecedores/valores são ofertas independentes da linha e são tratados por
    ``salvar_valor_oferta``. Isso permite várias cotações para o mesmo material.
    """
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está bloqueada nesta etapa.")
    if material is None or not material.ativo:
        raise ValidationError("Selecione um material ativo do cadastro.")

    quantidade = _decimal_2(quantidade, nome="Quantidade", permitir_zero=False)
    micro_item.material = material
    micro_item.item = material.descricao_completa
    micro_item.unidade = material.unidade.sigla
    micro_item.quantidade = quantidade
    if pavimento is not None:
        micro_item.pavimento = (pavimento or "").strip()
    if local is not None:
        micro_item.local = (local or "").strip()
    micro_item.save(
        update_fields=["material", "item", "unidade", "quantidade", "pavimento", "local", "atualizado_em"]
    )
    registrar_evento(
        processo,
        "GF_ITEM_ATUALIZADO",
        usuario,
        f"Item atualizado: {material.descricao_completa}.",
        {"item_id": micro_item.pk, "material_id": material.pk},
    )
    return micro_item


@transaction.atomic
def excluir_item(*, micro_item, usuario):
    processo = micro_item.fluxo.processo
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está bloqueada nesta etapa.")
    if micro_item.pedido_item_id or micro_item.necessidade_gerada_id:
        raise ValidationError("Este item já foi materializado em pedido e não pode ser excluído.")
    descricao = micro_item.item
    micro_item.delete()
    registrar_evento(processo, "GF_ITEM_EXCLUIDO", usuario, f"Item removido da matriz: {descricao}.")


@transaction.atomic
def atualizar_item(*, micro_item, campo, valor, usuario):
    """Mantém os campos logísticos e a compatibilidade com o endpoint legado."""
    permitidos = {"pavimento", "local", "status", "quantidade_recebida"}
    if campo not in permitidos:
        raise ValidationError("Campo não permitido neste fluxo.")
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if campo == "status":
        raise ValidationError(
            "O status deste item é controlado exclusivamente pelo Pedido de Compra."
        )
    else:
        if not _matriz_editavel(processo):
            raise ValidationError(
                "Após a aprovação, somente o status individual de cada item pode ser alterado."
            )
        if campo == "quantidade_recebida":
            valor = _decimal_2(valor, nome="Quantidade recebida", permitir_zero=True)
        else:
            valor = (valor or "").strip()
    setattr(micro_item, campo, valor)
    micro_item.save(update_fields=[campo, "atualizado_em"])
    return micro_item


@transaction.atomic
def salvar_valor_oferta(*, micro_item, participante, valor, usuario):
    """Cria/atualiza uma oferta sem substituir as demais ofertas do material."""
    if not _matriz_editavel(micro_item.fluxo.processo):
        raise ValidationError("Os valores estão bloqueados nesta etapa.")
    if micro_item.fluxo_id != participante.fluxo_id:
        raise ValidationError("Item e fornecedor não pertencem à mesma matriz.")
    oferta = _salvar_oferta(
        micro_item=micro_item,
        participante=participante,
        valor=valor,
        usuario=usuario,
    )
    # A primeira proposta válida vira a seleção inicial. Ao adicionar outras
    # propostas a escolha atual permanece até o comprador trocar na matriz.
    if micro_item.participante_aprovado_id is None:
        micro_item.participante_aprovado = participante
        micro_item.save(update_fields=["participante_aprovado", "atualizado_em"])
    return oferta


@transaction.atomic
def adicionar_oferta_item(*, micro_item, fornecedor, valor, usuario):
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está bloqueada nesta etapa.")
    if fornecedor is None or not fornecedor.ativo:
        raise ValidationError("Selecione um fornecedor ativo.")
    participante = _obter_participante(
        fluxo=micro_item.fluxo,
        fornecedor=fornecedor,
        usuario=usuario,
    )
    if micro_item.ofertas.filter(participante=participante).exists():
        raise ValidationError("Este fornecedor já possui uma oferta para este material.")
    oferta = salvar_valor_oferta(
        micro_item=micro_item,
        participante=participante,
        valor=valor,
        usuario=usuario,
    )
    registrar_evento(
        processo,
        "GF_OFERTA_INCLUIDA",
        usuario,
        f"Oferta incluída: {micro_item.item} · {fornecedor.nome}.",
        {"item_id": micro_item.pk, "fornecedor_id": fornecedor.pk},
    )
    return oferta


@transaction.atomic
def excluir_oferta_item(*, micro_item, participante, usuario):
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("A matriz está bloqueada nesta etapa.")
    oferta = micro_item.ofertas.filter(participante=participante).first()
    if not oferta:
        raise ValidationError("Oferta não encontrada para este material.")
    era_escolhida = micro_item.participante_aprovado_id == participante.pk
    fornecedor_nome = participante.fornecedor.nome
    oferta.delete()
    if era_escolhida:
        proxima = micro_item.ofertas.select_related("participante").order_by("id").first()
        micro_item.participante_aprovado = proxima.participante if proxima else None
        micro_item.save(update_fields=["participante_aprovado", "atualizado_em"])
    registrar_evento(
        processo,
        "GF_OFERTA_EXCLUIDA",
        usuario,
        f"Oferta removida: {micro_item.item} · {fornecedor_nome}.",
    )


@transaction.atomic
def avancar_para_negociacao(*, processo, usuario):
    """Compatibilidade: a nova experiência trata compatibilização e negociação como uma etapa."""
    fluxo = obter_ou_criar_fluxo(processo)
    if not fluxo.itens.exists():
        raise ValidationError("Inclua pelo menos um item.")
    processo.etapa_atual = processo.Etapa.NEGOCIACAO
    processo.status = processo.Status.EM_NEGOCIACAO
    processo.data_compatibilizacao_concluida = processo.data_compatibilizacao_concluida or timezone.now()
    processo.save(update_fields=["etapa_atual", "status", "data_compatibilizacao_concluida", "atualizado_em"])
    sincronizar_data_real(processo, "COMPATIBILIZACAO", usuario)
    return processo


@transaction.atomic
def enviar_para_aprovacao(*, processo, usuario, condicao_pagamento_resumo=""):
    fluxo = obter_ou_criar_fluxo(processo)
    if not _matriz_editavel(processo):
        raise ValidationError("O processo não está na etapa de Compatibilização / Negociação.")
    if processo.etapa_atual == processo.Etapa.COMPATIBILIZACAO:
        raise ValidationError("Conclua a compatibilização antes de enviar a negociação ao gestor.")

    itens = list(
        fluxo.itens
        .select_related("material", "participante_aprovado__fornecedor")
        .prefetch_related("ofertas")
    )
    if not itens:
        raise ValidationError("Inclua pelo menos um item antes de enviar ao gestor.")

    incompletos = []
    for micro in itens:
        oferta = micro.oferta_negociada
        if not micro.material_id or not micro.participante_aprovado_id or not oferta or oferta.valor_atual is None or oferta.valor_atual <= ZERO:
            incompletos.append(micro.item or f"Item {micro.pk}")
    if incompletos:
        raise ValidationError(
            "Preencha material, fornecedor, quantidade e valor de todos os itens: "
            + ", ".join(incompletos[:5])
        )

    agora = timezone.now()
    fluxo.fornecedor_escolhido = None
    fluxo.condicao_pagamento_resumo = (condicao_pagamento_resumo or "").strip()
    fluxo.save(update_fields=["fornecedor_escolhido", "condicao_pagamento_resumo", "atualizado_em"])

    processo.etapa_atual = processo.Etapa.APROVACAO
    processo.status = processo.Status.AGUARDANDO_APROVACAO
    processo.data_compatibilizacao_concluida = processo.data_compatibilizacao_concluida or agora
    processo.data_negociacao_concluida = processo.data_negociacao_concluida or agora
    processo.save(
        update_fields=[
            "etapa_atual",
            "status",
            "data_compatibilizacao_concluida",
            "data_negociacao_concluida",
            "atualizado_em",
        ]
    )
    sincronizar_data_real(processo, "COMPATIBILIZACAO", usuario)
    sincronizar_data_real(processo, "NEGOCIACAO", usuario)
    registrar_evento(
        processo,
        "GF_ENVIADO_APROVACAO",
        usuario,
        f"Matriz com {len(itens)} item(ns) enviada ao gestor para aprovação.",
    )
    return processo


@transaction.atomic
def selecionar_fornecedor_item(*, processo, micro_item, participante, usuario):
    """Marca qual oferta será contratada para o material antes do envio ao gestor."""
    fluxo = obter_ou_criar_fluxo(processo)
    if micro_item.fluxo_id != fluxo.pk or participante.fluxo_id != fluxo.pk:
        raise ValidationError("Item ou fornecedor inválido para esta matriz.")
    oferta = micro_item.ofertas.filter(participante=participante, valor_atual__isnull=False).first()
    if not oferta:
        raise ValidationError("Esse fornecedor não possui valor informado para o item.")
    micro_item.participante_aprovado = participante
    micro_item.save(update_fields=["participante_aprovado", "atualizado_em"])
    return micro_item


def _materializar_para_pedido(*, fluxo, usuario):
    processo = fluxo.processo
    agora = timezone.now()
    itens = list(
        fluxo.itens
        .select_related("material__unidade", "participante_aprovado__fornecedor")
        .prefetch_related("ofertas")
        .select_for_update()
    )

    incompletos = []
    for micro in itens:
        oferta = micro.oferta_negociada
        if not micro.material_id or not micro.participante_aprovado_id or not oferta or oferta.valor_atual is None:
            incompletos.append(micro.item or f"Item {micro.pk}")
    if incompletos:
        raise ValidationError("Existem itens incompletos na matriz: " + ", ".join(incompletos[:5]))

    processo.adjudicacoes.filter(cancelada=False).update(
        cancelada=True,
        cancelada_por=usuario,
        cancelada_em=agora,
        motivo_cancelamento="Substituída pela aprovação da matriz de Grande Fornecedor.",
    )

    cotacoes = {}
    for micro in itens:
        participante = micro.participante_aprovado
        fornecedor = participante.fornecedor
        oferta = micro.oferta_negociada

        cotacao = cotacoes.get(fornecedor.pk)
        if not cotacao:
            cotacao, _ = CotacaoFornecedor.objects.get_or_create(
                processo=processo,
                fornecedor=fornecedor,
                defaults={"criado_por": usuario},
            )
            cotacao.condicao_pagamento = fluxo.condicao_pagamento_resumo[:255]
            cotacao.enviada_compatibilizacao_em = cotacao.enviada_compatibilizacao_em or agora
            cotacao.enviada_compatibilizacao_por = cotacao.enviada_compatibilizacao_por or usuario
            cotacao.enviada_negociacao_em = cotacao.enviada_negociacao_em or agora
            cotacao.enviada_negociacao_por = cotacao.enviada_negociacao_por or usuario
            cotacao.enviada_aprovacao_em = cotacao.enviada_aprovacao_em or agora
            cotacao.enviada_aprovacao_por = cotacao.enviada_aprovacao_por or usuario
            cotacao.save()
            cotacoes[fornecedor.pk] = cotacao

        necessidade = micro.necessidade_gerada
        if not necessidade:
            necessidade = NecessidadeCompra.objects.create(
                processo=processo,
                material=micro.material,
                descricao=micro.material.nome,
                especificacao=micro.material.especificacao,
                unidade=micro.material.unidade.sigla,
                quantidade_necessaria=micro.quantidade,
                quantidade_incluida=micro.quantidade,
                observacao="Item negociado no fluxo de Grande Fornecedor.",
            )
            micro.necessidade_gerada = necessidade
            micro.save(update_fields=["necessidade_gerada", "atualizado_em"])

        item_cotado, _ = CotacaoFornecedorItem.objects.update_or_create(
            cotacao=cotacao,
            necessidade=necessidade,
            defaults={
                "descricao_comercial": micro.material.descricao_completa,
                "quantidade": micro.quantidade,
                "valor_unitario_cotado": oferta.valor_inicial if oferta.valor_inicial is not None else oferta.valor_atual,
            },
        )
        CompatibilizacaoItem.objects.update_or_create(
            item_cotado=item_cotado,
            defaults={"resultado": CompatibilizacaoItem.Resultado.APROVADO, "responsavel": usuario},
        )
        NegociacaoItem.objects.update_or_create(
            item_cotado=item_cotado,
            defaults={
                "valor_unitario_negociado": oferta.valor_atual,
                "condicao_pagamento_negociada": fluxo.condicao_pagamento_resumo[:255],
                "atualizado_por": usuario,
            },
        )
        AdjudicacaoCompra.objects.create(
            processo=processo,
            necessidade=necessidade,
            cotacao=cotacao,
            item_cotado=item_cotado,
            quantidade=micro.quantidade,
            valor_unitario_final=oferta.valor_atual,
            desconto_final=ZERO,
            condicao_pagamento_final=fluxo.condicao_pagamento_resumo[:255],
            selecionado_por=usuario,
        )


@transaction.atomic
def decidir_aprovacao(*, processo, decisao, usuario, observacao=""):
    fluxo = obter_ou_criar_fluxo(processo)
    if processo.etapa_atual != processo.Etapa.APROVACAO:
        raise ValidationError("O processo não está aguardando aprovação.")
    if decisao not in AprovacaoCompra.Decisao.values:
        raise ValidationError("Decisão inválida.")
    if decisao != AprovacaoCompra.Decisao.APROVADO and not (observacao or "").strip():
        raise ValidationError("Informe o motivo da decisão.")

    ciclo = (processo.aprovacoes.order_by("-ciclo").values_list("ciclo", flat=True).first() or 0) + 1
    aprovacao = AprovacaoCompra.objects.create(
        processo=processo,
        ciclo=ciclo,
        usuario=usuario,
        decisao=decisao,
        observacao=(observacao or "").strip(),
    )

    if decisao == AprovacaoCompra.Decisao.AJUSTE_SOLICITADO:
        processo.etapa_atual = processo.Etapa.COMPATIBILIZACAO
        processo.status = processo.Status.AJUSTE_SOLICITADO
        processo.data_compatibilizacao_concluida = None
        processo.data_negociacao_concluida = None
        processo.save(
            update_fields=[
                "etapa_atual",
                "status",
                "data_compatibilizacao_concluida",
                "data_negociacao_concluida",
                "atualizado_em",
            ]
        )
        limpar_data_real(processo, "COMPATIBILIZACAO")
        limpar_data_real(processo, "NEGOCIACAO")
        registrar_evento(processo, "GF_AJUSTE_SOLICITADO", usuario, observacao)
        return aprovacao, []

    if decisao == AprovacaoCompra.Decisao.REPROVADO:
        processo.status = processo.Status.REPROVADO
        processo.save(update_fields=["status", "atualizado_em"])
        registrar_evento(processo, "GF_REPROVADO", usuario, observacao)
        return aprovacao, []

    _materializar_para_pedido(fluxo=fluxo, usuario=usuario)
    processo.status = processo.Status.APROVADO
    processo.save(update_fields=["status", "atualizado_em"])
    pedidos = gerar_pedidos(processo, usuario)

    mapa = {}
    for pedido in pedidos:
        mapa.update({pi.necessidade_id: pi for pi in pedido.itens.all()})
    for micro in fluxo.itens.all():
        pedido_item = mapa.get(micro.necessidade_gerada_id)
        if pedido_item:
            micro.pedido_item = pedido_item
            micro.status = GrandeFornecedorItem.Status.AGUARDANDO
            micro.quantidade_recebida = pedido_item.quantidade_recebida
            micro.previsao_entrega = pedido_item.pedido.previsao_entrega_atual
            micro.save(update_fields=[
                "pedido_item", "status", "quantidade_recebida", "previsao_entrega", "atualizado_em"
            ])

    registrar_evento(
        processo,
        "GF_APROVADO",
        usuario,
        f"Grande Fornecedor aprovado. {len(pedidos)} pedido(s) separado(s) por fornecedor gerado(s).",
    )
    return aprovacao, pedidos


@transaction.atomic
def atualizar_status_operacional_item(*, micro_item, novo_status, usuario):
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if not micro_item.pedido_item_id:
        raise ValidationError("O item ainda não possui pedido gerado.")
    if novo_status not in GrandeFornecedorItem.Status.values:
        raise ValidationError("Status inválido para o item.")
    if novo_status in STATUS_DERIVADOS_RECEBIMENTO:
        raise ValidationError("Entrega parcial e Entregue são definidos automaticamente pelo recebimento.")
    if novo_status not in transicoes_manuais(micro_item.status):
        raise ValidationError(
            f"Não é permitido alterar de {micro_item.get_status_display()} para "
            f"{GrandeFornecedorItem.Status(novo_status).label}."
        )
    anterior = micro_item.status
    micro_item.status = novo_status
    micro_item.save(update_fields=["status", "atualizado_em"])
    registrar_evento(
        processo,
        "GF_STATUS_ITEM",
        usuario,
        f"{micro_item.item}: {GrandeFornecedorItem.Status(anterior).label} → {micro_item.get_status_display()}.",
        {"item_id": micro_item.pk, "pedido_item_id": micro_item.pedido_item_id},
    )
    return micro_item


@transaction.atomic
def atualizar_previsao_operacional_item(*, micro_item, previsao, usuario):
    processo = micro_item.fluxo.processo
    _validar_fluxo(processo)
    if not micro_item.pedido_item_id:
        raise ValidationError("O item ainda não possui pedido gerado.")
    if micro_item.status in {GrandeFornecedorItem.Status.CANCELADO, GrandeFornecedorItem.Status.ENTREGUE}:
        raise ValidationError("A previsão não pode ser alterada neste status.")
    if not previsao:
        raise ValidationError("Informe a previsão de entrega.")
    anterior = micro_item.previsao_entrega
    micro_item.previsao_entrega = previsao
    micro_item.save(update_fields=["previsao_entrega", "atualizado_em"])
    registrar_evento(
        processo,
        "GF_PREVISAO_ITEM",
        usuario,
        f"Previsão de {micro_item.item} alterada para {previsao:%d/%m/%Y}.",
        {"item_id": micro_item.pk, "anterior": str(anterior or "")},
    )
    return micro_item


@transaction.atomic
def adicionar_parcela(*, processo, descricao, percentual=None, valor=None, data_prevista=None, gatilho="DATA"):
    fluxo = obter_ou_criar_fluxo(processo)
    ordem = (fluxo.parcelas.order_by("-ordem").values_list("ordem", flat=True).first() or 0) + 1
    return ParcelaGrandeFornecedor.objects.create(
        fluxo=fluxo,
        ordem=ordem,
        descricao=(descricao or "").strip(),
        percentual=percentual or None,
        valor=valor or None,
        data_prevista=data_prevista or None,
        gatilho=gatilho,
    )


@transaction.atomic
def adicionar_rateio(*, parcela, beneficiario_nome, documento, valor, observacao=""):
    valor = Decimal(str(valor))
    if valor <= 0:
        raise ValidationError("O valor do rateio deve ser maior que zero.")
    if parcela.valor is not None:
        ja_rateado = sum(parcela.rateios.values_list("valor", flat=True), ZERO)
        if ja_rateado + valor > parcela.valor:
            raise ValidationError("O rateio ultrapassa o valor previsto da parcela.")
    return RateioParcelaGrandeFornecedor.objects.create(
        parcela=parcela,
        beneficiario_nome=(beneficiario_nome or "").strip(),
        documento=(documento or "").strip(),
        valor=valor,
        observacao=(observacao or "").strip(),
    )
