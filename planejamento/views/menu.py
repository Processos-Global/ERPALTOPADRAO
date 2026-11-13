from django.shortcuts import render

from usuarios.decorators import algum_modulo_required
from usuarios.models import ModuloSistema


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
def menu_planejamento(request):
    return render(request, "planejamento/menu.html")
