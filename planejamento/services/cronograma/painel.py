from __future__ import annotations

from collections import Counter

from .agenda_semanal import obter_programacao_semana
from .atividades import listar_atividades, obter_atividades_prioritarias, resumir_atividades
from .checklists import obter_checklists
from .consultas import (
    listar_projetos_ativos,
    listar_semanas_ativas,
    listar_semanas_com_resumo_geral,
    obter_importacao_ativa,
    obter_ultima_semana_valida,
    usar_importacao_ativa,
)
from .marcos import obter_marcos
from .disciplinas import obter_disciplinas
from .operacional import obter_operacional
from .prazos import calcular_indicadores_prazo
from .resumo_geral import (
    calcular_avancos_mensais,
    calcular_avancos_semanais,
    calcular_media_avancos,
    obter_resumo_geral,
    obter_serie_resumo_geral,
)


def _formatar_intervalos_semanais(avancos, serie):
    ocorrencias = Counter(item["inicio_semana"] for item in serie)
    semana_anterior = None
    for item in avancos:
        inicio, fim = item["inicio_semana"], item["fim_semana"]
        if inicio and fim and ocorrencias[inicio] == 1:
            item["rotulo_intervalo"] = f"{inicio:%d/%m} – {fim:%d/%m}"
            item["intervalo_completo"] = f"{inicio:%d/%m/%Y} – {fim:%d/%m/%Y}"
        else:
            item["rotulo_intervalo"] = ""
            item["intervalo_completo"] = ""
        item["base_acumulada"] = semana_anterior is None
        item["intervalo_entre_medicoes"] = semana_anterior is not None and item["semana"] != semana_anterior + 1
        semana_anterior = item["semana"]


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
        "avancos_mensais": [],
        "periodo_semana": None,
        "ultima_medicao": None,
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
    aba=None,
):
    """
    Monta o contexto da aba reutilizando a importação já resolvida.

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
    contexto["aba"] = aba

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

    contexto["resumo"] = resumo
    if aba in (None, "visao-geral", "semanal", "mensal", "indicadores", "importacao"):
        serie = obter_serie_resumo_geral(projeto=projeto)
        contexto["ultima_medicao"] = max(
            (item["data_atualizacao"] for item in serie if item["data_atualizacao"]),
            default=None,
        )
        serie_ate_semana = [item for item in serie if item["semana"] <= semana]
        if aba in (None, "visao-geral"):
            contexto["serie"] = serie_ate_semana
        if aba in (None, "mensal"):
            contexto["avancos_mensais"] = calcular_avancos_mensais(serie_ate_semana)
        if aba != "mensal":
            avancos = calcular_avancos_semanais(serie_ate_semana)
            if aba in (None, "semanal"):
                contexto["avancos"] = avancos
            if aba == "semanal":
                _formatar_intervalos_semanais(avancos, serie)
            if aba != "semanal":
                medias = calcular_media_avancos(avancos)
                contexto["medias"] = medias
                contexto["prazos"] = calcular_indicadores_prazo(
                    resumo=resumo, media_avanco_real=medias["media_real"], avancos=avancos
                )
        if aba is None:
            contexto["periodo_semana"] = next((item for item in serie if item["semana"] == semana), None)

    if aba in (None, "marcos"):
        contexto["marcos"] = obter_marcos(projeto=projeto, semana=semana)
    if aba is None:
        contexto.update(obter_operacional(projeto=projeto, semana=semana))
    elif aba == "programacao":
        programacao = obter_programacao_semana(projeto=projeto, semana=semana)
        contexto["programacao_semana"] = programacao
        contexto["resumo_prioridades"] = programacao["resumo"]
    elif aba in ("indicadores", "disciplinas", "checklists"):
        atividades = listar_atividades(projeto=projeto, semana=semana)
        if aba == "indicadores":
            contexto["contadores_atividades"] = resumir_atividades(atividades)
            contexto["atividades_prioritarias"] = obter_atividades_prioritarias(atividades=atividades)
        elif aba == "disciplinas":
            contexto["disciplinas"] = obter_disciplinas(atividades=atividades)
        else:
            contexto["checklists"] = obter_checklists(atividades=atividades)

    return contexto


def montar_painel_cronograma(
    *,
    projeto=None,
    semana=None,
    aba=None,
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
            aba=aba,
        )
