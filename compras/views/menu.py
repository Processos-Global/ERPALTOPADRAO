from django.shortcuts import render

from usuarios.models import AcaoCompra

from compras.services.permissoes import compras_acao_required


@compras_acao_required(AcaoCompra.VISUALIZAR)
def menu_suprimentos(request):
    return render(request, "compras/menu.html")
