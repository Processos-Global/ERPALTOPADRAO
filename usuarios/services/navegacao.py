"""Rotas de navegação do ERP. Os mesmos links alimentam o menu e a busca."""
from django.urls import reverse


def _entry(request, route, label, terms=""):
    current = getattr(getattr(request, "resolver_match", None), "view_name", "")
    return {
        "route": route, "label": label, "url": reverse(route),
        "terms": terms, "current": current == route,
    }


def navigation_context(request, groups, home_label):
    home = _entry(request, "core:index", home_label)
    active_group = None
    active_entry = None
    visible_groups = []
    path = request.path
    for section, key, label, icon, specs in groups:
        entries = [_entry(request, route, title, terms) for route, title, terms, allowed in specs if allowed]
        if not entries:
            continue
        branch = max(
            (entry for entry in entries if entry["current"] or path.startswith(entry["url"])),
            key=lambda entry: (entry["current"], len(entry["url"])),
            default=None,
        )
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


def internal_navigation(request, access):
    obras = access["obras"]
    compras = access["compras"]
    financeiro = access["financeiro"]
    planejamento = access["planejamento"]
    suprimentos = access["suprimentos"]
    pos_obra = access["pos_obra"]
    projetos = access["projetos"]
    cadastros = access["cadastros"]
    return navigation_context(request, [
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
        ("Operações", "financeiro", "Financeiro", "wallet", [
            ("financeiro:dashboard", "Visão Geral Financeira", "financeiro saldo vencimento", financeiro),
            ("financeiro:titulos", "Contas a Pagar", "títulos despesas vencimentos", financeiro),
            ("financeiro:titulo_novo", "Nova solicitação financeira", "lançar título pagamento", access["lancar_titulos"]),
            ("financeiro:pagamentos", "Pagamentos", "programados efetivados", financeiro),
            ("financeiro:compromissos", "Compromissos", "compras contratadas", financeiro),
            ("financeiro:previsoes", "Planejamento Financeiro", "previsões", financeiro),
            ("financeiro:relatorios_pagamento", "Relatórios de Pagamento", "exportações", financeiro),
            ("financeiro:indicadores", "Indicadores Financeiros", "relatórios", financeiro),
            ("financeiro:agenda", "Agenda Financeira", "calendário", financeiro),
        ]),
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
    ], "Início")
