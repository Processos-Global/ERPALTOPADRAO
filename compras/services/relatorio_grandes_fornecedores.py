"""Consulta única para a tela e as exportações do acompanhamento GF."""

from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone

from compras.models import GrandeFornecedorItem, PedidoCompra, RecebimentoPedidoItem
from compras.services.grande_fornecedor_status import status_por_recebimento
from compras.services.integracao_planejamento import data_necessaria_processo
from compras.services.sla import impacto_na_obra


def linhas_relatorio_gf(*, obra="", categoria="", fornecedor="", status="", busca=""):
    qs = GrandeFornecedorItem.objects.filter(fluxo__processo__fluxo_grande_fornecedor=True).select_related(
        "fluxo__processo__obra", "fluxo__processo__categoria_grande_fornecedor",
        "fluxo__processo__item_cronograma__cronograma_obra",
        "fluxo__processo__comprador", "participante_aprovado__fornecedor",
        "pedido_item__pedido__fornecedor", "pedido_item__pedido__responsavel",
    ).prefetch_related(Prefetch(
        "pedido_item__recebimentos",
        queryset=RecebimentoPedidoItem.objects.select_related("recebimento").order_by("recebimento__criado_em", "pk"),
    ))
    if any(valor and not str(valor).isdigit() for valor in (obra, categoria, fornecedor)):
        return []
    if obra:
        qs = qs.filter(fluxo__processo__obra_id=obra)
    if categoria:
        qs = qs.filter(fluxo__processo__categoria_grande_fornecedor_id=categoria)
    if fornecedor:
        qs = qs.filter(Q(participante_aprovado__fornecedor_id=fornecedor) | Q(pedido_item__pedido__fornecedor_id=fornecedor))
    if busca:
        qs = qs.filter(Q(item__icontains=busca) | Q(fluxo__processo__numero__icontains=busca)
                       | Q(material__nome__icontains=busca) | Q(pedido_item__pedido__numero__icontains=busca))

    hoje = timezone.localdate()
    linhas = []
    for item in qs.order_by("fluxo__processo__obra__nome", "fluxo__processo__numero", "ordem", "pk"):
        processo = item.fluxo.processo
        pedido_item = item.pedido_item
        pedido = pedido_item.pedido if pedido_item else None
        quantidade = pedido_item.quantidade if pedido_item else item.quantidade
        recebida = pedido_item.quantidade_recebida if pedido_item else item.quantidade_recebida
        cancelado = bool(pedido and pedido.status == PedidoCompra.Status.CANCELADO)
        pendente = Decimal("0") if cancelado else max(quantidade - recebida, Decimal("0"))
        status_codigo = status_por_recebimento(quantidade, recebida, item.status) if pedido_item else item.status
        if cancelado:
            status_codigo = GrandeFornecedorItem.Status.CANCELADO
        if status in GrandeFornecedorItem.Status.values and status_codigo != status:
            continue
        previsao = item.previsao_entrega or (pedido.previsao_entrega_atual or pedido.previsao_entrega_original if pedido else None)
        realizada = ultimo_recebimento = None
        if pedido_item:
            acumulado = Decimal("0")
            for recebimento_item in pedido_item.recebimentos.all():
                if recebimento_item.recebimento.pedido_id != pedido.pk:
                    continue
                ultimo_recebimento = timezone.localdate(recebimento_item.recebimento.criado_em)
                acumulado += recebimento_item.quantidade
                if realizada is None and acumulado >= quantidade:
                    realizada = ultimo_recebimento
        desvio_comercial = None
        if not cancelado and isinstance(previsao, date) and (realizada or status_codigo != GrandeFornecedorItem.Status.ENTREGUE):
            desvio = ((realizada or hoje) - previsao).days
            desvio_comercial = desvio if realizada else (desvio if desvio > 0 else None)
        necessaria = None
        if not pedido or (pedido.processo_id == processo.pk and pedido.obra_id == processo.obra_id):
            necessaria = data_necessaria_processo(processo)
        desvio_obra, situacao_obra = impacto_na_obra(
            necessaria=necessaria, previsao=previsao, realizada=realizada, referencia=hoje,
            cancelado=cancelado, entregue=status_codigo == GrandeFornecedorItem.Status.ENTREGUE,
        )
        fornecedor_obj = pedido.fornecedor if pedido else (item.participante_aprovado.fornecedor if item.participante_aprovado_id else None)
        responsavel = (pedido.responsavel if pedido else None) or processo.comprador
        linhas.append({
            "obra": processo.obra.nome, "categoria": str(processo.categoria_grande_fornecedor or ""),
            "fornecedor": str(fornecedor_obj or ""), "processo": processo.numero,
            "etapa": processo.get_etapa_atual_display(), "pedido": pedido.numero if pedido else "",
            "status_contratacao": pedido.get_status_display() if pedido else "Sem pedido",
            "responsavel": (responsavel.get_full_name() or responsavel.get_username()) if responsavel else "",
            "item": item.item, "especificacao": item.especificacao,
            "solicitada": item.quantidade, "unidade_solicitada": item.unidade,
            "contratada": pedido_item.quantidade if pedido_item else None,
            "quantidade": quantidade, "recebida": recebida, "pendente": pendente,
            "unidade": pedido_item.unidade if pedido_item else item.unidade,
            "valor_contratado": pedido_item.valor_total if pedido_item else None,
            "previsao": previsao, "realizada": realizada,
            "ultimo_recebimento": ultimo_recebimento, "desvio_comercial": desvio_comercial,
            "dias_atraso": max(desvio_comercial or 0, 0) if previsao and not cancelado else None,
            "data_necessaria_obra": necessaria, "desvio_obra": desvio_obra, "situacao_obra": situacao_obra,
            "status_entrega": dict(GrandeFornecedorItem.Status.choices).get(status_codigo, status_codigo),
            "pendencia": "Aguardando entrega" if pedido and pendente > 0 else ("Aguardando pedido" if not pedido else ""),
        })
    return linhas
