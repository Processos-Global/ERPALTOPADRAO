from django import template

from compras.services.permissoes import possui_acao_compras

register = template.Library()


@register.simple_tag(takes_context=True)
def pode_compras(context, acao):
    request = context.get("request")
    return bool(request and possui_acao_compras(request.user, acao))
