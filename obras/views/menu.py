from django.shortcuts import render

from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def menu(request):
    from obras.services.concretagem.permissoes import pode_concretagem

    return render(request, "obras/menu.html", {"pode_concretagem": pode_concretagem(request.user)})
