from decimal import Decimal, ROUND_HALF_UP
import unicodedata

from django.db.models import F, OuterRef, Q, Subquery

from compras.models import CompatibilizacaoItem

CENTAVO = Decimal("0.01")
ZERO = Decimal("0")


def _normalizar_categoria(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return " ".join(texto.encode("ascii", "ignore").decode("ascii").upper().split())


def processo_exige_compatibilizacao(processo):
    """Materiais variados pulam a análise técnica; demais categorias mantêm a etapa."""
    categoria = _normalizar_categoria(getattr(getattr(processo, "item_cronograma", None), "categoria", ""))
    return not ("MATERIA" in categoria and "VARIAD" in categoria)


def cotacao_elegivel_para_negociacao(cotacao):
    if not processo_exige_compatibilizacao(cotacao.processo):
        return cotacao.itens.exists()
    itens = list(cotacao.itens.all())
    return bool(itens) and all(item_tecnicamente_aprovado(item) for item in itens)


def queryset_itens_elegiveis_comercial(queryset, processo):
    if not processo_exige_compatibilizacao(processo):
        return queryset
    return queryset_itens_tecnicamente_aprovados(queryset)


def processo_em_fase_comercial(processo):
    """
    Retorna True enquanto o mapa comercial permanece aberto.

    Cotação, análise técnica e negociação passam a coexistir: depois que a
    análise técnica é iniciada, novas propostas ainda podem entrar e propostas
    tecnicamente aprovadas podem ser negociadas sem aguardar os demais
    fornecedores. O mapa só é congelado quando segue para APROVAÇÃO.
    """
    return processo.etapa_atual in {
        processo.Etapa.COTACAO,
        processo.Etapa.COMPATIBILIZACAO,
        processo.Etapa.NEGOCIACAO,
        processo.Etapa.APROVACAO,
    }


def processo_em_analise_ou_negociacao(processo):
    """Fase em que uma oferta já pode receber decisão técnica/comercial."""
    return processo.etapa_atual in {
        processo.Etapa.COMPATIBILIZACAO,
        processo.Etapa.NEGOCIACAO,
        processo.Etapa.APROVACAO,
    }


def quantizar_moeda(valor):
    return Decimal(str(valor or ZERO)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def ultima_compatibilizacao(item_cotado):
    return (
        item_cotado.compatibilizacoes
        .order_by("-data", "-id")
        .first()
    )


def item_tecnicamente_aprovado(item_cotado):
    """Valida a análise técnica; materiais variados são elegíveis sem compatibilização."""
    if not processo_exige_compatibilizacao(item_cotado.cotacao.processo):
        return True
    ultima = ultima_compatibilizacao(item_cotado)
    if not ultima:
        return False

    processo = item_cotado.cotacao.processo
    inicio_ciclo = processo.data_cotacao_concluida
    if inicio_ciclo and ultima.data < inicio_ciclo:
        return False
    if item_cotado.atualizado_em and ultima.data < item_cotado.atualizado_em:
        return False

    return ultima.resultado in {
        CompatibilizacaoItem.Resultado.APROVADO,
        CompatibilizacaoItem.Resultado.APROVADO_COM_RESSALVA,
    }


def queryset_itens_tecnicamente_aprovados(queryset):
    """
    Filtra pelo resultado da ÚLTIMA análise técnica de cada item e ignora
    decisões de ciclos anteriores quando o gestor solicitou ajuste.
    """
    ultima_resultado = (
        CompatibilizacaoItem.objects
        .filter(item_cotado_id=OuterRef("pk"))
        .order_by("-data", "-id")
        .values("resultado")[:1]
    )
    ultima_data = (
        CompatibilizacaoItem.objects
        .filter(item_cotado_id=OuterRef("pk"))
        .order_by("-data", "-id")
        .values("data")[:1]
    )
    return (
        queryset.annotate(
            _ultimo_resultado_tecnico=Subquery(ultima_resultado),
            _ultima_data_tecnica=Subquery(ultima_data),
        )
        .filter(
            _ultimo_resultado_tecnico__in=[
                CompatibilizacaoItem.Resultado.APROVADO,
                CompatibilizacaoItem.Resultado.APROVADO_COM_RESSALVA,
            ]
        )
        .filter(_ultima_data_tecnica__gte=F("atualizado_em"))
        .filter(
            Q(cotacao__processo__data_cotacao_concluida__isnull=True)
            | Q(_ultima_data_tecnica__gte=F("cotacao__processo__data_cotacao_concluida"))
        )
    )


def calcular_desconto_adjudicacao(item_cotado, quantidade, valor_unitario_final):
    """
    Congela o desconto proporcional da proposta original.

    Regra: se houve negociação explícita de preço unitário, considera-se que o
    preço negociado já é o preço líquido e o desconto avulso original não é
    reaplicado. Caso contrário, o desconto cotado é rateado pela quantidade
    efetivamente adjudicada.
    """
    quantidade = Decimal(str(quantidade or ZERO))
    valor_unitario_final = Decimal(str(valor_unitario_final or ZERO))
    bruto = quantidade * valor_unitario_final

    negociacao = getattr(item_cotado, "negociacao", None)
    if negociacao and negociacao.valor_unitario_negociado is not None:
        return ZERO

    desconto_cotado = Decimal(str(item_cotado.desconto_cotado or ZERO))
    quantidade_cotada = Decimal(str(item_cotado.quantidade or ZERO))
    if desconto_cotado <= 0 or quantidade_cotada <= 0 or quantidade <= 0:
        return ZERO

    desconto = desconto_cotado * (quantidade / quantidade_cotada)
    return min(quantizar_moeda(desconto), quantizar_moeda(bruto))


def frete_final_fornecedor(processo, fornecedor_id):
    """
    Retorna um único frete por fornecedor, evitando somar o mesmo frete por item.
    Prioriza o frete negociado mais recentemente informado; caso contrário,
    utiliza o frete da proposta do fornecedor.
    """
    itens = (
        processo.adjudicacoes
        .filter(cancelada=False, cotacao__fornecedor_id=fornecedor_id)
        .select_related("item_cotado__negociacao", "cotacao")
        .order_by("-item_cotado__negociacao__atualizado_em", "-id")
    )
    primeira = itens.first()
    if not primeira:
        return ZERO

    for adjudicacao in itens:
        negociacao = getattr(adjudicacao.item_cotado, "negociacao", None)
        if negociacao and negociacao.frete_negociado is not None:
            return quantizar_moeda(negociacao.frete_negociado)

    return quantizar_moeda(primeira.cotacao.frete)


def condicao_pagamento_final_fornecedor(processo, fornecedor_id):
    adjudicacoes = (
        processo.adjudicacoes
        .filter(cancelada=False, cotacao__fornecedor_id=fornecedor_id)
        .select_related("item_cotado__negociacao", "cotacao")
        .order_by("-item_cotado__negociacao__atualizado_em", "-id")
    )
    for adjudicacao in adjudicacoes:
        negociacao = getattr(adjudicacao.item_cotado, "negociacao", None)
        if negociacao and (negociacao.condicao_pagamento_negociada or "").strip():
            return negociacao.condicao_pagamento_negociada.strip()
        if (adjudicacao.condicao_pagamento_final or "").strip():
            return adjudicacao.condicao_pagamento_final.strip()
    primeira = adjudicacoes.first()
    return (primeira.cotacao.condicao_pagamento or "").strip() if primeira else ""


def prazo_final_fornecedor(processo, fornecedor_id):
    adjudicacoes = list(
        processo.adjudicacoes
        .filter(cancelada=False, cotacao__fornecedor_id=fornecedor_id)
        .exclude(prazo_entrega_dias_final__isnull=True)
        .values_list("prazo_entrega_dias_final", flat=True)
    )
    return max(adjudicacoes) if adjudicacoes else None


def total_aprovacao_processo(processo):
    adjudicacoes = list(
        processo.adjudicacoes
        .filter(cancelada=False)
        .select_related("cotacao__fornecedor")
    )
    subtotal_liquido = sum((a.valor_total for a in adjudicacoes), ZERO)
    fornecedores = {a.cotacao.fornecedor_id for a in adjudicacoes}
    fretes = sum((frete_final_fornecedor(processo, fornecedor_id) for fornecedor_id in fornecedores), ZERO)
    return quantizar_moeda(subtotal_liquido + fretes)
