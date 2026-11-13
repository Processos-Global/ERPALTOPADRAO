from django.shortcuts import render

from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def menu(request):
    return render(request, "obras/menu.html")
