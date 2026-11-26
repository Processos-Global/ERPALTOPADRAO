from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from usuarios.context_processors import erp_layout
from usuarios.models import ModuloSistema


@login_required
def index_view(request):
    layout = erp_layout(request)
    if layout.get("is_cliente_pos_obra"):
        from pos_obra.access import cliente_do_usuario

        cliente = cliente_do_usuario(request.user)
        if not cliente:
            raise PermissionDenied("Acesso ao portal do cliente desabilitado.")
        return render(request, "core/index.html", {**layout, "cliente": cliente})

    modulos = [
        {
            "codigo": ModuloSistema.RELATORIOS if group["key"] == "indicadores" else group["key"].upper().replace("-", "_"),
            "titulo": group["label"], "icone": group["icon"], "url_name": group["landing"]["route"],
        }
        for group in layout["erp_nav_groups"]
    ]
    return render(request, "core/index.html", {**layout, "modulos": modulos, "total_modulos": len(modulos)})
