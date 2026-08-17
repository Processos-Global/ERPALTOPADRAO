from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import CotacaoFornecedor, CotacaoFornecedorItem, FornecedorCompra
from .auditoria import registrar_evento


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
    if processo.etapa_atual != processo.Etapa.COTACAO:
        raise ValidationError("Propostas só podem ser alteradas durante a etapa de cotação.")
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
    if cotacao.processo.etapa_atual != cotacao.processo.Etapa.COTACAO:
        raise ValidationError("Itens da proposta só podem ser alterados durante a etapa de cotação.")
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
