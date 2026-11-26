from urllib.parse import urlsplit

from django import template
from django.core.exceptions import TooManyFieldsSent
from django.http import QueryDict
from django.urls import reverse

register = template.Library()


@register.simple_tag
def retorno_listagem(request, rota_padrao, *rotas_alternativas):
    """Reconstitui o link com as origens admitidas pelo template de destino."""
    padrao = reverse(rota_padrao)
    retorno = request.GET.get("retorno", "")
    if not retorno.startswith("/") or retorno.startswith("//"):
        return padrao

    caminhos = (padrao, *(reverse(rota) for rota in rotas_alternativas))
    try:
        destino = urlsplit(retorno)
        if destino.path not in caminhos:
            return padrao
        filtros = QueryDict(destino.query, mutable=True)
    except (ValueError, TooManyFieldsSent):
        return padrao

    filtros.pop("retorno", None)
    query = filtros.urlencode()
    return f"{destino.path}?{query}" if query else destino.path
