from __future__ import annotations

from typing import Any

from .atividades import listar_atividades
from .consultas import listar_semanas_ativas


TOLERANCIA_PERCENTUAL = 0.001


def _chave_atividade(item: dict[str, Any]):
    permanente = item.get("atividade_planejamento_id")
    if permanente:
        return ("atividade_planejamento", permanente)
    chave = item.get("chave_atividade")
    if chave:
        return ("chave", chave)
    return (
        "texto",
        item["disciplina"].strip().upper(),
        item["local"].strip().upper(),
        item["atividade"].strip().upper(),
    )


def obter_semana_anterior(*, projeto: str, semana: int) -> int | None:
    anteriores = [
        valor
        for valor in listar_semanas_ativas(projeto=projeto)
        if valor < semana
    ]
    return max(anteriores) if anteriores else None


def _categoria_resumo(
    *,
    atividade: dict[str, Any],
    planejado_semana: float,
    realizado_semana: float,
) -> tuple[str, str, int]:
    if atividade["situacao"] == "CONCLUIDA":
        return "CONCLUIDA", "Concluídas", 4
    if atividade["situacao"] == "ATRASADA":
        return "ATRASADA", "Atrasadas", 1
    if atividade["situacao"] == "PARA_INICIAR":
        return "PARA_INICIAR", "Para iniciar", 3
    if atividade["situacao"] == "PARA_CONCLUIR":
        return "EM_ANDAMENTO", "Em andamento", 2
    if (
        atividade["realizado"] > TOLERANCIA_PERCENTUAL
        or realizado_semana > TOLERANCIA_PERCENTUAL
    ):
        return "EM_ANDAMENTO", "Em andamento", 2
    if planejado_semana > TOLERANCIA_PERCENTUAL:
        return "PARA_INICIAR", "Para iniciar", 3
    return "PARA_INICIAR", "Para iniciar", 3


def resumir_programacao(programacao: list[dict[str, Any]]) -> dict[str, Any]:
    categorias = (
        ("ATRASADA", "Atrasadas", "atrasadas"),
        ("EM_ANDAMENTO", "Em andamento", "em_andamento"),
        ("PARA_INICIAR", "Para iniciar", "para_iniciar"),
        ("CONCLUIDA", "Concluídas", "concluidas"),
    )
    contagens = {
        chave: sum(1 for item in programacao if item["categoria_resumo"] == codigo)
        for codigo, _, chave in categorias
    }
    return {
        "total": len(programacao),
        **contagens,
        "itens": [
            {
                "codigo": codigo,
                "rotulo": rotulo,
                "quantidade": contagens[chave],
                "chave": chave,
            }
            for codigo, rotulo, chave in categorias
        ],
    }


def obter_programacao_semana(
    *,
    projeto: str,
    semana: int,
    limite: int = 100,
    atividades_atuais: list[dict[str, Any]] | None = None,
    atividades_anteriores: list[dict[str, Any]] | None = None,
    semana_anterior: int | None = None,
) -> dict[str, Any]:
    if semana_anterior is None:
        semana_anterior = obter_semana_anterior(projeto=projeto, semana=semana)

    atuais = atividades_atuais
    if atuais is None:
        atuais = listar_atividades(projeto=projeto, semana=semana)

    anteriores = atividades_anteriores
    if anteriores is None:
        anteriores = (
            listar_atividades(projeto=projeto, semana=semana_anterior)
            if semana_anterior is not None
            else []
        )

    anteriores_por_chave = {_chave_atividade(item): item for item in anteriores}
    programacao: list[dict[str, Any]] = []

    for atual in atuais:
        anterior = anteriores_por_chave.get(_chave_atividade(atual))
        planejado_anterior = float(anterior["planejado"]) if anterior else 0.0
        realizado_anterior = float(anterior["realizado"]) if anterior else 0.0

        planejado_semana = max(float(atual["planejado"]) - planejado_anterior, 0.0)
        realizado_semana = max(float(atual["realizado"]) - realizado_anterior, 0.0)

        tem_movimento = (
            planejado_semana > TOLERANCIA_PERCENTUAL
            or realizado_semana > TOLERANCIA_PERCENTUAL
        )

        data_referencia = atual.get("data_referencia")
        datas_no_periodo = False
        for campo in (
            "inicio_base_data",
            "termino_base_data",
            "inicio_real_data",
            "termino_real_data",
        ):
            valor = atual.get(campo)
            if valor and data_referencia and valor <= data_referencia:
                if anterior is None or (
                    anterior.get("data_referencia")
                    and valor > anterior["data_referencia"]
                ):
                    datas_no_periodo = True
                    break

        if not tem_movimento and not datas_no_periodo:
            continue

        categoria, categoria_rotulo, ordem = _categoria_resumo(
            atividade=atual,
            planejado_semana=planejado_semana,
            realizado_semana=realizado_semana,
        )
        programacao.append({
            **atual,
            "semana_anterior": semana_anterior,
            "planejado_semana": planejado_semana,
            "realizado_semana": realizado_semana,
            "diferenca_semana": realizado_semana - planejado_semana,
            "categoria_resumo": categoria,
            "categoria_resumo_rotulo": categoria_rotulo,
            "ordem_programacao": ordem,
        })

    programacao.sort(
        key=lambda item: (
            item["ordem_programacao"],
            item["disciplina"].upper(),
            item["local"].upper(),
            item["atividade"].upper(),
        )
    )

    # O resumo é calculado sobre o universo completo. O limite afeta somente
    # os itens enviados à tabela do painel.
    resumo = resumir_programacao(programacao)
    atividades_exibidas = programacao[:limite]

    return {
        "semana": semana,
        "semana_anterior": semana_anterior,
        "atividades": atividades_exibidas,
        "resumo": resumo,
        "total_exibido": len(atividades_exibidas),
        "limitado": len(programacao) > limite,
    }
