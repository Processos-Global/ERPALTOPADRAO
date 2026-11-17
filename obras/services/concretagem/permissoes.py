"""Permissões da concretagem, sobre as ações específicas do módulo Obras.

Uma única permissão: "Concretagem" (ação "concretagem"). Quem tem vê e faz tudo:
lançar, enviar, aceitar manualmente, avançar/voltar etapa, concluir laudos,
formatos do mapa e indicadores. Sem ela, a concretagem não aparece nem para consulta
(só ter o módulo Obras não basta). A página pública da concreteira não exige login.

Os nomes `eh_gerente`/`pode_preencher` (e os decorators) continuam existindo
para não espalhar mudanças pelas views e templates; hoje todos equivalem a
`pode_concretagem`. Sempre verifique no backend; ocultar botões não basta.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from usuarios.decorators import possui_permissao_acao
from usuarios.models import ModuloSistema

ACAO_CONCRETAGEM = "concretagem"


def pode_concretagem(user):
    """Exige o módulo Obras e a permissão Concretagem marcada (superusuário passa)."""
    return possui_permissao_acao(user, ModuloSistema.OBRAS, ACAO_CONCRETAGEM)


# Ver também exige a permissão Concretagem.
pode_ver = pode_concretagem


# Equivalentes (antes havia "preencher" e "gerente" separados).
pode_preencher = pode_concretagem
eh_gerente = pode_concretagem


def pode_editar_concretagem(user, concretagem):
    return pode_concretagem(user)


def contexto_permissoes(user):
    pode = pode_concretagem(user)
    return {"pode_preencher": pode, "eh_gerente": pode}


def _exigir(checagem, mensagem):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not checagem(request.user):
                raise PermissionDenied(mensagem)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


ver_required = _exigir(pode_ver, "Você não possui a permissão Concretagem.")
preencher_required = _exigir(pode_concretagem, "Você não possui a permissão Concretagem.")
gerente_required = preencher_required
