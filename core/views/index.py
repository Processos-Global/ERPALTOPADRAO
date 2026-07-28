from django.contrib.auth.decorators import login_required
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
        "descricao": "Atendimento e assistência",
        "icone": "tools",
        "url_name": "",
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
    }

    return render(
        request,
        "core/index.html",
        contexto,
    )