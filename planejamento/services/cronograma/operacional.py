from __future__ import annotations

from typing import Any

from .agenda_semanal import obter_programacao_semana, obter_semana_anterior
from .atividades import listar_atividades, obter_atividades_prioritarias, resumir_atividades
from .checklists import obter_checklists
from .disciplinas import obter_disciplinas


def obter_operacional(
    *,
    projeto: str,
    semana: int,
    atividades_atuais: list[dict[str, Any]] | None = None,
    atividades_anteriores: list[dict[str, Any]] | None = None,
    semana_anterior: int | None = None,
) -> dict[str, Any]:
    atividades = atividades_atuais
    if atividades is None:
        atividades = listar_atividades(projeto=projeto, semana=semana)

    if semana_anterior is None:
        semana_anterior = obter_semana_anterior(projeto=projeto, semana=semana)

    anteriores = atividades_anteriores
    if anteriores is None:
        anteriores = (
            listar_atividades(projeto=projeto, semana=semana_anterior)
            if semana_anterior is not None
            else []
        )

    programacao = obter_programacao_semana(
        projeto=projeto,
        semana=semana,
        atividades_atuais=atividades,
        atividades_anteriores=anteriores,
        semana_anterior=semana_anterior,
    )

    return {
        "contadores_atividades": resumir_atividades(atividades),
        "atividades_prioritarias": obter_atividades_prioritarias(atividades=atividades),
        "programacao_semana": programacao,
        "resumo_prioridades": programacao["resumo"],
        "disciplinas": obter_disciplinas(atividades=atividades),
        "checklists": obter_checklists(atividades=atividades),
    }
