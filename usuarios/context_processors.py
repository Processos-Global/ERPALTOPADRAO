from django.urls import NoReverseMatch, reverse

from usuarios.models import PermissaoModulo
from usuarios.services.registro_permissoes import MODULOS_REGISTRY


def _resolver_url(url_name):
    if not url_name:
        return ""
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return ""


def erp_layout(request):
    if not request.user.is_authenticated:
        return {}

    resolver_match = getattr(request, "resolver_match", None)
    current_view_name = resolver_match.view_name if resolver_match else ""

    if request.user.is_superuser:
        permissoes = {item.codigo: True for item in MODULOS_REGISTRY}
    else:
        permissoes = {
            modulo: True
            for modulo in PermissaoModulo.objects.filter(
                usuario=request.user,
                ativo=True,
            ).values_list("modulo", flat=True)
        }

    sidebar_modulos = []
    for item in sorted(MODULOS_REGISTRY, key=lambda modulo: modulo.ordem):
        if not permissoes.get(item.codigo):
            continue
        url = _resolver_url(item.url_name)
        sidebar_modulos.append({
            "codigo": item.codigo,
            "titulo": item.titulo,
            "icone": item.icone,
            "url_name": item.url_name,
            "url": url,
            "ativo": current_view_name == item.url_name,
            "desabilitado": not bool(url),
        })

    return {
        "sidebar_dashboard": {
            "titulo": "Painel Geral",
            "icone": "grid",
            "url": reverse("core:index"),
            "ativo": current_view_name == "core:index",
        },
        "sidebar_modulos": sidebar_modulos,
        "sidebar_total_modulos": len(sidebar_modulos),
        "sidebar_obra_ativa_nome": request.session.get("obra_ativa_nome", "Nenhuma obra selecionada"),
        "sidebar_obra_ativa_status": request.session.get("obra_ativa_status", "Sem obra ativa"),
    }
