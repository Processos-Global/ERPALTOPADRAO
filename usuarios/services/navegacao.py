"""Rotas de navegação do ERP. Os mesmos links alimentam o menu e a busca."""
from django.urls import reverse


PAIS_FINANCEIRO = {
    "financeiro:agenda": "financeiro:titulos",
    "financeiro:compromissos": "financeiro:previsoes",
    "financeiro:liberacoes": "financeiro:previsoes",
    "financeiro:relatorios_pagamento": "financeiro:pagamentos",
    "financeiro:relatorio_pagamento_excel": "financeiro:pagamentos",
    "financeiro:gastos": "financeiro:indicadores",
    "financeiro:analises": "financeiro:indicadores",
    "financeiro:despesas_recorrentes": "financeiro:plano_financeiro",
    "financeiro:despesa_recorrente_editar": "financeiro:plano_financeiro",
}


def _entry(request, route, label, terms=""):
    current = getattr(getattr(request, "resolver_match", None), "view_name", "")
    return {
        "route": route, "label": label, "url": reverse(route),
        "terms": terms, "current": current == route,
    }


def _entries(request, specs):
    return [_entry(request, route, title, terms) for route, title, terms, allowed in specs if allowed]


def _active_branch(request, entries, parent_routes=None):
    view_name = getattr(getattr(request, "resolver_match", None), "view_name", "")
    parent = parent_routes.get(view_name) if parent_routes else None
    return max(
        (entry for entry in entries if entry["current"] or entry["route"] == parent or request.path.startswith(entry["url"])),
        key=lambda entry: (entry["current"], entry["route"] == parent, len(entry["url"])),
        default=None,
    )


def navigation_context(request, groups, home_label, parent_routes=None):
    home = _entry(request, "core:index", home_label)
    active_group = None
    active_entry = None
    visible_groups = []
    for section, key, label, icon, specs in groups:
        entries = _entries(request, specs)
        if not entries:
            continue
        branch = _active_branch(request, entries, parent_routes)
        group = {
            "section": section, "key": key, "label": label, "icon": icon,
            "entries": entries, "landing": entries[0], "children": entries[1:],
            "active": branch is not None,
        }
        if branch is not None:
            active_group, active_entry = group, branch
        visible_groups.append(group)

    return {
        "erp_nav_home": home,
        "erp_nav_groups": visible_groups,
        "erp_nav_group": active_group,
        "erp_nav_branch": active_entry,
    }


def portal_navigation(request, available):
    return navigation_context(request, [
        ("Portal do cliente", "portal", "Portal do cliente", "building", [
            ("pos_obra:portal", "Meus imóveis", "solicitações assistência técnica", available),
            ("pos_obra:portal_novo", "Nova solicitação", "chamado assistência técnica", available),
        ]),
    ], "Minha área")


def acesso_menu_financeiro(permite):
    return {
        "financeiro": permite("VISUALIZAR"),
        "lancar_titulos": permite("LANCAR_TITULOS"),
        "aprovar_financeiro": permite("APROVAR"),
        "administrar_financeiro": permite("ADMINISTRAR"),
    }


def _secoes_financeiro(access):
    visualizar = access["financeiro"]
    return [
        ("financeiro:dashboard", "Visão geral", "financeiro saldo vencimento", visualizar),
        ("financeiro:titulos", "Solicitações de pagamento", "títulos contas a pagar agenda vencimentos", visualizar),
        ("financeiro:titulo_novo", "Solicitações de pagamento", "nova solicitação lançar título", access["lancar_titulos"] and not visualizar),
        ("financeiro:aprovacoes", "Aprovações", "decidir revisão pagamentos", access["aprovar_financeiro"]),
        ("financeiro:pagamentos", "Pagamentos", "programados efetivados malote relatórios de pagamento", visualizar),
        ("financeiro:previsoes", "Planejamento financeiro", "previsões compromissos contratos despesas recorrentes", visualizar),
        ("financeiro:indicadores", "Relatórios e indicadores", "análises gastos exportações", visualizar),
        ("financeiro:plano_financeiro", "Configurações", "apropriações plano financeiro despesas recorrentes", access["administrar_financeiro"]),
    ]


def menu_financeiro(request, access, entries=None):
    if entries is None:
        entries = _entries(request, _secoes_financeiro(access))
    return {
        "entries": entries,
        "branch": _active_branch(request, entries, PAIS_FINANCEIRO),
        "pode_lancar": access["lancar_titulos"],
        "pode_administrar": access["administrar_financeiro"],
    }


def internal_navigation(request, access):
    obras = access["obras"]
    compras = access["compras"]
    planejamento = access["planejamento"]
    suprimentos = access["suprimentos"]
    pos_obra = access["pos_obra"]
    projetos = access["projetos"]
    cadastros = access["cadastros"]
    context = navigation_context(request, [
        ("Operações", "obras", "Obras", "building", [
            ("obras:menu", "Obras", "", obras),
            ("obras:diario_lista", "Diário de Obra", "registro execução", obras),
            ("obras:fichas_tecnicas", "Ficha Técnica", "ambientes especificações", obras),
            ("obras:almoxarifado_dashboard", "Almoxarifado", "estoque transferências", obras),
            ("obras:fvs_lista", "FVS", "fichas verificação serviços", obras),
            ("obras:vistorias_lista", "Vistorias", "inspeção", obras),
            ("obras:cautelares_lista", "Vistoria Cautelar", "inspeção vizinhança", obras),
            ("obras:concretagem_painel", "Concretagem", "concreto laudos", access["concretagem"]),
        ]),
        ("Operações", "planejamento", "Planejamento", "calendar", [
            ("planejamento:menu", "Planejamento", "", planejamento or suprimentos),
            ("planejamento:painel_cronograma", "Cronograma Físico", "curva s avanço semanal", planejamento),
            ("planejamento:painel_cronograma_suprimentos", "Cronograma de Suprimentos", "prazos materiais", planejamento or suprimentos),
            ("planejamento:kanban_cronograma_suprimentos", "Quadro de Suprimentos", "kanban", planejamento or suprimentos),
        ]),
        ("Operações", "compras", "Compras", "cart", [
            ("compras:menu", "Compras", "suprimentos", compras),
            ("compras:dashboard", "Quadro de Compras", "kanban etapas comerciais", compras),
            ("compras:lista_processos", "Processos de Compra", "cotações compatibilizações negociações", compras),
            ("compras:lista_pedidos", "Pedidos", "ordens de compra recebimentos", compras),
            ("compras:grandes_fornecedores", "Grandes Fornecedores", "", compras),
            ("compras:contratos_dashboard", "Contratos", "", compras),
        ]),
        ("Operações", "financeiro", "Financeiro", "wallet", _secoes_financeiro(access)),
        ("Operações", "projetos", "Projetos", "ruler", [
            ("projetos:menu", "Projetos", "", projetos),
            ("projetos:checklist_compatibilizacao", "Checklist de compatibilização", "", projetos),
            ("projetos:checklist_documental", "Checklist documental", "documentação", projetos),
            ("projetos:alteracoes", "Alterações de projeto", "revisões histórico", projetos),
        ]),
        ("Operações", "pos-obra", "Pós-Obra", "tools", [
            ("pos_obra:painel", "Pós-Obra", "assistência técnica", pos_obra),
            ("pos_obra:lista", "Ordens de serviço", "chamados triagem", pos_obra),
            ("pos_obra:kanban", "Quadro de atendimentos", "kanban", pos_obra),
            ("pos_obra:agenda", "Agenda de Pós-Obra", "vistorias", pos_obra),
        ]),
        ("Operações", "indicadores", "Indicadores", "chart", [
            ("relatorios:indicadores", "Indicadores", "relatórios gerenciais análises", access["indicadores"]),
        ]),
        ("Cadastros", "cadastros", "Cadastros", "package", [
            ("cadastros:index", "Cadastros", "", cadastros),
            ("cadastros:fornecedores_lista", "Fornecedores", "", cadastros),
            ("cadastros:materiais_lista", "Materiais", "", cadastros),
            ("cadastros:mao_obra_lista", "Serviços de mão de obra", "", cadastros),
            ("cadastros:unidades_lista", "Unidades de medida", "", cadastros),
            ("cadastros:modelos_fvs_lista", "Modelos FVS", "", cadastros),
        ]),
        ("Configurações", "usuarios", "Usuários", "users", [
            ("usuarios:lista_usuarios", "Usuários", "permissões acessos configurações", access["usuarios"]),
        ]),
    ], "Início", parent_routes=PAIS_FINANCEIRO)
    entries = next((group["entries"] for group in context["erp_nav_groups"] if group["key"] == "financeiro"), [])
    context["financeiro_menu"] = menu_financeiro(request, access, entries)
    return context
