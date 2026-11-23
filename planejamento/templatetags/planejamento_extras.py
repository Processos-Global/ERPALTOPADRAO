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


@register.filter
def desvio_prazo(dias):
    if dias is None:
        return "Dados insuficientes"
    if dias == 0:
        return "No prazo"
    unidade = "dia" if abs(dias) == 1 else "dias"
    situacao = "adiantado" if dias < 0 else "atrasado"
    return f"{abs(dias)} {unidade} {situacao}"
