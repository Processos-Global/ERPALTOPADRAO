from django.shortcuts import render

from usuarios.models import NivelPermissao

from compras.services.permissoes import compras_permission_required


@compras_permission_required(NivelPermissao.LEITURA)
def menu_suprimentos(request):
    return render(request, "compras/menu.html")
