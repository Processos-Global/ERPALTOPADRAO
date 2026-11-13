from decimal import Decimal, InvalidOperation

from django import template

from financeiro.services.permissoes import possui_acao_financeiro

register = template.Library()


@register.filter
def moeda_br(valor):
    try:
        numero = Decimal(valor or 0)
    except (InvalidOperation, TypeError, ValueError):
        numero = Decimal("0")
    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@register.filter
def numero_br(valor, casas=2):
    try:
        numero = Decimal(valor or 0)
        casas = int(casas)
    except (InvalidOperation, TypeError, ValueError):
        return "0,00"
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def status_fin_classe(status):
    if status in {"PAGO", "APROVADO", "CONFERIDO", "EFETIVADO"}:
        return "success"
    if status in {"REJEITADO", "CANCELADO", "DIVERGENCIA", "ESTORNADO"}:
        return "danger"
    if status in {"AGUARDANDO_APROVACAO", "PREVISTA"}:
        return "warning"
    return "neutral"


@register.simple_tag(takes_context=True)
def pode_financeiro(context, acao):
    request = context.get("request")
    return bool(request and possui_acao_financeiro(request.user, acao))
