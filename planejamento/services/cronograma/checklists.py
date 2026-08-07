from __future__ import annotations

from collections import defaultdict
from typing import Any

from .atividades import listar_atividades
from .consultas import normalizar_texto


DISCIPLINAS_HABITESE = {
    "CHECKLIST HABITE-SE",
    "CHECKLIST PRE HABITE-SE",
}
DISCIPLINA_POS_HABITESE = "POS HABITE-SE"


def _situacao_item(
    *,
    planejado: float,
    realizado: float,
) -> tuple[str, str, str]:
    if realizado >= 0.999:
        return "CONCLUIDO", "Concluído", "concluido"

    if realizado + 0.001 < planejado:
        return "ATRASADO", "Em atraso", "atrasado"

    if realizado > 0.001:
        return "EM_ANDAMENTO", "Em andamento", "andamento"

    return "NAO_INICIADO", "Não iniciado", "nao-iniciado"


def _montar_checklist(
    *,
    atividades: list[dict[str, Any]],
    titulo: str,
    disciplinas_permitidas: set[str],
) -> dict[str, Any]:
    """
    Monta checklist somente a partir das linhas específicas do cronograma.

    Alto Padrão:
    - Habite-se: DISCIPLINA = CHECKLIST HABITE-SE /
      CHECKLIST PRÉ HABITE-SE.
    - Pós Habite-se: DISCIPLINA = PÓS HABITE-SE.

    O agrupamento usa LOCAL DA TAREFA, que no arquivo já representa
    a área/bloco do checklist.
    """
    grupos_brutos: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for atividade in atividades:
        disciplina = normalizar_texto(
            atividade.get("disciplina")
        )

        if disciplina not in disciplinas_permitidas:
            continue

        nome_grupo = (
            atividade.get("local")
            or "Sem local informado"
        ).strip()

        situacao, rotulo, css = _situacao_item(
            planejado=float(
                atividade.get("planejado") or 0.0
            ),
            realizado=float(
                atividade.get("realizado") or 0.0
            ),
        )

        grupos_brutos[nome_grupo].append(
            {
                **atividade,
                "situacao_checklist": situacao,
                "situacao_checklist_rotulo": rotulo,
                "situacao_checklist_css": css,
            }
        )

    grupos = []
    todos = []

    for nome, itens in grupos_brutos.items():
        todos.extend(itens)
        total = len(itens)

        realizado = (
            sum(
                float(item["realizado"])
                for item in itens
            ) / total
            if total
            else 0.0
        )

        planejado = (
            sum(
                float(item["planejado"])
                for item in itens
            ) / total
            if total
            else 0.0
        )

        concluidos = sum(
            1
            for item in itens
            if item["situacao_checklist"] == "CONCLUIDO"
        )
        atrasados = sum(
            1
            for item in itens
            if item["situacao_checklist"] == "ATRASADO"
        )
        em_andamento = sum(
            1
            for item in itens
            if item["situacao_checklist"] == "EM_ANDAMENTO"
        )
        nao_iniciados = sum(
            1
            for item in itens
            if item["situacao_checklist"] == "NAO_INICIADO"
        )

        if atrasados:
            situacao = "ATENCAO"
            situacao_rotulo = "Atenção"
            situacao_css = "atencao"
        elif total and concluidos == total:
            situacao = "CONCLUIDO"
            situacao_rotulo = "Concluído"
            situacao_css = "concluido"
        elif em_andamento:
            situacao = "EM_ANDAMENTO"
            situacao_rotulo = "Em andamento"
            situacao_css = "andamento"
        else:
            situacao = "NAO_INICIADO"
            situacao_rotulo = "Não iniciado"
            situacao_css = "nao-iniciado"

        grupos.append(
            {
                "nome": nome,
                "total": total,
                "realizado": realizado,
                "planejado": planejado,
                "diferenca": realizado - planejado,
                "concluidos": concluidos,
                "atrasados": atrasados,
                "em_andamento": em_andamento,
                "nao_iniciados": nao_iniciados,
                "situacao": situacao,
                "situacao_rotulo": situacao_rotulo,
                "situacao_css": situacao_css,
                "itens": sorted(
                    itens,
                    key=lambda item: (
                        0
                        if item["situacao_checklist"] == "ATRASADO"
                        else 1,
                        item["atividade"].upper(),
                    ),
                ),
            }
        )

    grupos.sort(
        key=lambda grupo: (
            0 if grupo["situacao"] == "ATENCAO" else 1,
            grupo["nome"].upper(),
        )
    )

    total_itens = len(todos)

    progresso = (
        sum(float(item["realizado"]) for item in todos)
        / total_itens
        if total_itens
        else 0.0
    )

    planejado = (
        sum(float(item["planejado"]) for item in todos)
        / total_itens
        if total_itens
        else 0.0
    )

    return {
        "titulo": titulo,
        "total_grupos": len(grupos),
        "total_itens": total_itens,
        "progresso": progresso,
        "planejado": planejado,
        "diferenca": progresso - planejado,
        "concluidos": sum(
            1
            for item in todos
            if item["situacao_checklist"] == "CONCLUIDO"
        ),
        "atrasados": sum(
            1
            for item in todos
            if item["situacao_checklist"] == "ATRASADO"
        ),
        "grupos": grupos,
    }


def obter_checklists(
    *,
    projeto: str | None = None,
    semana: int | None = None,
    atividades: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Checklists específicos do Alto Padrão.

    Não existe checklist CEF.

    Habite-se:
      somente linhas cuja disciplina é CHECKLIST HABITE-SE
      ou CHECKLIST PRÉ HABITE-SE.

    Pós Habite-se:
      somente linhas cuja disciplina é PÓS HABITE-SE.

    Ambos usam LOCAL DA TAREFA como agrupador.
    """
    itens = atividades

    if itens is None:
        if not projeto or semana is None:
            itens = []
        else:
            itens = listar_atividades(
                projeto=projeto,
                semana=semana,
            )

    return {
        "habitese": _montar_checklist(
            atividades=itens,
            titulo="Checklist Habite-se",
            disciplinas_permitidas=DISCIPLINAS_HABITESE,
        ),
        "pos_habitese": _montar_checklist(
            atividades=itens,
            titulo="Checklist Pós Habite-se",
            disciplinas_permitidas={DISCIPLINA_POS_HABITESE},
        ),
    }
