from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


_ORDEM_NIVEL = {
    NivelPermissao.LEITURA: 1,
    NivelPermissao.EDICAO: 2,
    NivelPermissao.APROVACAO: 3,
    NivelPermissao.ADMINISTRADOR: 4,
}


def possui_permissao_modulo(usuario, modulo, nivel_minimo=NivelPermissao.LEITURA):
    if not usuario or not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True

    permissao = (
        PermissaoModulo.objects
        .filter(usuario=usuario, modulo=modulo, ativo=True)
        .only("nivel")
        .first()
    )
    if permissao is None:
        return False

    return _ORDEM_NIVEL.get(permissao.nivel, 0) >= _ORDEM_NIVEL.get(nivel_minimo, 999)


def modulo_required(modulo, nivel_minimo=NivelPermissao.LEITURA):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not possui_permissao_modulo(request.user, modulo, nivel_minimo):
                try:
                    nome_modulo = ModuloSistema(modulo).label
                except ValueError:
                    nome_modulo = str(modulo)
                raise PermissionDenied(
                    f"Você não possui permissão suficiente no módulo {nome_modulo}."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def algum_modulo_required(*modulos):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if any(possui_permissao_modulo(request.user, modulo) for modulo in modulos):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Você não possui permissão para acessar esta área.")
        return wrapper
    return decorator
