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
    valor_liquido = _decimal(valor_liquido)
    total_pago = _decimal(total_pago)
    if total_pago <= 0:
        return "PENDENTE"
    if total_pago >= valor_liquido:
        return "PAGO"
    return "PAGO_PARCIAL"


def nivel_certeza_ordem(nivel):
    return NIVEIS_CERTEZA.get(nivel, 99)
