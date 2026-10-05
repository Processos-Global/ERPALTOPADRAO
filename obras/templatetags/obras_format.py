from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _numero(valor):
    try:
        return Decimal(str(valor or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@register.filter
def numero_br(valor, casas=2):
    numero = _numero(valor)
    casas = int(casas)
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def moeda_br(valor):
    return f"R$ {numero_br(valor, 2)}"


@register.filter
def nome_obra(obra):
    if not obra:
        return "—"
    return (getattr(obra, "nome_curto", "") or getattr(obra, "nome", "") or getattr(obra, "codigo", "") or "Obra").strip()
