from decimal import Decimal, InvalidOperation


# Status que o usuário pode selecionar manualmente no acompanhamento.
STATUS_OPERACIONAIS_MANUAIS = (
    "APROVACAO_PROJETO",
    "LIBERADO_MEDICAO",
    "PRODUCAO",
)

# Status exibidos no filtro/tela de acompanhamento. PARCIAL e ENTREGUE
# são calculados pelo recebimento do PedidoCompra.
STATUS_ACOMPANHAMENTO = (
    "APROVACAO_PROJETO",
    "LIBERADO_MEDICAO",
    "PRODUCAO",
    "PARCIAL",
    "ENTREGUE",
)

STATUS_DERIVADOS_RECEBIMENTO = {"PARCIAL", "ENTREGUE"}


def transicoes_manuais(status_atual):
    """Retorna as etapas operacionais disponíveis para seleção manual.

    O fluxo não é travado em sequência: Aprovação de projeto, Liberado p/
    medição e Produção podem ser escolhidos conforme a situação real do item.
    Entrega Parcial e Entregue permanecem derivados do recebimento.
    """
    atual = str(status_atual or "")
    if atual in STATUS_DERIVADOS_RECEBIMENTO or atual == "CANCELADO":
        return ()
    return tuple(status for status in STATUS_OPERACIONAIS_MANUAIS if status != atual)


def _decimal(valor):
    try:
        return Decimal(str(valor or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def status_por_recebimento(quantidade, quantidade_recebida, status_atual):
    total = _decimal(quantidade)
    recebido = _decimal(quantidade_recebida)
    if total > 0 and recebido >= total:
        return "ENTREGUE"
    if recebido > 0:
        return "PARCIAL"
    return str(status_atual or "APROVACAO_PROJETO")
