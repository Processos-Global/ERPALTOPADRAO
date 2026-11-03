from __future__ import annotations

import unicodedata
from decimal import Decimal

from orcamento.models import InsumoOrcamento


def _partes_codigo(codigo: str) -> list[str]:
    return [parte.strip() for parte in str(codigo or "").split(".") if parte.strip()]


def _normalizar_busca(texto: str) -> str:
    texto = str(texto or "").strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return texto


def _no_vazio(insumo: InsumoOrcamento | None, codigo: str, nivel: int) -> dict:
    descricao = insumo.descricao if insumo else f"(sem cadastro: {codigo})"
    return {
        "id": insumo.id if insumo else None,
        "codigo": codigo,
        "nivel": nivel,
        "tipo": insumo.tipo if insumo else "F",
        "descricao": descricao,
        "unid": insumo.unid if insumo else "",
        "quant": float(insumo.quant) if insumo and insumo.quant is not None else 0.0,
        "custo": float(insumo.custo) if insumo and insumo.custo is not None else 0.0,
        "total": float(insumo.total) if insumo and insumo.total is not None else 0.0,
        "mao_de_obra": bool(insumo.mao_de_obra) if insumo else False,
        "eh_servico_final": bool(insumo and insumo.tipo == InsumoOrcamento.Tipo.INSUMO),
        "placeholder": insumo is None,
        "busca": _normalizar_busca(f"{codigo} {descricao}"),
        "filhos": [],
    }


def _obter_ou_criar_no(codigo: str, tree: dict, raizes: list, insumos_por_codigo: dict) -> dict:
    existente = tree.get(codigo)
    if existente:
        return existente

    partes = _partes_codigo(codigo)
    no = _no_vazio(insumos_por_codigo.get(codigo), codigo, len(partes))
    tree[codigo] = no

    if len(partes) <= 1:
        raizes.append(no)
        return no

    codigo_pai = ".".join(partes[:-1])
    pai = _obter_ou_criar_no(codigo_pai, tree, raizes, insumos_por_codigo)
    pai["filhos"].append(no)
    return no


def _remover_galhos_sem_servico(no: dict) -> bool:
    filhos_validos = [
        filho for filho in no["filhos"] if _remover_galhos_sem_servico(filho)
    ]
    no["filhos"] = filhos_validos

    if no["eh_servico_final"]:
        return True

    return bool(filhos_validos)


def _recalcular_totais(no: dict) -> None:
    if no["eh_servico_final"]:
        return

    total = 0.0
    for filho in no["filhos"]:
        _recalcular_totais(filho)
        total += filho["total"]

    no["total"] = total


def montar_arvore_orcamento(obra) -> dict:
    """
    Monta a árvore de fases/serviços do orçamento a partir de InsumoOrcamento.

    Sem integração com contratos/medições ainda: gasto, contratado e
    progresso não existem nesta versão (ficam para quando o app orcamento
    ganhar essa integração).
    """
    insumos = list(
        InsumoOrcamento.objects.filter(obra=obra).exclude(codigo="").order_by("codigo")
    )

    insumos_por_codigo = {insumo.codigo: insumo for insumo in insumos}

    tree: dict[str, dict] = {}
    raizes: list[dict] = []

    for insumo in insumos:
        codigo = insumo.codigo
        if codigo in tree:
            continue

        partes = _partes_codigo(codigo)
        no = _no_vazio(insumo, codigo, len(partes))
        tree[codigo] = no

        if len(partes) <= 1:
            raizes.append(no)
            continue

        codigo_pai = ".".join(partes[:-1])
        pai = _obter_ou_criar_no(codigo_pai, tree, raizes, insumos_por_codigo)
        pai["filhos"].append(no)

    raizes = [fase for fase in raizes if _remover_galhos_sem_servico(fase)]

    for fase in raizes:
        _recalcular_totais(fase)

    valor_total = float(
        sum(
            insumo.total or Decimal("0")
            for insumo in insumos
            if insumo.tipo == InsumoOrcamento.Tipo.INSUMO
        )
    )

    valor_mao_de_obra = sum(
        insumo.total or Decimal("0")
        for insumo in insumos
        if insumo.tipo == InsumoOrcamento.Tipo.INSUMO and insumo.mao_de_obra
    )

    return {
        "fases": raizes,
        "valor_total": valor_total,
        "valor_mao_de_obra": float(valor_mao_de_obra),
        "quantidade_insumos": sum(
            1 for insumo in insumos if insumo.tipo == InsumoOrcamento.Tipo.INSUMO
        ),
    }
