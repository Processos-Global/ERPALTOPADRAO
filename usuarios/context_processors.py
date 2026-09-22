from django.urls import NoReverseMatch, reverse

from usuarios.models import ModuloSistema, NivelPermissao, Notificacao, PermissaoModulo
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

    notificacoes_recentes = list(
        Notificacao.objects
        .filter(usuario=request.user)
        .order_by("-atualizada_em", "-id")[:6]
    )
    notificacoes_nao_lidas = Notificacao.objects.filter(
        usuario=request.user,
        lida=False,
    ).count()

    planejamento_acesso = bool(permissoes.get(ModuloSistema.PLANEJAMENTO))
    compras_acesso = bool(permissoes.get(ModuloSistema.COMPRAS))
    projetos_acesso = bool(permissoes.get(ModuloSistema.PROJETOS))
    obras_acesso = bool(permissoes.get(ModuloSistema.OBRAS))
    cadastros_acesso = bool(permissoes.get(ModuloSistema.CADASTROS))
    financeiro_acesso = bool(permissoes.get(ModuloSistema.FINANCEIRO))

    if request.user.is_superuser:
        usuarios_acesso = True
    else:
        usuarios_acesso = PermissaoModulo.objects.filter(
            usuario=request.user,
            modulo=ModuloSistema.USUARIOS,
            ativo=True,
            nivel=NivelPermissao.ADMINISTRADOR,
        ).exists()

    return {
        "notificacoes_recentes": notificacoes_recentes,
        "planejamento_acesso": planejamento_acesso,
        "compras_acesso": compras_acesso,
        "projetos_acesso": projetos_acesso,
        "obras_acesso": obras_acesso,
        "cadastros_acesso": cadastros_acesso,
        "financeiro_acesso": financeiro_acesso,
        "usuarios_acesso": usuarios_acesso,
        "notificacoes_nao_lidas": notificacoes_nao_lidas,
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
