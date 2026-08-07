from __future__ import annotations

from collections import defaultdict
from typing import Any

from .atividades import listar_atividades


def _media_ponderada(itens: list[dict[str, Any]], campo: str) -> float:
    itens_com_peso = [item for item in itens if float(item.get("peso") or 0.0) > 0]
    if itens_com_peso:
        soma_pesos = sum(float(item["peso"]) for item in itens_com_peso)
        if soma_pesos > 0:
            return sum(
                float(item.get(campo) or 0.0) * float(item["peso"])
                for item in itens_com_peso
            ) / soma_pesos
    if not itens:
        return 0.0
    return sum(float(item.get(campo) or 0.0) for item in itens) / len(itens)


def obter_disciplinas(
    *,
    projeto: str | None = None,
    semana: int | None = None,
    atividades: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if atividades is None:
        if projeto is None or semana is None:
            raise ValueError("Informe atividades ou projeto e semana.")
        atividades = listar_atividades(projeto=projeto, semana=semana)

    por_disciplina: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atividade in atividades:
        por_disciplina[atividade["disciplina"]].append(atividade)

    disciplinas: list[dict[str, Any]] = []
    for nome_disciplina, itens in por_disciplina.items():
        locais_brutos: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in itens:
            locais_brutos[item["local"]].append(item)

        locais = []
        for nome_local, atividades_local in locais_brutos.items():
            realizado_local = _media_ponderada(atividades_local, "realizado")
            previsto_local = _media_ponderada(atividades_local, "planejado")
            locais.append({
                "nome": nome_local,
                "total": len(atividades_local),
                "realizado": realizado_local,
                "planejado": previsto_local,
                "diferenca": realizado_local - previsto_local,
                "atividades": sorted(
                    atividades_local,
                    key=lambda item: (item["ordem_situacao"], item["atividade"].upper()),
                ),
            })
        locais.sort(key=lambda item: item["nome"].upper())

        realizado = _media_ponderada(itens, "realizado")
        previsto = _media_ponderada(itens, "planejado")
        atrasadas = sum(1 for item in itens if item["situacao"] == "ATRASADA")
        em_andamento = sum(1 for item in itens if item["situacao"] == "EM_ANDAMENTO")
        concluidas = sum(1 for item in itens if item["situacao"] == "CONCLUIDA")
        para_iniciar = sum(1 for item in itens if item["situacao"] == "PARA_INICIAR")
        para_concluir = sum(1 for item in itens if item["situacao"] == "PARA_CONCLUIR")

        if atrasadas:
            situacao, situacao_rotulo, situacao_css = "ATENCAO", "Atenção", "atencao"
        elif concluidas == len(itens):
            situacao, situacao_rotulo, situacao_css = "CONCLUIDA", "Concluída", "concluida"
        elif em_andamento or para_concluir or realizado > 0:
            situacao, situacao_rotulo, situacao_css = "EM_ANDAMENTO", "Em andamento", "andamento"
        else:
            situacao, situacao_rotulo, situacao_css = "PLANEJADA", "Planejada", "planejada"

        disciplinas.append({
            "nome": nome_disciplina,
            "total": len(itens),
            "total_locais": len(locais),
            "realizado": realizado,
            "planejado": previsto,
            "diferenca": realizado - previsto,
            "atrasadas": atrasadas,
            "em_andamento": em_andamento,
            "concluidas": concluidas,
            "para_iniciar": para_iniciar,
            "para_concluir": para_concluir,
            "situacao": situacao,
            "situacao_rotulo": situacao_rotulo,
            "situacao_css": situacao_css,
            "locais": locais,
        })

    ordem = {"ATENCAO": 1, "EM_ANDAMENTO": 2, "PLANEJADA": 3, "CONCLUIDA": 4}
    disciplinas.sort(
        key=lambda item: (
            ordem.get(item["situacao"], 9),
            -item["atrasadas"],
            item["nome"].upper(),
        )
    )
    return disciplinas
