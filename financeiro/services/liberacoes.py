"""Liberações aditivas de compras; nunca modifica o valor contratado ou pago."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from compras.models import PedidoCompra, RecebimentoPedido, RecebimentoPedidoItem
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.numeracao import gerar_numero
from financeiro.services.permissoes import possui_acao_financeiro


CENTAVO = Decimal("0.01")
ZERO = Decimal("0")


def _valor_monetario(valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Informe um valor monetário válido.")
    if not numero.is_finite() or numero <= 0 or numero != numero.quantize(CENTAVO):
        raise ValidationError("O valor deve ser positivo e ter no máximo duas casas decimais.")
    return numero


def _conferir_valor_recebimento(recebimento, pedido):
    itens = list(RecebimentoPedidoItem.objects.filter(recebimento=recebimento).select_related("item_pedido"))
    motivos = []
    if not itens:
        motivos.append("Recebimento sem itens.")
    if any(item.item_pedido.pedido_id != recebimento.pedido_id for item in itens):
        motivos.append("Item de outro pedido.")
    if any(item.valor_recebido is None for item in itens):
        motivos.append("Itens sem valor recebido.")
    valor_itens = sum((item.valor_recebido or ZERO for item in itens), ZERO)
    if valor_itens <= ZERO:
        motivos.append("Valor recebido não positivo.")
    frete = recebimento.valor_frete_nota or ZERO
    if frete < ZERO or frete > (pedido.frete or ZERO):
        motivos.append("Frete da nota fiscal fora do valor contratado no pedido.")
    if frete > ZERO and not (
        recebimento.numero_nota_fiscal and recebimento.arquivo_nota_fiscal and recebimento.valor_total_nota is not None
    ):
        motivos.append("Frete discriminado exige identificação, arquivo e total da nota fiscal.")
    valor = valor_itens + frete
    if recebimento.valor_total_nota is not None and valor != recebimento.valor_total_nota:
        motivos.append("Total da nota fiscal difere da soma dos itens e do frete discriminado.")
    return valor, motivos


@transaction.atomic
def registrar_recebimento_para_liberacao(recebimento, *, usuario=None):
    """Cria uma candidata por recebimento. Divergência exige correção na origem."""
    recebimento = RecebimentoPedido.objects.select_for_update().get(pk=recebimento.pk)
    referencia = f"RECEBIMENTO:{recebimento.pk}"
    existente = LiberacaoFinanceiraPedido.objects.filter(referencia=referencia).first()
    if existente:
        return existente
    pedido = recebimento.pedido
    valor, motivos = _conferir_valor_recebimento(recebimento, pedido)
    return LiberacaoFinanceiraPedido.objects.create(
        pedido=pedido, recebimento=recebimento, referencia=referencia,
        tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
        status=(LiberacaoFinanceiraPedido.Status.DIVERGENTE if motivos else LiberacaoFinanceiraPedido.Status.PENDENTE),
        valor=valor, valor_origem=valor, divergencia=" ".join(motivos), criado_por=usuario,
    )


@transaction.atomic
def registrar_liberacao_condicional(pedido, *, tipo, valor, referencia, usuario,
                                   parcela=None, justificativa=""):
    """Condição contratual explícita (antecipação, parcela ou medição)."""
    if not possui_acao_financeiro(usuario, "LANCAR_TITULOS"):
        raise PermissionDenied("Permissão financeira de lançamento necessária.")
    if tipo not in {
        LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
        LiberacaoFinanceiraPedido.Tipo.PARCELA,
        LiberacaoFinanceiraPedido.Tipo.MEDICAO,
        LiberacaoFinanceiraPedido.Tipo.CONDICAO,
    }:
        raise ValidationError("Tipo de condição inválido.")
    valor = _valor_monetario(valor)
    if not referencia or len(referencia) > 100 or not justificativa.strip():
        raise ValidationError("Informe referência estável e justificativa contratual.")
    if parcela and parcela.pedido_id != pedido.pk:
        raise ValidationError("A parcela não pertence ao pedido.")
    chave = f"CONDICAO:{pedido.pk}:{referencia}"
    existente = LiberacaoFinanceiraPedido.objects.select_for_update().filter(referencia=chave).first()
    if existente:
        if (existente.tipo, existente.valor, existente.parcela_id) != (tipo, valor, parcela.pk if parcela else None):
            raise ValidationError("A referência já foi usada com dados diferentes.")
        return existente
    return LiberacaoFinanceiraPedido.objects.create(
        pedido=pedido, parcela=parcela, referencia=chave, tipo=tipo,
        valor=valor, valor_origem=valor, justificativa=justificativa.strip(), criado_por=usuario,
    )


@transaction.atomic
def autorizar_liberacao(liberacao, *, usuario):
    """Autoriza o valor de origem e cria título separado, ainda sujeito à aprovação."""
    if not possui_acao_financeiro(usuario, "APROVAR"):
        raise PermissionDenied("Permissão financeira de aprovação necessária.")
    pedido = PedidoCompra.objects.select_for_update().get(pk=liberacao.pedido_id)
    liberacao = LiberacaoFinanceiraPedido.objects.select_for_update().get(pk=liberacao.pk)
    if liberacao.status == LiberacaoFinanceiraPedido.Status.AUTORIZADA and liberacao.titulo_id:
        return liberacao.titulo
    if liberacao.status == LiberacaoFinanceiraPedido.Status.COMPENSADA:
        return None
    if liberacao.status != LiberacaoFinanceiraPedido.Status.PENDENTE:
        raise ValidationError("Esta liberação não está pendente e conciliada.")
    if pedido.status == PedidoCompra.Status.CANCELADO:
        raise ValidationError("Pedido cancelado não admite liberação.")
    valor_origem = _valor_monetario(liberacao.valor_origem)
    valor = valor_origem
    frete_recebido = None
    if liberacao.recebimento_id:
        recebimento = liberacao.recebimento
        valor_atual, motivos = _conferir_valor_recebimento(recebimento, pedido)
        if motivos:
            raise ValidationError(motivos)
        if valor_atual != valor_origem:
            raise ValidationError("O recebimento mudou desde a conferência da liberação.")
        frete_recebido = recebimento.valor_frete_nota
        if frete_recebido:
            frete_anterior = LiberacaoFinanceiraPedido.objects.filter(
                pedido=pedido,
                tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
                status__in=[LiberacaoFinanceiraPedido.Status.AUTORIZADA, LiberacaoFinanceiraPedido.Status.COMPENSADA],
            ).aggregate(total=Sum("recebimento__valor_frete_nota"))["total"] or ZERO
            if frete_anterior + frete_recebido > pedido.frete:
                raise ValidationError("O frete das notas liberadas excede o frete contratado.")
        antecipado = LiberacaoFinanceiraPedido.objects.filter(
            pedido=pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
        ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
        compensado_anterior = LiberacaoFinanceiraPedido.objects.filter(
            pedido=pedido, tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
            status__in=[LiberacaoFinanceiraPedido.Status.AUTORIZADA, LiberacaoFinanceiraPedido.Status.COMPENSADA],
        ).aggregate(total=Sum("valor_compensado"))["total"] or Decimal("0")
        compensacao = min(valor_origem, max(antecipado - compensado_anterior, Decimal("0")))
        valor = valor_origem - compensacao
    else:
        compensacao = Decimal("0")
    total_anterior = LiberacaoFinanceiraPedido.objects.filter(
        pedido=pedido, status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
    ).aggregate(total=Sum("valor"))["total"] or Decimal("0")
    if total_anterior + valor > pedido.valor_total:
        raise ValidationError("A soma das liberações excede o valor contratado.")

    if Pagamento.objects.filter(
        titulo__pedido=pedido, status=Pagamento.Status.EFETIVADO,
    ).exclude(titulo__referencia_externa__startswith="COMPRA_LIBERACAO:").exists():
        raise ValidationError("Há pagamento antigo vinculado ao pedido; concilie-o antes de liberar novamente.")

    prefixos = ("COMPRA_PEDIDO:", "COMPRA_PARCELA:")
    legados = list(TituloPagar.objects.select_for_update().filter(pedido=pedido, origem=TituloPagar.Origem.COMPRA))
    for titulo in legados:
        if not (titulo.referencia_externa or "").startswith(prefixos):
            continue
        if titulo.status not in (TituloPagar.Status.PREVISTA, TituloPagar.Status.CANCELADO):
            raise ValidationError("Há título anterior em fluxo de aprovação ou pagamento; concilie-o antes de liberar novamente.")
        if Pagamento.objects.filter(titulo=titulo, status=Pagamento.Status.EFETIVADO).exists():
            raise ValidationError("Há pagamento anterior efetivado; concilie-o antes de liberar novamente.")

    for legado in legados:
        if (legado.referencia_externa or "").startswith(prefixos) and legado.status == TituloPagar.Status.PREVISTA:
            legado.status = TituloPagar.Status.CANCELADO
            legado.cancelado_em = timezone.now()
            legado.save(update_fields=["status", "cancelado_em", "atualizado_em"])
            registrar_evento(legado, "SUBSTITUIDO_LIBERACAO", "Previsão substituída por títulos de liberações.", usuario)

    if valor == 0:
        liberacao.valor = Decimal("0")
        liberacao.valor_compensado = compensacao
        liberacao.status = LiberacaoFinanceiraPedido.Status.COMPENSADA
        liberacao.autorizado_por = usuario
        liberacao.autorizado_em = timezone.now()
        liberacao.save(update_fields=["valor", "valor_compensado", "status", "autorizado_por", "autorizado_em"])
        return None

    titulo = TituloPagar.objects.create(
        numero=gerar_numero("TITULO"), referencia_externa=f"COMPRA_LIBERACAO:{liberacao.pk}",
        origem=TituloPagar.Origem.COMPRA, pedido=pedido, recebimento=liberacao.recebimento,
        fornecedor=pedido.fornecedor, beneficiario_nome=getattr(pedido.fornecedor, "nome_exibicao", None) or str(pedido.fornecedor),
        obra=pedido.obra, plano_financeiro=pedido.processo.apropriacao,
        origem_detalhe=f"Pedido {pedido.numero}",
        descricao=f"{pedido.numero} · {liberacao.get_tipo_display()}",
        especificacao_pagamento=(f"Liberação {liberacao.referencia}. {liberacao.justificativa}"),
        condicao_pagamento=pedido.condicao_pagamento or "",
        gatilho_pagamento=liberacao.get_tipo_display(),
        vencimento=liberacao.parcela.data_prevista if liberacao.parcela_id else None,
        valor_original=valor, status=TituloPagar.Status.PREVISTA, criado_por=usuario,
    )
    dados = {"liberacao_id": liberacao.pk, "pedido_id": pedido.pk}
    if frete_recebido is not None:
        dados["valor_frete_nota"] = str(frete_recebido)
    registrar_evento(titulo, "LIBERACAO_COMPRA", "Título criado por liberação financeira do pedido.", usuario, dados)
    liberacao.titulo = titulo
    liberacao.valor = valor
    liberacao.valor_compensado = compensacao
    liberacao.status = LiberacaoFinanceiraPedido.Status.AUTORIZADA
    liberacao.autorizado_por = usuario
    liberacao.autorizado_em = timezone.now()
    liberacao.save(update_fields=["titulo", "valor", "valor_compensado", "status", "autorizado_por", "autorizado_em"])
    return titulo
