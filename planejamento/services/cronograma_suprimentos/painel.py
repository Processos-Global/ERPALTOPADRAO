from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from planejamento.models.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)


ETAPAS_FILTRO = [
    (ItemCronogramaSuprimento.Etapa.COTACAO, "Cotação"),
    (ItemCronogramaSuprimento.Etapa.COMPATIBILIZACAO, "Compatibilização"),
    (ItemCronogramaSuprimento.Etapa.NEGOCIACAO, "Negociação"),
    (ItemCronogramaSuprimento.Etapa.CONTRATACAO, "Contratação"),
    (ItemCronogramaSuprimento.Etapa.CONCLUIDO, "Concluído"),
]


def _filtrar_por_etapa(itens, etapa: str):
    if not etapa:
        return itens
    return [item for item in itens if item.etapa_atual == etapa]


def _decorar_desvio(item, atributo: str, desvio):
    """Prepara valor, classe visual e texto do desvio Planejado x Realizado."""
    setattr(item, f"{atributo}_desvio_dias", desvio)

    if desvio is None:
        setattr(item, f"{atributo}_desvio_classe", "")
        setattr(item, f"{atributo}_desvio_label", "")
        return

    if desvio > 0:
        classe = "late"
        label = f"+{desvio} dia{'s' if desvio != 1 else ''}"
    elif desvio < 0:
        dias = abs(desvio)
        classe = "early"
        label = f"-{dias} dia{'s' if dias != 1 else ''}"
    else:
        classe = "ontime"
        label = "No prazo"

    setattr(item, f"{atributo}_desvio_classe", classe)
    setattr(item, f"{atributo}_desvio_label", label)


def _decorar_item(item, hoje):
    item.percentual_calculado = item.percentual_andamento
    item.etapas_concluidas = item.percentual_andamento // 25
    item.etapa_calculada = item.etapa_atual
    item.etapa_calculada_label = item.etapa_atual_label
    item.prazo_etapa_atual = item.data_planejada_etapa_atual
    item.dias_atraso_calculado = item.dias_atraso_etapa_atual
    item.atrasado_calculado = item.etapa_atual_atrasada

    # Situação individual de cada marco para a tabela.
    item.cotacao_atrasada = bool(
        not item.data_real_cotacao
        and item.data_cotacao
        and item.data_cotacao < hoje
    )
    item.compatibilizacao_atrasada = bool(
        not item.data_real_compatibilizacao
        and item.data_compatibilizacao
        and item.data_compatibilizacao < hoje
    )
    item.negociacao_atrasada = bool(
        not item.data_real_negociacao
        and item.data_negociacao
        and item.data_negociacao < hoje
    )
    item.contratacao_atrasada = bool(
        not item.data_real_contratacao
        and item.prazo_limite_contratacao
        and item.prazo_limite_contratacao < hoje
    )

    _decorar_desvio(item, "cotacao", item.desvio_cotacao_dias)
    _decorar_desvio(
        item,
        "compatibilizacao",
        item.desvio_compatibilizacao_dias,
    )
    _decorar_desvio(item, "negociacao", item.desvio_negociacao_dias)
    _decorar_desvio(item, "contratacao", item.desvio_contratacao_dias)
    return item


def montar_painel_cronograma_suprimentos(
    *,
    obra_id=None,
    categoria: str = "",
    etapa: str = "",
    situacao: str = "",  # compatibilidade com URLs antigas
    busca: str = "",
):
    etapa = etapa or situacao
    importacao = (
        ImportacaoCronogramaSuprimentos.objects
        .filter(
            ativa=True,
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        .select_related("executado_por")
        .first()
    )

    vazio = {
        "importacao_ativa": None,
        "obras": [],
        "cronograma_obra": None,
        "categorias": [],
        "categorias_filtro": [],
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": {
            "total": 0,
            "concluidos": 0,
            "em_andamento": 0,
            "nao_iniciados": 0,
            "atrasados": 0,
            "filtrados": 0,
            "percentual_medio": 0,
        },
        "filtros": {
            "categoria": categoria,
            "etapa": etapa,
            "busca": busca,
        },
    }
    if not importacao:
        return vazio

    obras = list(
        importacao.obras_importadas
        .select_related("obra")
        .order_by("ordem_aba", "nome_aba")
    )

    selecionado = None
    if obra_id:
        selecionado = next(
            (x for x in obras if str(x.obra_id) == str(obra_id)),
            None,
        )
    if selecionado is None and obras:
        selecionado = obras[0]

    grupos = []
    categorias_filtro = []
    resumo = vazio["resumo"].copy()

    if selecionado:
        hoje = timezone.localdate()
        todos_itens = [
            _decorar_item(item, hoje)
            for item in selecionado.itens.all().order_by("ordem", "id")
        ]

        categorias_filtro = sorted(
            {x.categoria for x in todos_itens if x.categoria},
            key=str.casefold,
        )

        resumo["total"] = len(todos_itens)
        resumo["concluidos"] = sum(
            1 for x in todos_itens if x.etapa_atual == ItemCronogramaSuprimento.Etapa.CONCLUIDO
        )
        resumo["nao_iniciados"] = sum(1 for x in todos_itens if x.percentual_andamento == 0)
        resumo["em_andamento"] = sum(1 for x in todos_itens if 0 < x.percentual_andamento < 100)
        resumo["atrasados"] = sum(1 for x in todos_itens if x.atrasado_calculado)
        if todos_itens:
            resumo["percentual_medio"] = round(
                sum(x.percentual_andamento for x in todos_itens) / len(todos_itens)
            )

        itens = todos_itens
        if categoria:
            itens = [x for x in itens if x.categoria == categoria]
        if etapa:
            itens = _filtrar_por_etapa(itens, etapa)
        if busca:
            termo = busca.casefold()
            itens = [
                x for x in itens
                if termo in (x.item or "").casefold()
                or termo in (x.local or "").casefold()
                or termo in (x.contratada_responsavel or "").casefold()
            ]

        resumo["filtrados"] = len(itens)

        mapa = {}
        for item in itens:
            nome_categoria = item.categoria or "SEM CATEGORIA"
            mapa.setdefault(nome_categoria, []).append(item)

        grupos = [
            {"nome": nome, "itens": itens_categoria}
            for nome, itens_categoria in mapa.items()
        ]

    return {
        "importacao_ativa": importacao,
        "obras": obras,
        "cronograma_obra": selecionado,
        "categorias": grupos,
        "categorias_filtro": categorias_filtro,
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": resumo,
        "filtros": {
            "categoria": categoria,
            "etapa": etapa,
            "busca": busca,
        },
    }
