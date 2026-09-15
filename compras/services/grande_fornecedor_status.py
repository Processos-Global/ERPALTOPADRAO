from decimal import Decimal, InvalidOperation

TRANSICOES_MANUAIS = {
    "AGUARDANDO": ("CONFIRMADO", "CANCELADO"),
    "CONFIRMADO": ("PRODUCAO", "PRONTO", "TRANSPORTE", "CANCELADO"),
    "PRODUCAO": ("PRONTO", "TRANSPORTE", "CANCELADO"),
    "PRONTO": ("TRANSPORTE", "CANCELADO"),
    "TRANSPORTE": ("CANCELADO",),
    "PARCIAL": ("TRANSPORTE", "CANCELADO"),
    "ENTREGUE": (),
    "CANCELADO": (),
}

STATUS_DERIVADOS_RECEBIMENTO = {"PARCIAL", "ENTREGUE"}


def transicoes_manuais(status_atual):
    return TRANSICOES_MANUAIS.get(str(status_atual or ""), ())


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
    return str(status_atual or "AGUARDANDO")
