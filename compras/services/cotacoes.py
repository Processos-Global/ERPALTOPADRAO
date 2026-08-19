from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import CotacaoFornecedor, CotacaoFornecedorItem, FornecedorCompra
from .auditoria import registrar_evento
from .comercial import processo_em_fase_comercial


@transaction.atomic
def criar_fornecedor(*, nome, documento="", email="", telefone=""):
    nome = (nome or "").strip()
    documento = (documento or "").strip()
    if not nome:
        raise ValidationError("Informe o nome do fornecedor.")
    if documento:
        fornecedor, _ = FornecedorCompra.objects.get_or_create(
            documento=documento,
            defaults={"nome": nome, "email": email, "telefone": telefone},
        )
        return fornecedor
    return FornecedorCompra.objects.create(nome=nome, email=email, telefone=telefone)


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
    cotacao, criada = CotacaoFornecedor.objects.get_or_create(
        processo=processo,
        fornecedor=fornecedor,
        defaults={"criado_por": usuario, **dados},
    )
    if not criada:
        for campo, valor in dados.items():
            setattr(cotacao, campo, valor)
        cotacao.save()
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

    fornecedor_nome = cotacao.fornecedor.nome
    cotacao_id = cotacao.pk
    fornecedor_id = cotacao.fornecedor_id
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
    return fornecedor_nome
