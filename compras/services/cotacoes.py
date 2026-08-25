from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import CotacaoFornecedor, CotacaoFornecedorItem, FornecedorCompra, SolicitacaoCotacaoFornecedor
from .auditoria import registrar_evento
from .comercial import processo_em_fase_comercial
from .solicitacoes_cotacao import marcar_solicitacao_respondida, restaurar_solicitacao_apos_exclusao_proposta


@transaction.atomic
def criar_fornecedor(*, nome, documento="", email="", telefone="", avaliacao=None):
    nome = (nome or "").strip()
    documento = (documento or "").strip()
    if not nome:
        raise ValidationError("Informe o nome do fornecedor.")
    if documento:
        fornecedor, _ = FornecedorCompra.objects.get_or_create(
            documento=documento,
            defaults={"nome": nome, "email": email, "telefone": telefone, "avaliacao": avaliacao},
        )
        return fornecedor
    return FornecedorCompra.objects.create(nome=nome, email=email, telefone=telefone, avaliacao=avaliacao)


@transaction.atomic
def incluir_cotacao(*, processo, fornecedor, usuario, **dados):
    if not processo_em_fase_comercial(processo):
        raise ValidationError(
            "O mapa comercial já foi fechado. Propostas não podem mais ser alteradas."
        )
    if dados.get("frete") is None:
        dados["frete"] = Decimal("0")
    if processo.status == processo.Status.CANCELADO:
        raise ValidationError("Processo cancelado não pode receber cotação.")

    cotacao_existente = CotacaoFornecedor.objects.filter(
        processo=processo,
        fornecedor=fornecedor,
    ).first()
    if cotacao_existente is None:
        envio_registrado = SolicitacaoCotacaoFornecedor.objects.filter(
            processo=processo,
            fornecedor=fornecedor,
            status=SolicitacaoCotacaoFornecedor.Status.ENVIADA,
            enviada_em__isnull=False,
        ).exists()
        if not envio_registrado:
            raise ValidationError(
                "A proposta só pode ser cadastrada depois que o envio da solicitação de cotação para este fornecedor for registrado."
            )

    cotacao, criada = CotacaoFornecedor.objects.get_or_create(
        processo=processo,
        fornecedor=fornecedor,
        defaults={"criado_por": usuario, **dados},
    )
    if not criada:
        if cotacao.enviada_compatibilizacao_em or cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em:
            raise ValidationError("A proposta já avançou no fluxo e não pode mais ser alterada sem retorno de etapa.")
        for campo, valor in dados.items():
            setattr(cotacao, campo, valor)
        cotacao.save()
    marcar_solicitacao_respondida(
        processo=processo,
        fornecedor=fornecedor,
        usuario=usuario,
        data=cotacao.criado_em,
    )
    registrar_evento(
        processo,
        "FORNECEDOR_COTACAO",
        usuario,
        f"Fornecedor {fornecedor.nome} incluído/atualizado na cotação.",
        {"cotacao_id": cotacao.pk, "fornecedor_id": fornecedor.pk},
    )
    return cotacao


@transaction.atomic
def incluir_item_cotacao(*, cotacao, necessidade, quantidade, valor_unitario, usuario, **dados):
    if cotacao.enviada_compatibilizacao_em or cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em:
        raise ValidationError("A proposta já avançou no fluxo e não pode mais ser alterada sem retorno de etapa.")
    if not processo_em_fase_comercial(cotacao.processo):
        raise ValidationError(
            "O mapa comercial já foi fechado. Itens da proposta não podem mais ser alterados."
        )
    if necessidade.processo_id != cotacao.processo_id:
        raise ValidationError("A necessidade não pertence ao processo desta cotação.")
    quantidade = Decimal(str(quantidade))
    valor_unitario = Decimal(str(valor_unitario))
    if quantidade <= 0 or quantidade > necessidade.quantidade_incluida:
        raise ValidationError("Quantidade cotada inválida para esta necessidade.")
    if dados.get("desconto_cotado") is None:
        dados["desconto_cotado"] = Decimal("0")
    item, _ = CotacaoFornecedorItem.objects.update_or_create(
        cotacao=cotacao,
        necessidade=necessidade,
        defaults={
            "quantidade": quantidade,
            "valor_unitario_cotado": valor_unitario,
            **dados,
        },
    )
    registrar_evento(
        cotacao.processo,
        "PROPOSTA_ATUALIZADA",
        usuario,
        f"Proposta de {cotacao.fornecedor.nome} atualizada para {necessidade.descricao}.",
        {"item_cotado_id": item.pk},
    )
    return item


@transaction.atomic
def excluir_cotacao(*, cotacao, usuario):
    """Exclui uma proposta completa enquanto o mapa comercial está aberto.

    Cotação, análise técnica e negociação podem ocorrer em paralelo. A exclusão
    só é bloqueada depois que o comprador fecha o mapa e o envia à aprovação.
    """
    processo = cotacao.processo

    if not processo_em_fase_comercial(processo):
        raise ValidationError(
            "A proposta só pode ser excluída enquanto o mapa comercial estiver aberto."
        )

    if processo.status == processo.Status.CANCELADO:
        raise ValidationError("Processo cancelado não pode ter propostas alteradas.")

    if cotacao.itens.filter(compatibilizacoes__isnull=False).exists():
        raise ValidationError(
            "Esta proposta já possui histórico de análise técnica e não pode ser excluída. "
            "Mantenha-a no mapa e registre uma nova decisão técnica, se necessário."
        )
    if cotacao.itens.filter(historico_negociacoes__isnull=False).exists():
        raise ValidationError(
            "Esta proposta já possui histórico de negociação e não pode ser excluída."
        )
    if cotacao.adjudicacoes.filter(cancelada=False).exists():
        raise ValidationError(
            "Esta proposta possui quantidade selecionada. Remova a seleção comercial antes de excluí-la."
        )

    fornecedor = cotacao.fornecedor
    fornecedor_nome = fornecedor.nome
    cotacao_id = cotacao.pk
    fornecedor_id = fornecedor.pk
    quantidade_itens = cotacao.itens.count()

    registrar_evento(
        processo,
        "PROPOSTA_EXCLUIDA",
        usuario,
        f"Proposta de {fornecedor_nome} excluída da cotação.",
        {
            "cotacao_id": cotacao_id,
            "fornecedor_id": fornecedor_id,
            "quantidade_itens": quantidade_itens,
        },
    )

    cotacao.delete()
    restaurar_solicitacao_apos_exclusao_proposta(
        processo=processo,
        fornecedor=fornecedor,
    )
    return fornecedor_nome
