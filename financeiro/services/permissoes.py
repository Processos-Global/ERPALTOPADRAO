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


def possui_acao_financeiro(usuario, acao):
    if not usuario or not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True

    geral = PermissaoModulo.objects.filter(
        usuario=usuario,
        modulo=ModuloSistema.FINANCEIRO,
        ativo=True,
    ).first()
    if geral is None:
        return False

    if PermissaoFinanceiro is not None:
        granular = PermissaoFinanceiro.objects.filter(usuario=usuario, ativo=True).first()
        if granular is not None:
            if granular.administrar:
                return True
            campo = CAMPO_POR_ACAO.get(str(acao))
            return bool(campo and getattr(granular, campo, False))

    return _legado_permite(geral.nivel, str(acao))


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
