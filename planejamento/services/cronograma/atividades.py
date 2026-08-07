from __future__ import annotations

from datetime import date
from typing import Any

from .consultas import (
    decimal_para_float,
    eh_linha_estrutural,
    formatar_data,
    queryset_ativo,
)


TOLERANCIA_PERCENTUAL = 0.001


def _percentual_executado(registro: dict[str, Any]) -> float:
    valor = registro.get("percentual_concluida")
    if valor is None:
        valor = registro.get("percentual_executado")
    return decimal_para_float(valor)


def _percentual_previsto(registro: dict[str, Any]) -> float:
    valor = registro.get("percentual_previsto_tarefa")
    if valor is None:
        valor = registro.get("percentual_previsto")
    return decimal_para_float(valor)


def _dias_atraso(*, termino_base: date | None, data_atualizacao: date | None, concluida: bool) -> int:
    if concluida or not termino_base or not data_atualizacao:
        return 0
    return max((data_atualizacao - termino_base).days, 0)


def _status_atividade(
    *,
    executado: float,
    previsto: float,
    inicio_base: date | None,
    termino_base: date | None,
    data_atualizacao: date | None,
) -> tuple[str, str, int, str]:
    """
    Ordem funcional das regras:
    - concluída sempre prevalece;
    - término vencido é atraso real;
    - atividade que já deveria ter iniciado e continua zerada é PARA_INICIAR;
    - atividade com planejamento praticamente em 100%, iniciada e ainda não
      vencida, é PARA_CONCLUIR;
    - depois avaliamos atraso físico por executado abaixo do previsto.
    """
    concluida = executado >= (1 - TOLERANCIA_PERCENTUAL)
    if concluida:
        return "CONCLUIDA", "Concluída", 6, "concluida"

    termino_ultrapassado = bool(
        termino_base
        and data_atualizacao
        and termino_base < data_atualizacao
    )
    if termino_ultrapassado:
        return "ATRASADA", "Término previsto ultrapassado", 1, "atrasada"

    inicio_alcancado_sem_execucao = bool(
        inicio_base
        and data_atualizacao
        and inicio_base <= data_atualizacao
        and executado <= TOLERANCIA_PERCENTUAL
    )
    if inicio_alcancado_sem_execucao:
        return "PARA_INICIAR", "Deveria ter sido iniciada", 2, "para-iniciar"

    prevista_para_conclusao = previsto >= (1 - TOLERANCIA_PERCENTUAL)
    if prevista_para_conclusao:
        return "PARA_CONCLUIR", "Prevista para conclusão", 3, "para-concluir"

    abaixo_previsto = executado + TOLERANCIA_PERCENTUAL < previsto
    if abaixo_previsto:
        return "ATRASADA", "Executado abaixo do previsto", 1, "atrasada"

    if executado > TOLERANCIA_PERCENTUAL:
        return "EM_ANDAMENTO", "Em andamento", 4, "andamento"

    return "PLANEJADA", "Planejada", 5, "planejada"


def listar_atividades(*, projeto: str, semana: int) -> list[dict[str, Any]]:
    registros = list(
        queryset_ativo(projeto=projeto, semana=semana)
        .values(
            "id",
            "obra_id",
            "atividade_planejamento_id",
            "chave_atividade",
            "disciplina",
            "local_tarefa",
            "nome_tarefa",
            "responsavel",
            "peso",
            "inicio_base",
            "termino_base",
            "inicio_real",
            "termino_real",
            "inicio_base_anterior",
            "termino_base_anterior",
            "reprogramada",
            "reprogramada_em",
            "data_atualizacao",
            "percentual_concluida",
            "percentual_previsto_tarefa",
            "percentual_executado",
            "percentual_previsto",
            "checklist_habitese",
            "checklist_cef",
        )
        .order_by("disciplina", "local_tarefa", "nome_tarefa", "id")
    )

    atividades: list[dict[str, Any]] = []
    for registro in registros:
        disciplina = (registro.get("disciplina") or "").strip()
        atividade = (registro.get("nome_tarefa") or "").strip()
        if not disciplina or eh_linha_estrutural(disciplina) or not atividade:
            continue

        executado = _percentual_executado(registro)
        previsto = _percentual_previsto(registro)
        situacao, rotulo, ordem, css = _status_atividade(
            executado=executado,
            previsto=previsto,
            inicio_base=registro.get("inicio_base"),
            termino_base=registro.get("termino_base"),
            data_atualizacao=registro.get("data_atualizacao"),
        )
        concluida = situacao == "CONCLUIDA"

        atividades.append({
            "id": registro["id"],
            "obra_id": registro.get("obra_id"),
            "atividade_planejamento_id": registro.get("atividade_planejamento_id"),
            "chave_atividade": registro.get("chave_atividade") or "",
            "atividade": atividade,
            "disciplina": disciplina,
            "local": (registro.get("local_tarefa") or "Local não informado").strip(),
            "responsavel": (registro.get("responsavel") or "Não informado").strip(),
            "peso": decimal_para_float(registro.get("peso")),
            "planejado": previsto,
            "realizado": executado,
            "diferenca": executado - previsto,
            "situacao": situacao,
            "situacao_rotulo": rotulo,
            "situacao_css": css,
            "ordem_situacao": ordem,
            "dias_atraso": _dias_atraso(
                termino_base=registro.get("termino_base"),
                data_atualizacao=registro.get("data_atualizacao"),
                concluida=concluida,
            ),
            "requer_atencao": situacao in {"ATRASADA", "PARA_INICIAR", "PARA_CONCLUIR"},
            "inicio_base_data": registro.get("inicio_base"),
            "termino_base_data": registro.get("termino_base"),
            "inicio_real_data": registro.get("inicio_real"),
            "termino_real_data": registro.get("termino_real"),
            "inicio_base_anterior_data": registro.get("inicio_base_anterior"),
            "termino_base_anterior_data": registro.get("termino_base_anterior"),
            "data_referencia": registro.get("data_atualizacao"),
            "inicio_base": formatar_data(registro.get("inicio_base")),
            "termino_base": formatar_data(registro.get("termino_base")),
            "inicio_real": formatar_data(registro.get("inicio_real")),
            "termino_real": formatar_data(registro.get("termino_real")),
            "inicio_base_anterior": formatar_data(registro.get("inicio_base_anterior")),
            "termino_base_anterior": formatar_data(registro.get("termino_base_anterior")),
            "data_atualizacao": formatar_data(registro.get("data_atualizacao")),
            "reprogramada": bool(registro.get("reprogramada")),
            "reprogramada_em": registro.get("reprogramada_em"),
            "checklist_habitese": (registro.get("checklist_habitese") or "").strip(),
            "checklist_cef": (registro.get("checklist_cef") or "").strip(),
        })

    return atividades


def resumir_atividades(atividades: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(atividades),
        "atrasadas": sum(1 for item in atividades if item["situacao"] == "ATRASADA"),
        "para_iniciar": sum(1 for item in atividades if item["situacao"] == "PARA_INICIAR"),
        "para_concluir": sum(1 for item in atividades if item["situacao"] == "PARA_CONCLUIR"),
        "em_andamento": sum(1 for item in atividades if item["situacao"] == "EM_ANDAMENTO"),
        "concluidas": sum(1 for item in atividades if item["situacao"] == "CONCLUIDA"),
        "planejadas": sum(1 for item in atividades if item["situacao"] == "PLANEJADA"),
        "reprogramadas": sum(1 for item in atividades if item["reprogramada"]),
    }


def obter_atividades_prioritarias(
    *,
    projeto: str | None = None,
    semana: int | None = None,
    atividades: list[dict[str, Any]] | None = None,
    limite: int = 15,
) -> list[dict[str, Any]]:
    if atividades is None:
        if projeto is None or semana is None:
            raise ValueError("Informe atividades ou projeto e semana.")
        atividades = listar_atividades(projeto=projeto, semana=semana)

    candidatas = [item for item in atividades if item["requer_atencao"]]
    candidatas.sort(
        key=lambda item: (
            item["ordem_situacao"],
            -item["dias_atraso"],
            item["diferenca"],
            -item["peso"],
            item["termino_base_data"] or date.max,
            item["disciplina"].upper(),
            item["atividade"].upper(),
        )
    )
    return candidatas[:limite]
