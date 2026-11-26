from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import transaction

from compras.models import NecessidadeCompra, ProcessoCompra, ReservaEstoqueCompra

from .auditoria import registrar_evento
from .numeracao import gerar_numero
from .notificacoes import notificar_novo_processo_para_cotacao


CRONOGRAMAS_SEM_ATIVIDADE_FISICA = {"02-04-02"}


def _quantidade_positiva(valor):
    try:
        quantidade = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("Informe uma quantidade válida.") from exc
    if not quantidade.is_finite() or quantidade <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    DecimalValidator(18, 4)(quantidade)
    return quantidade


def _quantidade_comercial(valor, solicitada):
    quantidade = _quantidade_positiva(valor)
    if quantidade > solicitada:
        raise ValidationError("A quantidade a cotar não pode exceder a quantidade solicitada.")
    return quantidade


def _criar_necessidade(*, processo, material, quantidade, quantidade_compra=None, observacao=""):
    solicitada = _quantidade_positiva(quantidade)
    comercial = solicitada if quantidade_compra is None else _quantidade_comercial(quantidade_compra, solicitada)
    if material is None or not material.ativo:
        raise ValidationError("Selecione um material ativo do catálogo.")
    return NecessidadeCompra.objects.create(
        processo=processo,
        material=material,
        descricao=material.nome,
        especificacao=material.especificacao,
        unidade=material.unidade.sigla,
        quantidade_necessaria=solicitada,
        quantidade_incluida=comercial,
        observacao=(observacao or "").strip(),
    )


def permite_compra_sem_atividade(item_cronograma):
    """Retorna True para cronogramas autorizados a comprar sem atividade física.

    A exceção é intencionalmente restrita ao código 02-04-02. A identificação
    prioriza o código da aba do Cronograma de Suprimentos e também aceita o
    código da obra quando esse atributo existir no cadastro.
    """
    if item_cronograma is None:
        return False

    cronograma_obra = getattr(item_cronograma, "cronograma_obra", None)
    if cronograma_obra is None:
        return False

    codigos = {
        str(getattr(cronograma_obra, "codigo_aba", "") or "").strip().upper(),
    }

    obra = getattr(cronograma_obra, "obra", None)
    if obra is not None:
        codigos.add(str(getattr(obra, "codigo", "") or "").strip().upper())

    return bool(codigos & CRONOGRAMAS_SEM_ATIVIDADE_FISICA)


@transaction.atomic
def criar_processo(
    *,
    item_cronograma,
    titulo,
    usuario,
    apropriacao,
    itens,
    comprador=None,
    descricao="",
    observacao="",
    iniciar_cotacao=True,
):
    obra_id = item_cronograma.cronograma_obra.obra_id

    # Um mesmo suprimento pode originar várias compras ao longo da obra.
    # Cada ProcessoCompra é independente e mantém suas próprias atividades,
    # itens, fornecedores, cotações, aprovações e pedidos. Por isso NÃO há
    # mais bloqueio quando já existe outro processo ativo para o mesmo item
    # do Cronograma de Suprimentos.

    itens = list(itens)
    if apropriacao is None:
        raise ValidationError("Selecione a apropriação financeira da compra.")
    if apropriacao.pai_id is None:
        raise ValidationError("Selecione uma apropriação, não apenas a classe financeira.")

    # Somente GRANDE_FORNECEDOR usa o fluxo paralelo.
    # Ausente, legado ou não reconhecido permanece no fluxo normal principal.
    fluxo_grande_fornecedor = bool(item_cronograma.usa_fluxo_grande_fornecedor)

    if not itens and not fluxo_grande_fornecedor:
        raise ValidationError("Inclua pelo menos um item para iniciar a compra.")
    if fluxo_grande_fornecedor:
        # No fluxo especial o cronograma representa somente o suprimento macro.
        # Os itens reais nascem exclusivamente na matriz de compatibilização.
        itens = []

    processo = ProcessoCompra.objects.create(
        numero=gerar_numero("PROCESSO"),
        obra_id=obra_id,
        apropriacao=apropriacao,
        item_cronograma=item_cronograma,
        titulo=titulo or item_cronograma.item,
        fluxo_grande_fornecedor=fluxo_grande_fornecedor,
        categoria_grande_fornecedor=(
            item_cronograma.categoria_grande_fornecedor
            if fluxo_grande_fornecedor else None
        ),
        descricao=descricao,
        comprador=comprador or usuario,
        observacao=observacao,
        etapa_atual=(ProcessoCompra.Etapa.COMPATIBILIZACAO if fluxo_grande_fornecedor else ProcessoCompra.Etapa.COTACAO),
        status=(ProcessoCompra.Status.EM_COMPATIBILIZACAO if fluxo_grande_fornecedor else (ProcessoCompra.Status.SOLICITACAO_COTACAO if iniciar_cotacao else ProcessoCompra.Status.RASCUNHO)),
        criado_por=usuario,
    )

    for item in itens:
        _criar_necessidade(
            processo=processo, material=item.get("material"), quantidade=item["quantidade"],
            quantidade_compra=item.get("quantidade_compra"), observacao=item.get("observacao"),
        )

    from .sla import reconciliar_regra_inicial
    reconciliar_regra_inicial(processo)

    registrar_evento(
        processo,
        "CRIACAO",
        usuario,
        (
            f"Compra criada com apropriação {apropriacao.caminho} e {len(itens)} item(ns). "
            + (
                "Os micro itens e fornecedores serão definidos na matriz de Grande Fornecedor."
                if fluxo_grande_fornecedor
                else "Os fornecedores serão definidos pelo comprador na etapa de cotação."
            )
        ),
    )
    if fluxo_grande_fornecedor:
        registrar_evento(
            processo,
            "FLUXO_GRANDE_FORNECEDOR",
            usuario,
            "Processo aberto como Grande Fornecedor e direcionado para a matriz de compatibilização.",
        )
        # A Ficha Técnica é contínua. Se a obra já possuir itens da categoria
        # técnica deste processo, eles entram na matriz imediatamente na criação.
        from .grandes_fornecedores import sincronizar_itens_ficha_tecnica
        sincronizar_itens_ficha_tecnica(processo=processo, usuario=usuario)
    elif iniciar_cotacao:
        registrar_evento(processo, "PEDIDO_ENVIADO", usuario, "Pedido de compra enviado ao Suprimentos.")
        registrar_evento(
            processo,
            "SOLICITACAO_COTACAO_CRIADA",
            usuario,
            "Processo liberado para cotação. Aguardando o comprador selecionar fornecedores e registrar os envios.",
        )
        notificar_novo_processo_para_cotacao(processo)
    return processo


@transaction.atomic
def incluir_necessidade(
    *,
    processo,
    material,
    quantidade,
    usuario,
    observacao="",
    quantidade_compra=None,
):
    processo = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if processo.etapa_atual != processo.Etapa.COTACAO or processo.status in {
        processo.Status.CANCELADO,
        processo.Status.REPROVADO,
        processo.Status.CONTRATADO,
    }:
        raise ValidationError("Itens só podem ser incluídos enquanto o processo estiver na etapa de cotação.")

    necessidade = _criar_necessidade(
        processo=processo, material=material, quantidade=quantidade,
        quantidade_compra=quantidade_compra, observacao=observacao,
    )
    registrar_evento(
        processo,
        "NECESSIDADE_ADICIONADA",
        usuario,
        f"Item adicionado do catálogo: {material.codigo or material.nome} · {material.nome}",
        {
            "necessidade_id": necessidade.pk,
            "material_id": material.pk,
            "quantidade": str(necessidade.quantidade_necessaria),
            "quantidade_compra": str(necessidade.quantidade_incluida),
        },
    )
    return necessidade

@transaction.atomic
def excluir_necessidade(*, processo, necessidade, usuario):
    """Exclui um item do fluxo normal enquanto ele ainda está em cotação.

    O item é removido também das propostas ainda abertas dos fornecedores.
    Se qualquer proposta que contenha o item já tiver avançado no fluxo, a
    exclusão é bloqueada para preservar o histórico comercial.
    """
    processo = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if processo.fluxo_grande_fornecedor:
        raise ValidationError("Use a exclusão própria do fluxo de Grandes Fornecedores.")

    if processo.etapa_atual != ProcessoCompra.Etapa.COTACAO:
        raise ValidationError("Itens só podem ser excluídos enquanto o processo estiver na etapa de cotação.")

    if processo.status in {
        ProcessoCompra.Status.CANCELADO,
        ProcessoCompra.Status.REPROVADO,
        ProcessoCompra.Status.CONTRATADO,
    }:
        raise ValidationError("Este processo não permite mais excluir itens.")

    if necessidade.processo_id != processo.pk:
        raise ValidationError("O item informado não pertence a este processo.")
    necessidade = NecessidadeCompra.objects.filter(pk=necessidade.pk, processo=processo).first()
    if necessidade is None:
        raise ValidationError("O item informado não pertence a este processo.")
    if necessidade.situacao == NecessidadeCompra.Situacao.CANCELADA:
        raise ValidationError("Este item já foi cancelado.")

    itens_cotados = necessidade.itens_cotados.select_related("cotacao").all()
    if any(
        item.cotacao.enviada_compatibilizacao_em
        or item.cotacao.enviada_negociacao_em
        or item.cotacao.enviada_aprovacao_em
        for item in itens_cotados
    ):
        raise ValidationError(
            "Este item já faz parte de uma proposta que avançou no fluxo e não pode mais ser excluído."
        )

    if necessidade.adjudicacoes.filter(cancelada=False).exists() or necessidade.itens_pedido.exists():
        raise ValidationError("Este item já possui adjudicação ou pedido e não pode ser excluído.")

    descricao = necessidade.descricao
    necessidade_id = necessidade.pk
    quantidade = necessidade.quantidade_incluida
    # NecessidadeCompra é PROTECT em CotacaoFornecedorItem; removemos primeiro
    # apenas os itens das propostas ainda abertas, preservando as propostas.
    quantidade_propostas = itens_cotados.count()
    itens_cotados.delete()
    # A reserva preserva a origem da solicitação; não apagar a necessidade auditada.
    if ReservaEstoqueCompra.objects.filter(necessidade=necessidade).exists():
        necessidade.situacao = NecessidadeCompra.Situacao.CANCELADA
        necessidade.save(update_fields=["situacao"])
    else:
        necessidade.delete()

    registrar_evento(
        processo,
        "NECESSIDADE_EXCLUIDA",
        usuario,
        f"Item excluído da compra: {descricao}.",
        {
            "necessidade_id": necessidade_id,
            "descricao": descricao,
            "quantidade": str(quantidade),
            "propostas_afetadas": quantidade_propostas,
        },
    )

    return descricao, quantidade_propostas


@transaction.atomic
def criar_processo_avulso(*, obra, apropriacao, titulo, usuario, itens, comprador=None, descricao="", observacao="", iniciar_cotacao=True):
    itens = list(itens)
    if not itens:
        raise ValidationError("Inclua pelo menos um item para iniciar a compra avulsa.")
    if apropriacao is None or apropriacao.pai_id is None:
        raise ValidationError("Selecione uma apropriação financeira válida.")

    processo = ProcessoCompra.objects.create(
        numero=gerar_numero("PROCESSO"),
        obra=obra,
        apropriacao=apropriacao,
        item_cronograma=None,
        titulo=(titulo or "Compra avulsa").strip(),
        fluxo_grande_fornecedor=False,
        descricao=descricao,
        comprador=comprador or usuario,
        observacao=observacao,
        etapa_atual=ProcessoCompra.Etapa.COTACAO,
        status=(ProcessoCompra.Status.SOLICITACAO_COTACAO if iniciar_cotacao else ProcessoCompra.Status.RASCUNHO),
        criado_por=usuario,
    )

    for item in itens:
        _criar_necessidade(
            processo=processo, material=item.get("material"), quantidade=item["quantidade"],
            quantidade_compra=item.get("quantidade_compra"), observacao=item.get("observacao"),
        )
    from .sla import reconciliar_regra_inicial
    reconciliar_regra_inicial(processo)
    registrar_evento(processo, "CRIACAO_AVULSA", usuario, f"Compra avulsa criada com {len(itens)} item(ns) e apropriação {apropriacao.caminho}.")
    if iniciar_cotacao:
        notificar_novo_processo_para_cotacao(processo)
    return processo


@transaction.atomic
def editar_necessidade(*, processo, necessidade, material, quantidade, observacao, usuario):
    processo = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if processo.fluxo_grande_fornecedor:
        raise ValidationError("Use a edição própria do fluxo de Grandes Fornecedores.")
    if processo.etapa_atual != ProcessoCompra.Etapa.COTACAO or processo.status in {
        processo.Status.CANCELADO, processo.Status.REPROVADO, processo.Status.CONTRATADO,
    }:
        raise ValidationError("Itens só podem ser editados enquanto o processo estiver na etapa de cotação.")
    if necessidade.processo_id != processo.pk:
        raise ValidationError("O item informado não pertence a este processo.")
    necessidade = NecessidadeCompra.objects.filter(pk=necessidade.pk, processo=processo).first()
    if necessidade is None or necessidade.situacao == NecessidadeCompra.Situacao.CANCELADA:
        raise ValidationError("Este item não está disponível para edição.")
    itens_cotados = list(necessidade.itens_cotados.select_related("cotacao"))
    if any(i.cotacao.enviada_compatibilizacao_em or i.cotacao.enviada_negociacao_em or i.cotacao.enviada_aprovacao_em for i in itens_cotados):
        raise ValidationError("Este item já faz parte de uma proposta que avançou no fluxo e não pode mais ser editado.")
    if necessidade.adjudicacoes.filter(cancelada=False).exists() or necessidade.itens_pedido.exists():
        raise ValidationError("Este item já possui adjudicação ou pedido e não pode ser editado.")
    quantidade_compra = _quantidade_comercial(quantidade, necessidade.quantidade_necessaria)
    if material is None or (not material.ativo and material.pk != necessidade.material_id):
        raise ValidationError("Selecione um material ativo do catálogo.")
    material_anterior = necessidade.material_id
    quantidade_anterior = necessidade.quantidade_incluida
    necessidade.material = material
    necessidade.descricao = material.nome
    necessidade.especificacao = material.especificacao
    necessidade.unidade = material.unidade.sigla
    necessidade.quantidade_incluida = quantidade_compra
    necessidade.observacao = (observacao or "").strip()
    necessidade.save(update_fields=[
        "material", "descricao", "especificacao", "unidade", "quantidade_incluida", "observacao",
    ])
    for item in itens_cotados:
        if item.quantidade > quantidade_compra:
            item.quantidade = quantidade_compra
            item.save(update_fields=["quantidade", "atualizado_em"])
    registrar_evento(
        processo, "NECESSIDADE_EDITADA", usuario, f"Item editado: {necessidade.descricao}.",
        {
            "necessidade_id": necessidade.pk,
            "quantidade": str(quantidade_compra),
            "quantidade_compra_anterior": str(quantidade_anterior),
            "material_id_anterior": material_anterior,
            "material_id": material.pk,
        },
    )
    return necessidade
