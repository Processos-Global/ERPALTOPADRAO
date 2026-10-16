from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema
from django.shortcuts import render


@modulo_required(ModuloSistema.PROJETOS)
def menu_projetos(request):
    return render(
        request,
        "projetos/menu.html",
    )
