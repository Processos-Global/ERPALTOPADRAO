from decimal import Decimal, ROUND_HALF_UP

CENTAVO = Decimal("0.01")
ZERO = Decimal("0")


def _decimal(valor):
    return Decimal(str(valor or ZERO))


def quantizar_moeda(valor):
    return _decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_total_proposta(*, subtotal, desconto=ZERO, frete=ZERO):
    """Calcula o total comercial: subtotal - desconto geral + frete."""
    total = _decimal(subtotal) - _decimal(desconto) + _decimal(frete)
    return quantizar_moeda(max(total, ZERO))


def preco_final_valido(valor):
    """Preço zero/negativo não representa uma oferta elegível para aprovação."""
    if valor is None:
        return False
    return _decimal(valor) > ZERO
