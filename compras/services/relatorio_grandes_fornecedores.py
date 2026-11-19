"""Consulta única para a tela e as exportações do acompanhamento GF."""

from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone

from compras.models import GrandeFornecedorItem, RecebimentoPedidoItem
from compras.services.grande_fornecedor_status import status_por_recebimento


def linhas_relatorio_gf(*, obra="", categoria="", fornecedor="", status="", busca=""):
    qs = GrandeFornecedorItem.objects.filter(fluxo__processo__fluxo_grande_fornecedor=True).select_related(
        "fluxo__processo__obra", "fluxo__processo__categoria_grande_fornecedor",
        "fluxo__processo__item_cronograma", "participante_aprovado__fornecedor",
        "pedido_item__pedido__fornecedor", "material",
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
        pendente = max(quantidade - recebida, Decimal("0"))
        status_codigo = status_por_recebimento(quantidade, recebida, item.status) if pedido_item else item.status
        if status in GrandeFornecedorItem.Status.values and status_codigo != status:
            continue
        previsao = item.previsao_entrega or (pedido.previsao_entrega_atual or pedido.previsao_entrega_original if pedido else None)
        realizada = None
        if pedido_item and pendente == 0:
            acumulado = Decimal("0")
            for recebimento_item in pedido_item.recebimentos.all():
                acumulado += recebimento_item.quantidade
                if acumulado >= quantidade:
                    realizada = timezone.localtime(recebimento_item.recebimento.criado_em).date()
                    break
        referencia_atraso = realizada or hoje
        dias_atraso = max((referencia_atraso - previsao).days, 0) if isinstance(previsao, date) else None
        fornecedor_obj = pedido.fornecedor if pedido else (item.participante_aprovado.fornecedor if item.participante_aprovado_id else None)
        linhas.append({
            "obra": processo.obra.nome, "categoria": str(processo.categoria_grande_fornecedor or ""),
            "fornecedor": str(fornecedor_obj or ""), "processo": processo.numero,
            "etapa": processo.get_etapa_atual_display(), "pedido": pedido.numero if pedido else "",
            "status_contratacao": pedido.get_status_display() if pedido else "Sem pedido",
            "item": item.item, "especificacao": item.especificacao,
            "quantidade": quantidade, "recebida": recebida, "pendente": pendente,
            "unidade": pedido_item.unidade if pedido_item else item.unidade,
            "valor_contratado": pedido_item.valor_total if pedido_item else None,
            "previsao": previsao, "realizada": realizada,
            "dias_atraso": dias_atraso,
            "status_entrega": dict(GrandeFornecedorItem.Status.choices).get(status_codigo, status_codigo),
            "pendencia": "Aguardando entrega" if pedido and pendente > 0 else ("Aguardando pedido" if not pedido else ""),
        })
    return linhas
