from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo

ORDEM = {
    NivelPermissao.LEITURA: 1,
    NivelPermissao.EDICAO: 2,
    NivelPermissao.APROVACAO: 3,
    NivelPermissao.ADMINISTRADOR: 4,
}

def possui_permissao_compras(usuario, nivel_minimo=NivelPermissao.LEITURA):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    p = PermissaoModulo.objects.filter(usuario=usuario, modulo=ModuloSistema.COMPRAS, ativo=True).only("nivel").first()
    return bool(p and ORDEM.get(p.nivel, 0) >= ORDEM.get(nivel_minimo, 999))

def compras_permission_required(nivel_minimo=NivelPermissao.LEITURA):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not possui_permissao_compras(request.user, nivel_minimo):
                raise PermissionDenied("Você não possui permissão suficiente no módulo de Compras.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
