from django import template


register = template.Library()


@register.filter
def percentual(valor, casas=2):
    if valor is None:
        return "-"

    try:
        numero = float(valor) * 100
        casas = int(casas)

        return f"{numero:.{casas}f}".replace(".", ",")

    except (TypeError, ValueError):
        return "-"