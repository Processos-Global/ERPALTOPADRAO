from pathlib import PurePosixPath
from django import template
register=template.Library()
@register.filter
def nome_arquivo(value):
    return PurePosixPath(str(value).replace('\\','/')).name
@register.simple_tag(takes_context=True)
def permissoes_ui(context):
    from usuarios.decorators import possui_permissao_acao
    from usuarios.models import ModuloSistema
    user=context['request'].user
    return {key:possui_permissao_acao(user,ModuloSistema.POS_OBRA,action) for key,action in [('criar','abrir_ocorrencia'),('editar','editar_ocorrencia')]}
