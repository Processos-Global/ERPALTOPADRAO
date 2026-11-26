from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo

try:
    from usuarios.models import PermissaoFinanceiro
except ImportError:
    PermissaoFinanceiro = None


CAMPO_POR_ACAO = {
    "VISUALIZAR": "visualizar",
    "LANCAR_TITULOS": "lancar_titulos",
    "EDITAR_TITULOS": "editar_titulos",
    "APROVAR": "aprovar_pagamentos",
    "PAGAR": "registrar_pagamentos",
    "ADMINISTRAR": "administrar",
}


def _legado_permite(nivel, acao):
    if nivel == NivelPermissao.ADMINISTRADOR:
        return True
    if acao == "VISUALIZAR":
        return nivel in {NivelPermissao.LEITURA, NivelPermissao.EDICAO, NivelPermissao.APROVACAO}
    if acao == "APROVAR":
        return nivel == NivelPermissao.APROVACAO
    if acao == "ADMINISTRAR":
        return False
    return nivel in {NivelPermissao.EDICAO, NivelPermissao.APROVACAO}


def permissoes_modulo_financeiro_ativas():
    permissoes = PermissaoModulo.objects.filter(modulo=ModuloSistema.FINANCEIRO, ativo=True)
    if PermissaoFinanceiro is not None:
        return permissoes.select_related("usuario__permissao_financeiro_erp")
    return permissoes


def permissao_modulo_financeiro_permite(geral, acao):
    granular = getattr(geral.usuario, "permissao_financeiro_erp", None) if PermissaoFinanceiro is not None else None
    if granular is not None and granular.ativo:
        if granular.administrar:
            return True
        campo = CAMPO_POR_ACAO.get(str(acao))
        return bool(campo and getattr(granular, campo, False))
    return _legado_permite(geral.nivel, str(acao))


def possui_acao_financeiro(usuario, acao):
    if not usuario or not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True

    geral = permissoes_modulo_financeiro_ativas().filter(usuario=usuario).first()
    return geral is not None and permissao_modulo_financeiro_permite(geral, acao)


def financeiro_acao_required(acao):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not possui_acao_financeiro(request.user, acao):
                raise PermissionDenied("Você não possui permissão para executar esta ação no Financeiro.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
