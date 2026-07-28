from django.urls import NoReverseMatch, reverse

from usuarios.models import ModuloSistema, PermissaoModulo


SIDEBAR_MODULES = [
    {
        "codigo": ModuloSistema.USUARIOS,
        "titulo": "Controle de Usuários",
        "icone": "users",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.PLANEJAMENTO,
        "titulo": "Cronograma de Obra",
        "icone": "calendar",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.SUPRIMENTOS,
        "titulo": "Cronograma de Suprimentos",
        "icone": "package",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.COMPRAS,
        "titulo": "Compras",
        "icone": "cart",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.CONTRATOS,
        "titulo": "Contratos",
        "icone": "file",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.FINANCEIRO,
        "titulo": "Financeiro",
        "icone": "wallet",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.ALMOXARIFADO,
        "titulo": "Almoxarifado",
        "icone": "warehouse",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.PROJETOS,
        "titulo": "Projetos",
        "icone": "ruler",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.VISTORIAS,
        "titulo": "Vistorias",
        "icone": "check",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.DIARIO_OBRA,
        "titulo": "Diário de Obra",
        "icone": "book",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.POS_OBRA,
        "titulo": "Pós-obra",
        "icone": "tools",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.RELATORIOS,
        "titulo": "Relatórios",
        "icone": "chart",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.INTEGRACOES,
        "titulo": "Integrações",
        "icone": "refresh",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.OBRAS,
        "titulo": "Obras",
        "icone": "building",
        "url_name": "",
    },
]


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
        permissoes = {
            item["codigo"]: True
            for item in SIDEBAR_MODULES
        }
    else:
        permissoes_qs = (
            PermissaoModulo.objects
            .filter(
                usuario=request.user,
                ativo=True,
            )
            .values_list(
                "modulo",
                flat=True,
            )
        )

        permissoes = {
            modulo: True
            for modulo in permissoes_qs
        }

    sidebar_modulos = []

    for item in SIDEBAR_MODULES:
        if not permissoes.get(item["codigo"]):
            continue

        url = _resolver_url(item["url_name"])

        sidebar_modulos.append(
            {
                **item,
                "url": url,
                "ativo": current_view_name == item["url_name"],
                "desabilitado": not bool(url),
            }
        )

    obra_ativa_nome = request.session.get(
        "obra_ativa_nome",
        "Nenhuma obra selecionada",
    )

    obra_ativa_status = request.session.get(
        "obra_ativa_status",
        "Sem obra ativa",
    )

    dashboard_url = reverse("core:index")

    return {
        "sidebar_dashboard": {
            "titulo": "Painel Geral",
            "icone": "grid",
            "url": dashboard_url,
            "ativo": current_view_name == "core:index",
        },
        "sidebar_modulos": sidebar_modulos,
        "sidebar_total_modulos": len(sidebar_modulos),
        "sidebar_obra_ativa_nome": obra_ativa_nome,
        "sidebar_obra_ativa_status": obra_ativa_status,
    }