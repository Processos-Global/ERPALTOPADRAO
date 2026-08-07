from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from planejamento.models import SuprimentoAtividade


ZERO = Decimal("0")


def _decimal(valor) -> Decimal:
    if valor is None:
        return ZERO
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def _resumo_vazio() -> dict[str, Any]:
    return {
        "valor_total": ZERO,
        "quantidade_insumos": 0,
        "quantidade_atividades": 0,
        "quantidade_atividades_com_suprimentos": 0,
        "quantidade_atividades_sem_suprimentos": 0,
        "disciplinas": [],
        "por_disciplina": {},
        "por_atividade": {},
    }


def obter_orcamento_suprimentos(
    *,
    atividades: list[dict[str, Any]],
) -> dict[str, Any]:
    atividades_validas = [
        item
        for item in atividades
        if item.get("atividade_planejamento_id")
    ]

    if not atividades_validas:
        return _resumo_vazio()

    ids_atividades = {
        item["atividade_planejamento_id"]
        for item in atividades_validas
    }

    suprimentos = list(
        SuprimentoAtividade.objects
        .filter(
            atividade_id__in=ids_atividades,
            ativo=True,
            insumo__ativo=True,
        )
        .select_related("atividade", "insumo")
        .order_by(
            "atividade_id",
            "data_limite_compra",
            "insumo__nome",
            "id",
        )
    )

    suprimentos_por_atividade: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for suprimento in suprimentos:
        quantidade = _decimal(suprimento.quantidade)
        valor_unitario = _decimal(suprimento.valor_unitario)
        valor_total = quantidade * valor_unitario

        suprimentos_por_atividade[suprimento.atividade_id].append(
            {
                "id": suprimento.id,
                "insumo_id": suprimento.insumo_id,
                "insumo": suprimento.insumo.nome,
                "quantidade": quantidade,
                "unidade_medida": suprimento.unidade_medida,
                "unidade_medida_rotulo": suprimento.get_unidade_medida_display(),
                "valor_unitario": valor_unitario,
                "valor_total": valor_total,
                "data_limite_compra": suprimento.data_limite_compra,
                "observacao": suprimento.observacao,
            }
        )

    disciplinas_brutas: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "nome": "",
            "valor_total": ZERO,
            "quantidade_insumos": 0,
            "quantidade_atividades": 0,
            "quantidade_atividades_com_suprimentos": 0,
            "quantidade_atividades_sem_suprimentos": 0,
            "atividades": [],
        }
    )

    por_atividade: dict[int, dict[str, Any]] = {}

    for atividade in atividades_validas:
        atividade_id = int(atividade["atividade_planejamento_id"])
        disciplina = (
            atividade.get("disciplina")
            or "SEM DISCIPLINA"
        ).strip()

        itens = suprimentos_por_atividade.get(atividade_id, [])
        valor_atividade = sum(
            (item["valor_total"] for item in itens),
            ZERO,
        )

        resumo_atividade = {
            "atividade_planejamento_id": atividade_id,
            "atividade": atividade.get("atividade") or "-",
            "local": atividade.get("local") or "-",
            "disciplina": disciplina,
            "responsavel": atividade.get("responsavel") or "-",
            "planejado": atividade.get("planejado") or 0.0,
            "realizado": atividade.get("realizado") or 0.0,
            "situacao": atividade.get("situacao") or "",
            "quantidade_insumos": len(itens),
            "valor_total": valor_atividade,
            "suprimentos": itens,
        }

        por_atividade[atividade_id] = resumo_atividade

        grupo = disciplinas_brutas[disciplina]
        grupo["nome"] = disciplina
        grupo["quantidade_atividades"] += 1
        grupo["quantidade_insumos"] += len(itens)
        grupo["valor_total"] += valor_atividade
        grupo["atividades"].append(resumo_atividade)

        if itens:
            grupo["quantidade_atividades_com_suprimentos"] += 1
        else:
            grupo["quantidade_atividades_sem_suprimentos"] += 1

    disciplinas = list(disciplinas_brutas.values())

    for disciplina in disciplinas:
        disciplina["atividades"].sort(
            key=lambda item: (
                item["atividade"].upper(),
                item["local"].upper(),
            )
        )

    disciplinas.sort(key=lambda item: item["nome"].upper())

    por_disciplina = {
        item["nome"]: item
        for item in disciplinas
    }

    valor_total = sum(
        (item["valor_total"] for item in disciplinas),
        ZERO,
    )

    quantidade_atividades = len(atividades_validas)
    quantidade_com_suprimentos = sum(
        1
        for item in por_atividade.values()
        if item["quantidade_insumos"] > 0
    )

    return {
        "valor_total": valor_total,
        "quantidade_insumos": len(suprimentos),
        "quantidade_atividades": quantidade_atividades,
        "quantidade_atividades_com_suprimentos": quantidade_com_suprimentos,
        "quantidade_atividades_sem_suprimentos": (
            quantidade_atividades - quantidade_com_suprimentos
        ),
        "disciplinas": disciplinas,
        "por_disciplina": por_disciplina,
        "por_atividade": por_atividade,
    }


def enriquecer_disciplinas_com_suprimentos(
    *,
    disciplinas: list[dict[str, Any]],
    orcamento: dict[str, Any],
) -> list[dict[str, Any]]:
    por_disciplina = orcamento.get("por_disciplina", {})
    resultado = []

    for disciplina in disciplinas:
        nome = (
            disciplina.get("nome")
            or disciplina.get("disciplina")
            or ""
        ).strip()

        dados = por_disciplina.get(nome) or {
            "valor_total": ZERO,
            "quantidade_insumos": 0,
            "quantidade_atividades_com_suprimentos": 0,
            "quantidade_atividades_sem_suprimentos": 0,
            "atividades": [],
        }

        resultado.append(
            {
                **disciplina,
                "valor_suprimentos": dados["valor_total"],
                "quantidade_insumos": dados["quantidade_insumos"],
                "atividades_orcadas": dados[
                    "quantidade_atividades_com_suprimentos"
                ],
                "atividades_sem_orcamento": dados[
                    "quantidade_atividades_sem_suprimentos"
                ],
                "suprimentos_atividades": dados["atividades"],
            }
        )

    return resultado
