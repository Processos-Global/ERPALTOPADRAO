"""Leitura gerencial de compromissos, sem criar ou alterar obrigações."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, Exists, F, OuterRef, Prefetch, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest

from compras.models import ContratoCompra, ParcelaPrevistaPedido, PedidoCompra, RecebimentoPedido, RecebimentoPedidoItem
from compras.services.comercial import quantizar_moeda
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.agenda import saldo_titulo_sql, titulos_disponiveis_pagamento


MOEDA = DecimalField(max_digits=18, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MOEDA)


def pedidos_comprometidos(*, obra_id=None, fornecedor_id=None, busca="", status=""):
    """Cada linha é um pedido; filhos são agregados em subconsultas independentes."""
    recebimentos = (
        RecebimentoPedidoItem.objects
        .filter(recebimento__pedido_id=OuterRef("pk"))
        .order_by()
        .values("recebimento__pedido_id")
        .annotate(valor=Sum("valor_recebido"), sem_valor=Count("pk", filter=Q(valor_recebido__isnull=True)))
    )
    notas = (
        RecebimentoPedido.objects.filter(pedido_id=OuterRef("pk"), valor_total_nota__isnull=False)
        .exclude(Q(numero_nota_fiscal__isnull=True) | Q(numero_nota_fiscal="") | Q(arquivo_nota_fiscal=""))
        .order_by().values("pedido_id")
        .annotate(
            valor=Sum("valor_total_nota"),
            frete=Sum("valor_frete_nota", filter=Q(liberacao_financeira__status__in=[
                LiberacaoFinanceiraPedido.Status.PENDENTE,
                LiberacaoFinanceiraPedido.Status.AUTORIZADA,
                LiberacaoFinanceiraPedido.Status.COMPENSADA,
            ])),
        )
    )
    pagamentos = (
        Pagamento.objects
        .filter(titulo__pedido_id=OuterRef("pk"), status=Pagamento.Status.EFETIVADO)
        .order_by()
        .values("titulo__pedido_id")
        .annotate(valor=Sum("valor"))
    )
    liberacoes = (
        LiberacaoFinanceiraPedido.objects
        .filter(pedido_id=OuterRef("pk"), status=LiberacaoFinanceiraPedido.Status.AUTORIZADA)
        .order_by().values("pedido_id").annotate(valor=Sum("valor"))
    )
    registros_financeiros = LiberacaoFinanceiraPedido.objects.filter(pedido_id=OuterRef("pk"))
    titulos = TituloPagar.objects.filter(pedido_id=OuterRef("pk")).order_by()
    valor_liquido = Greatest(
        F("valor_original") + F("juros") + F("multa") + F("outros_acrescimos") - F("desconto"), ZERO,
    )
    titulos_ativos = titulos.exclude(status=TituloPagar.Status.CANCELADO).values("pedido_id").annotate(
        valor=Sum(valor_liquido),
    )
    aguardando = titulos.filter(
        recebimento__isnull=False, status=TituloPagar.Status.AGUARDANDO_APROVACAO,
    ).values("pedido_id").annotate(valor=Sum(valor_liquido))
    aprovado_a_pagar = titulos_disponiveis_pagamento(titulos).values("pedido_id").annotate(valor=Sum(saldo_titulo_sql()))
    # O cancelamento integral em Compras preserva pedido, recebimentos e títulos.
    # Excluí-lo ocultaria pagamentos já efetivados e o saldo não entregue.
    qs = PedidoCompra.objects.all()
    if obra_id:
        qs = qs.filter(obra_id=obra_id)
    if fornecedor_id:
        qs = qs.filter(fornecedor_id=fornecedor_id)
    if status in PedidoCompra.Status.values:
        qs = qs.filter(status=status)
    if busca:
        qs = qs.filter(Q(numero__icontains=busca) | Q(processo__numero__icontains=busca))
    return (
        qs.select_related("obra", "fornecedor", "processo")
        .annotate(
            recebido_identificado=Coalesce(Subquery(recebimentos.values("valor")[:1], output_field=MOEDA), ZERO),
            valor_documentado=Coalesce(Subquery(notas.values("valor")[:1], output_field=MOEDA), ZERO),
            frete_documentado=Coalesce(Subquery(notas.values("frete")[:1], output_field=MOEDA), ZERO),
            itens_recebidos_sem_valor=Coalesce(Subquery(recebimentos.values("sem_valor")[:1]), Value(0)),
            pago_efetivado=Coalesce(Subquery(pagamentos.values("valor")[:1], output_field=MOEDA), ZERO),
            liberado_financeiramente=Coalesce(Subquery(liberacoes.values("valor")[:1], output_field=MOEDA), ZERO),
            tem_registros_financeiros=Exists(registros_financeiros),
            obrigacao_em_titulos=Coalesce(Subquery(titulos_ativos.values("valor")[:1], output_field=MOEDA), ZERO),
            recebido_aguardando_aprovacao=Coalesce(Subquery(aguardando.values("valor")[:1], output_field=MOEDA), ZERO),
            aprovado_a_pagar=Coalesce(Subquery(aprovado_a_pagar.values("valor")[:1], output_field=MOEDA), ZERO),
        )
        .alias(recebido_com_frete=F("recebido_identificado") + F("frete_documentado"))
        .annotate(
            saldo_cancelado=Case(
                When(
                    ~Q(motivo_cancelamento=""),
                    status=PedidoCompra.Status.CANCELADO,
                    cancelado_em__isnull=False,
                    itens_recebidos_sem_valor=0,
                    obrigacao_em_titulos__lte=F("recebido_com_frete"),
                    then=Greatest(F("valor_total") - F("frete") - F("recebido_identificado"), ZERO),
                ),
                default=ZERO,
                output_field=MOEDA,
            ),
        )
        .annotate(
            valor_vigente=Greatest(F("valor_total") - F("saldo_cancelado"), ZERO),
            saldo_receber=Case(
                When(status__in=[PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE], then=ZERO),
                default=Greatest(F("valor_total") - F("frete") - F("recebido_identificado"), ZERO),
                output_field=MOEDA,
            ),
            saldo_cancelamento_pendente=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("valor_total") - F("recebido_com_frete") - F("saldo_cancelado"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
            excedente_pago=Greatest(F("pago_efetivado") - F("valor_total"), ZERO),
            pago_sem_recebimento=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("pago_efetivado") - F("recebido_com_frete"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
            liberado_sem_recebimento=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("liberado_financeiramente") - F("recebido_com_frete"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
        )
        .annotate(
            saldo_financeiro=Greatest(F("valor_vigente") - F("pago_efetivado"), ZERO),
            saldo_liberar=Greatest(F("valor_vigente") - Greatest(F("liberado_financeiramente"), F("pago_efetivado")), ZERO),
        )
        .order_by("-criado_em", "-pk")
    )


def totais_pedidos(qs):
    # SQLite não agrega corretamente algumas anotações correlacionadas deste
    # queryset. Projetar apenas números e somar em fluxo evita linhas duplicadas
    # por joins e mantém os mesmos valores da tabela em todos os bancos.
    monetarios = (
        "valor_total", "frete", "descontos", "valor_vigente", "recebido_identificado", "pago_efetivado",
        "valor_documentado", "frete_documentado", "saldo_receber", "saldo_liberar",
        "saldo_financeiro", "saldo_cancelado", "excedente_pago",
        "saldo_cancelamento_pendente",
        "pago_sem_recebimento", "liberado_sem_recebimento",
        "liberado_financeiramente", "recebido_aguardando_aprovacao", "aprovado_a_pagar",
    )
    totais = {campo if campo != "valor_total" else "contratado": Decimal("0") for campo in monetarios}
    totais["itens_recebidos_sem_valor"] = 0
    for linha in qs.order_by().values_list(*monetarios, "itens_recebidos_sem_valor").iterator(chunk_size=1000):
        for campo, valor in zip(monetarios, linha[:-1]):
            totais["contratado" if campo == "valor_total" else campo] += valor or Decimal("0")
        totais["itens_recebidos_sem_valor"] += linha[-1] or 0
    return totais


def compromissos_datados(inicio, fim, *, obra_ids=None, classe=None, apropriacao=None, fornecedor=None):
    """Projeta o saldo de pedidos normais em parcelas com data comercial conhecida."""
    from financeiro.services.indicadores_gerenciais import _filtros
    from financeiro.services.previsoes import _data_parcela_pedido, _valor_parcela_pedido

    parcelas = ParcelaPrevistaPedido.objects.filter(pedido_id=OuterRef("pk"))
    datas = parcelas.filter(
        Q(data_prevista__range=(inicio, fim))
        | Q(data_prevista__isnull=True, dias__isnull=False)
        | Q(data_prevista__isnull=True, evento_gatilho=ParcelaPrevistaPedido.Gatilho.ENTREGA),
    )
    pedidos = pedidos_comprometidos().filter(
        Exists(datas), processo__fluxo_grande_fornecedor=False,
    ).exclude(status__in=[PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE]).annotate(
        plano_financeiro_id=F("processo__apropriacao_id"),
    )
    pedidos = _filtros(pedidos, obra_ids=obra_ids, classe=classe, apropriacao=apropriacao, fornecedor=fornecedor)
    pedidos = pedidos.select_related(None).only(
        "valor_total", "data", "previsao_entrega_atual", "previsao_entrega_original",
    ).prefetch_related(Prefetch(
        "parcelas_previstas", queryset=ParcelaPrevistaPedido.objects.order_by("ordem", "pk"),
    ))
    por_data = defaultdict(Decimal)
    for pedido in pedidos.iterator(chunk_size=200):
        comprometido = max(
            pedido.obrigacao_em_titulos, pedido.pago_efetivado, pedido.recebido_identificado + pedido.frete_documentado,
        )
        saldo = pedido.valor_total - comprometido
        if saldo <= 0:
            continue
        pesos = [(parcela, _valor_parcela_pedido(pedido, parcela)) for parcela in pedido.parcelas_previstas.all()]
        total_pesos = sum(peso for _, peso in pesos if peso > 0)
        acumulado = anterior = Decimal("0.00")
        for parcela, peso in pesos:
            if peso <= 0:
                continue
            acumulado += peso
            atual = quantizar_moeda(saldo * acumulado / total_pesos)
            data = _data_parcela_pedido(pedido, parcela)
            if data and inicio <= data <= fim:
                por_data[data] += atual - anterior
            anterior = atual
    return por_data


def contratos_assinados_separados(*, obra_id=None, fornecedor_id=None, busca=""):
    """Contratos assinados ficam fora dos totais de pedidos, mesmo com processo comum."""
    qs = ContratoCompra.objects.filter(status=ContratoCompra.Status.ASSINADO).select_related(
        "obra", "fornecedor", "processo"
    )
    if obra_id:
        qs = qs.filter(obra_id=obra_id)
    if fornecedor_id:
        qs = qs.filter(fornecedor_id=fornecedor_id)
    if busca:
        qs = qs.filter(Q(numero__icontains=busca) | Q(processo__numero__icontains=busca))
    return qs.order_by("-assinado_em", "-pk")
