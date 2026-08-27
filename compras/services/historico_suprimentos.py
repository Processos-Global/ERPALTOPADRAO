from __future__ import annotations

import re
import unicodedata

from django.db import transaction

from compras.models import (
    HistoricoCompraSuprimento,
    PedidoCompra,
    ProcessoCompra,
    SuprimentoReferencia,
)


STATUS_PEDIDOS_CONFIRMADOS = {
    PedidoCompra.Status.CONFIRMADO,
    PedidoCompra.Status.EM_PRODUCAO,
    PedidoCompra.Status.PRONTO_EXPEDICAO,
    PedidoCompra.Status.EM_TRANSPORTE,
    PedidoCompra.Status.ENTREGA_PARCIAL,
    PedidoCompra.Status.ENTREGUE,
}


def normalizar_suprimento(valor) -> str:
    texto = str(valor or "").strip().upper()
    texto = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", texto).strip()


def obter_ou_criar_referencia_suprimento(nome: str) -> SuprimentoReferencia:
    nome = (nome or "").strip()
    chave = normalizar_suprimento(nome)

    referencia, criada = SuprimentoReferencia.objects.get_or_create(
        chave=chave,
        defaults={
            "nome": nome,
            "ativo": True,
        },
    )

    # Mantém a grafia da referência atualizada com o cronograma mais recente.
    alterou = False
    if nome and referencia.nome != nome:
        referencia.nome = nome
        alterou = True
    if not referencia.ativo:
        referencia.ativo = True
        alterou = True
    if alterou:
        referencia.save(update_fields=["nome", "ativo", "atualizado_em"])

    return referencia


def _dados_obra(processo):
    item = processo.item_cronograma
    cronograma_obra = getattr(item, "cronograma_obra", None)

    codigo = ""
    if cronograma_obra is not None:
        codigo = (getattr(cronograma_obra, "codigo_aba", "") or "").strip()

    return {
        "obra": processo.obra,
        "obra_codigo": codigo,
        "obra_nome": str(processo.obra),
    }


@transaction.atomic
def sincronizar_historico_processo(processo: ProcessoCompra):
    """
    Cria/atualiza um registro histórico por pedido confirmado do processo.

    Compras novas do ERP sempre ficam ligadas à referência canônica
    correspondente ao suprimento atual do cronograma.
    """
    p = (
        ProcessoCompra.objects
        .select_for_update()
        .select_related(
            "obra",
            "item_cronograma",
            "item_cronograma__cronograma_obra",
        )
        .get(pk=processo.pk)
    )

    if p.status != ProcessoCompra.Status.CONTRATADO:
        remover_historico_processo(p)
        return []

    item = p.item_cronograma
    suprimento = (item.item or "").strip()
    chave = normalizar_suprimento(suprimento)
    referencia = obter_ou_criar_referencia_suprimento(suprimento)

    data_fechamento = (
        p.data_contratacao_concluida.date()
        if p.data_contratacao_concluida
        else None
    )

    pedidos = list(
        p.pedidos
        .filter(status__in=STATUS_PEDIDOS_CONFIRMADOS)
        .select_related("fornecedor")
        .order_by("id")
    )

    ids_ativos = []
    registros = []
    obra_defaults = _dados_obra(p)

    for pedido in pedidos:
        ids_ativos.append(pedido.pk)

        registro, _ = HistoricoCompraSuprimento.objects.update_or_create(
            pedido=pedido,
            defaults={
                "suprimento": suprimento,
                "suprimento_chave": chave,
                **obra_defaults,
                "fornecedor": pedido.fornecedor,
                "fornecedor_nome": pedido.fornecedor.nome,
                "valor": pedido.valor_total,
                "data_fechamento": data_fechamento,
                "origem": HistoricoCompraSuprimento.Origem.ERP,
                "processo": p,
                "arquivo_origem": "",
                "aba_origem": "",
                "linha_origem": None,
                "chave_importacao": None,
            },
        )

        registro.suprimentos_referencia.set([referencia])
        registros.append(registro)

    obsoletos = HistoricoCompraSuprimento.objects.filter(
        processo=p,
        origem=HistoricoCompraSuprimento.Origem.ERP,
    )

    if ids_ativos:
        obsoletos = obsoletos.exclude(pedido_id__in=ids_ativos)

    obsoletos.delete()

    return registros


@transaction.atomic
def remover_historico_processo(processo: ProcessoCompra):
    """Remove somente registros automáticos do ERP quando a contratação é reaberta."""
    HistoricoCompraSuprimento.objects.filter(
        processo_id=processo.pk,
        origem=HistoricoCompraSuprimento.Origem.ERP,
    ).delete()
