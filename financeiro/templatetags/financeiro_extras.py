from decimal import Decimal, InvalidOperation

from django import template

from financeiro.services.permissoes import (
    permissao_modulo_financeiro_permite, permissoes_modulo_financeiro_ativas, possui_acao_financeiro,
)
from usuarios.services.navegacao import acesso_menu_financeiro, menu_financeiro

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


@register.simple_tag(takes_context=True)
def navegacao_financeiro(context):
    if "financeiro_menu" in context:
        return context["financeiro_menu"]

    request = context.get("request")
    if not request or not request.user.is_authenticated or not request.user.is_active:
        return {}
    usuario = request.user
    permissao = None if usuario.is_superuser else permissoes_modulo_financeiro_ativas().filter(usuario=usuario).first()

    def permite(acao):
        return usuario.is_superuser or (permissao is not None and permissao_modulo_financeiro_permite(permissao, acao))

    return menu_financeiro(request, acesso_menu_financeiro(permite))
