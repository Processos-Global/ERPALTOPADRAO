from __future__ import annotations

from .agenda_semanal import obter_semana_anterior
from .atividades import listar_atividades
from .consultas import (
    listar_projetos_ativos,
    listar_semanas_ativas,
    listar_semanas_com_resumo_geral,
    obter_importacao_ativa,
    obter_ultima_semana_valida,
    usar_importacao_ativa,
)
from .marcos import obter_marcos
from .operacional import obter_operacional
from .prazos import calcular_indicadores_prazo
from .resumo_geral import (
    calcular_avancos_semanais,
    calcular_media_avancos,
    obter_resumo_geral,
    obter_serie_resumo_geral,
)


def _contexto_base(
    *,
    projetos,
    projeto,
    semanas,
    semana,
):
    return {
        "projetos": projetos,
        "projeto_selecionado": projeto,
        "semanas": semanas,
        "semana_selecionada": semana,
        "possui_dados": bool(
            projeto and semana is not None
        ),
        "resumo": None,
        "serie": [],
        "avancos": [],
        "medias": None,
        "prazos": None,
        "marcos": [],
        "contadores_atividades": {},
        "atividades_prioritarias": [],
        "programacao_semana": {},
        "resumo_prioridades": {},
        "disciplinas": [],
        "checklists": {
            "habitese": {},
            "cef": {},
        },
        "alertas_painel": [],
        "erro_base": None,
        "importacao_ativa": None,
    }


def _montar_painel_com_importacao(
    *,
    projeto=None,
    semana=None,
    importacao,
):
    """
    Monta todo o painel reutilizando a importação já resolvida.

    Como esta função é chamada dentro de usar_importacao_ativa(), todas
    as funções que internamente usam queryset_ativo() deixam de consultar
    ImportacaoCronograma repetidamente.
    """
    projetos = listar_projetos_ativos()

    if not projeto or projeto not in projetos:
        projeto = projetos[0] if projetos else None

    semanas = (
        listar_semanas_ativas(projeto=projeto)
        if projeto
        else []
    )

    semanas_com_resumo = (
        listar_semanas_com_resumo_geral(
            projeto=projeto
        )
        if projeto
        else []
    )

    semana_solicitada = semana

    if semana not in semanas:
        semana = semanas[-1] if semanas else None

    contexto = _contexto_base(
        projetos=projetos,
        projeto=projeto,
        semanas=semanas,
        semana=semana,
    )

    contexto["semana_solicitada"] = semana_solicitada
    contexto["importacao_ativa"] = importacao

    if not contexto["possui_dados"]:
        return contexto

    # Uma semana pode existir nas atividades e estar inconsistente por
    # não ter RESUMO GERAL. Nesse caso recuamos para a última semana
    # válida e mantemos o painel funcional.
    if semana not in semanas_com_resumo:
        fallback = obter_ultima_semana_valida(
            projeto=projeto,
            ate_semana=semana,
        )

        if fallback is None and semanas_com_resumo:
            fallback = semanas_com_resumo[-1]

        if fallback is None:
            contexto["possui_dados"] = False
            contexto["alertas_painel"].append(
                f"O projeto {projeto} não possui nenhuma semana "
                "com RESUMO GERAL."
            )
            return contexto

        contexto["alertas_painel"].append(
            f"A semana {semana} não possui RESUMO GERAL. "
            f"Exibindo a semana {fallback}."
        )

        semana = fallback
        contexto["semana_selecionada"] = semana

    resumo = obter_resumo_geral(
        projeto=projeto,
        semana=semana,
    )

    if resumo is None:
        contexto["possui_dados"] = False
        contexto["alertas_painel"].append(
            f"Não foi possível montar o resumo do projeto "
            f"{projeto}, semana {semana}."
        )
        return contexto

    serie = obter_serie_resumo_geral(
        projeto=projeto
    )

    avancos = calcular_avancos_semanais(serie)

    avancos_ate_semana = [
        item
        for item in avancos
        if item["semana"] <= semana
    ]

    medias = calcular_media_avancos(
        avancos_ate_semana
    )

    prazos = calcular_indicadores_prazo(
        resumo=resumo,
        media_avanco_real=medias["media_real"],
    )

    # Apenas duas consultas de atividades:
    # 1. semana atual;
    # 2. semana anterior.
    atividades_atuais = listar_atividades(
        projeto=projeto,
        semana=semana,
    )

    semana_anterior = obter_semana_anterior(
        projeto=projeto,
        semana=semana,
    )

    atividades_anteriores = (
        listar_atividades(
            projeto=projeto,
            semana=semana_anterior,
        )
        if semana_anterior is not None
        else []
    )

    operacional = obter_operacional(
        projeto=projeto,
        semana=semana,
        atividades_atuais=atividades_atuais,
        atividades_anteriores=atividades_anteriores,
        semana_anterior=semana_anterior,
    )

    contexto.update(
        {
            "resumo": resumo,
            "serie": serie,
            "avancos": avancos_ate_semana,
            "medias": medias,
            "prazos": prazos,
            "marcos": obter_marcos(
                projeto=projeto,
                semana=semana,
            ),
            **operacional,
        }
    )

    return contexto


def montar_painel_cronograma(
    *,
    projeto=None,
    semana=None,
):
    """
    Busca a importação ativa uma única vez e mantém esse snapshot lógico
    durante toda a montagem do painel.
    """
    importacao = obter_importacao_ativa()

    with usar_importacao_ativa(importacao):
        return _montar_painel_com_importacao(
            projeto=projeto,
            semana=semana,
            importacao=importacao,
        )
