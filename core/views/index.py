from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render

from usuarios.models import (
    ModuloSistema,
    NivelPermissao,
    PermissaoModulo,
)


MODULOS_ERP = [
    {
        "codigo": ModuloSistema.OBRAS,
        "titulo": "Obras",
        "descricao": "Cadastros e ambientes",
        "icone": "building",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.PLANEJAMENTO,
        "titulo": "Planejamento",
        "descricao": "Cronogramas e avanço físico",
        "icone": "calendar",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.SUPRIMENTOS,
        "titulo": "Suprimentos",
        "descricao": "Prazos e contratações",
        "icone": "package",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.COMPRAS,
        "titulo": "Compras",
        "descricao": "Requisições e cotações",
        "icone": "cart",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.CONTRATOS,
        "titulo": "Contratos",
        "descricao": "Contratos e medições",
        "icone": "file",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.FINANCEIRO,
        "titulo": "Financeiro",
        "descricao": "Pagamentos e previsões",
        "icone": "wallet",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.ALMOXARIFADO,
        "titulo": "Almoxarifado",
        "descricao": "Estoque e movimentações",
        "icone": "warehouse",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.PROJETOS,
        "titulo": "Projetos",
        "descricao": "Documentos e revisões",
        "icone": "ruler",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.VISTORIAS,
        "titulo": "Vistorias",
        "descricao": "FVS e aprovações",
        "icone": "check",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.DIARIO_OBRA,
        "titulo": "Diário de obra",
        "descricao": "Registros da execução",
        "icone": "book",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.POS_OBRA,
        "titulo": "Pós-obra",
        "descricao": "Atendimentos, garantias e ordens de serviço",
        "icone": "tools",
        "url_name": "pos_obra:painel",
    },
    {
        "codigo": ModuloSistema.RELATORIOS,
        "titulo": "Relatórios",
        "descricao": "Indicadores consolidados",
        "icone": "chart",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.INTEGRACOES,
        "titulo": "Integrações",
        "descricao": "Drive e importações",
        "icone": "refresh",
        "url_name": "",
    },
    {
        "codigo": ModuloSistema.USUARIOS,
        "titulo": "Usuários",
        "descricao": "Acessos e permissões",
        "icone": "users",
        "url_name": "",
    },
]


@login_required
def index_view(request):
    from pos_obra.models import Cliente
    from pos_obra.access import cliente_do_usuario, acesso_interno
    from django.core.exceptions import PermissionDenied
    if Cliente.objects.filter(usuario=request.user).exists():
        cliente = cliente_do_usuario(request.user)
        if not cliente:
            raise PermissionDenied("Acesso ao portal do cliente desabilitado.")
        return render(request, "core/index.html", {"is_cliente_pos_obra": True, "cliente": cliente})
    if request.user.is_superuser:
        permissoes_por_modulo = {
            modulo["codigo"]: NivelPermissao.ADMINISTRADOR
            for modulo in MODULOS_ERP
        }
    else:
        permissoes = (
            PermissaoModulo.objects
            .filter(
                usuario=request.user,
                ativo=True,
            )
            .values(
                "modulo",
                "nivel",
            )
        )

        permissoes_por_modulo = {
            permissao["modulo"]: permissao["nivel"]
            for permissao in permissoes
        }

    # O painel e a barra lateral seguem a mesma autorização das views de Pós-Obra.
    pos_obra_acesso = acesso_interno(request.user)
    if pos_obra_acesso:
        permissoes_por_modulo.setdefault(ModuloSistema.POS_OBRA, NivelPermissao.EDICAO)
    else:
        permissoes_por_modulo.pop(ModuloSistema.POS_OBRA, None)

    niveis = dict(NivelPermissao.choices)
    modulos_liberados = []

    for modulo in MODULOS_ERP:
        nivel = permissoes_por_modulo.get(
            modulo["codigo"],
        )

        if not nivel:
            continue

        modulos_liberados.append(
            {
                **modulo,
                "nivel": nivel,
                "nivel_display": niveis.get(
                    nivel,
                    nivel,
                ),
            }
        )

    contexto = {
        "modulos": modulos_liberados,
        "total_modulos": len(modulos_liberados),
        "pos_obra_acesso": pos_obra_acesso,
    }

    return render(
        request,
        "core/index.html",
        contexto,
    )