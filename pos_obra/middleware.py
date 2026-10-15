"""Bloqueia as rotas internas do ERP para contas de clientes do Pós-Obra."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import resolve, Resolver404

from .models import Cliente
from .access import cliente_do_usuario


class IsolamentoPortalClienteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and Cliente.objects.filter(usuario=user).exists():
            try:
                match = resolve(request.path_info)
                nome = match.view_name or ""
            except Resolver404:
                nome = ""
            if nome == "usuarios:logout":
                return self.get_response(request)
            if not cliente_do_usuario(user):
                raise PermissionDenied("O acesso do cliente ao portal está desabilitado.")
            if not nome.startswith("pos_obra:portal") and nome not in ("pos_obra:pesquisa", "pos_obra:anexo", "core:index"):
                if request.method in ("GET", "HEAD"):
                    return redirect("pos_obra:portal")
                raise PermissionDenied("Clientes não podem executar operações internas do ERP.")
        return self.get_response(request)
