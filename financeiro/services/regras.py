from decimal import Decimal


NIVEIS_CERTEZA = {
    "REALIZADO": 0,
    "COMPROMETIDO": 1,
    "CONTRATADO": 2,
    "PREVISTO": 3,
}


def _decimal(valor):
    if valor in (None, ""):
        return Decimal("0")
    return Decimal(valor)


def calcular_saldo_titulo(valor_original, acrescimos=0, descontos=0, total_pago=0):
    total = _decimal(valor_original) + _decimal(acrescimos) - _decimal(descontos)
    return max(total - _decimal(total_pago), Decimal("0"))


def calcular_status_pagamento(valor_liquido, total_pago):
    """Financeiro v2 não trabalha com pagamento parcial de uma Conta a Pagar."""
    valor_liquido = _decimal(valor_liquido)
    total_pago = _decimal(total_pago)
    if total_pago <= 0:
        return "PENDENTE"
    return "PAGO" if total_pago >= valor_liquido else "INCONSISTENTE"


def nivel_certeza_ordem(nivel):
    return NIVEIS_CERTEZA.get(nivel, 99)


def calcular_situacao_temporal(vencimento, status, hoje):
    """Classifica o vencimento sem substituir o status do fluxo financeiro."""
    if status in {"PAGO", "CANCELADO"}:
        return "ENCERRADA"
    if vencimento is None:
        return "SEM_DATA"
    if vencimento < hoje:
        return "VENCIDA"
    if vencimento == hoje:
        return "VENCE_HOJE"
    return "A_VENCER"


def distribuir_valor_parcelas(valor_total, quantidade):
    """Divide um valor em parcelas iguais preservando exatamente os centavos."""
    valor_total = _decimal(valor_total).quantize(Decimal("0.01"))
    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantidade de parcelas inválida.") from exc
    if quantidade <= 0:
        raise ValueError("Quantidade de parcelas deve ser maior que zero.")
    if valor_total <= 0:
        raise ValueError("Valor total deve ser maior que zero.")

    centavos = int(valor_total * 100)
    base, resto = divmod(centavos, quantidade)
    return [Decimal(base + (1 if indice < resto else 0)) / Decimal("100") for indice in range(quantidade)]
