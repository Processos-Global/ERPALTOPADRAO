from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from planejamento.models.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)
from .painel import _decorar_item


KANBAN_ETAPAS = (
    (ItemCronogramaSuprimento.Etapa.COTACAO, "Cotação"),
    (ItemCronogramaSuprimento.Etapa.COMPATIBILIZACAO, "Compatibilização"),
    (ItemCronogramaSuprimento.Etapa.NEGOCIACAO, "Negociação"),
    (ItemCronogramaSuprimento.Etapa.CONTRATACAO, "Contratação"),
    (ItemCronogramaSuprimento.Etapa.CONCLUIDO, "Concluído"),
)


def montar_kanban_cronograma_suprimentos(*, obra_id=None, busca: str = ""):
    """Monta a visão Kanban do andamento dos suprimentos.

    Sem ``obra_id`` a visão reúne todas as obras da importação ativa. O estágio
    de cada card é derivado das datas realizadas, portanto não existe status
    manual específico para o Kanban.
    """
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
        "colunas": [
            {"codigo": codigo, "titulo": titulo, "itens": [], "quantidade": 0}
            for codigo, titulo in KANBAN_ETAPAS
        ],
        "resumo": {
            "total": 0,
            "atrasados": 0,
            "concluidos": 0,
            "percentual_medio": 0,
        },
        "filtros": {"obra": "", "busca": busca},
    }
    if not importacao:
        return vazio

    obras = list(
        importacao.obras_importadas
        .select_related("obra")
        .order_by("ordem_aba", "nome_aba")
    )

    queryset = (
        ItemCronogramaSuprimento.objects
        .filter(cronograma_obra__importacao=importacao)
        .select_related("cronograma_obra", "cronograma_obra__obra")
        .order_by("cronograma_obra__ordem_aba", "ordem", "id")
    )

    obra_selecionada = None
    if obra_id:
        obra_selecionada = next(
            (registro for registro in obras if str(registro.obra_id) == str(obra_id)),
            None,
        )
        if obra_selecionada is not None:
            queryset = queryset.filter(cronograma_obra=obra_selecionada)

    if busca:
        queryset = queryset.filter(
            Q(item__icontains=busca)
            | Q(local__icontains=busca)
            | Q(categoria__icontains=busca)
            | Q(contratada_responsavel__icontains=busca)
            | Q(cronograma_obra__nome_aba__icontains=busca)
        )

    hoje = timezone.localdate()
    itens = [_decorar_item(item, hoje) for item in queryset]

    mapa_colunas = {codigo: [] for codigo, _ in KANBAN_ETAPAS}
    for item in itens:
        mapa_colunas.setdefault(item.etapa_atual, []).append(item)

    colunas = [
        {
            "codigo": codigo,
            "titulo": titulo,
            "itens": mapa_colunas.get(codigo, []),
            "quantidade": len(mapa_colunas.get(codigo, [])),
        }
        for codigo, titulo in KANBAN_ETAPAS
    ]

    total = len(itens)
    resumo = {
        "total": total,
        "atrasados": sum(1 for item in itens if item.atrasado_calculado),
        "concluidos": sum(
            1
            for item in itens
            if item.etapa_atual == ItemCronogramaSuprimento.Etapa.CONCLUIDO
        ),
        "percentual_medio": (
            round(sum(item.percentual_andamento for item in itens) / total)
            if total
            else 0
        ),
    }

    return {
        "importacao_ativa": importacao,
        "obras": obras,
        "obra_selecionada": obra_selecionada,
        "colunas": colunas,
        "resumo": resumo,
        "filtros": {
            "obra": str(obra_selecionada.obra_id) if obra_selecionada else "",
            "busca": busca,
        },
    }
