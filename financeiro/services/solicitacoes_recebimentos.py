"""Solicitação financeira da entrega física no fluxo normal de Compras."""

import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from compras.models import PedidoCompra, RecebimentoPedido, RecebimentoPedidoItem
from compras.services.valores import CENTAVO, ZERO, quantizar_moeda
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.aprovacoes import enviar_para_aprovacao
from financeiro.services.auditoria import registrar_evento
from financeiro.services.liberacoes import registrar_recebimento_para_liberacao
from financeiro.services.numeracao import gerar_numero
from financeiro.services.permissoes import possui_acao_financeiro
from financeiro.services.previsoes import _data_parcela_pedido, _valor_parcela_pedido


def _bloquear_recebimento(recebimento):
    pedido = PedidoCompra.objects.select_for_update().get(pk=recebimento.pedido_id)
    recebimento = RecebimentoPedido.objects.select_for_update().get(pk=recebimento.pk, pedido=pedido)
    return pedido, recebimento


def _fluxo_condicional(pedido):
    tipos = LiberacaoFinanceiraPedido.Tipo
    return pedido.processo.fluxo_grande_fornecedor or pedido.liberacoes_financeiras.filter(
        tipo__in=(tipos.PARCELA, tipos.MEDICAO, tipos.CONDICAO),
    ).exclude(status=LiberacaoFinanceiraPedido.Status.CANCELADA).exists()


def _valores_liquidos_contratados(pedido, itens):
    soma_itens = sum((item.valor_total for item in itens), ZERO)
    if soma_itens <= ZERO:
        return {item.pk: ZERO for item in itens}
    # O total de cada item já inclui o desconto individual. O resíduo entre
    # essa soma e o contratado sem frete é o desconto geral da proposta.
    total = min(soma_itens, max(pedido.valor_total - pedido.frete, ZERO))
    acumulado = anterior = ZERO
    liquidos = {}
    for item in itens:
        acumulado += item.valor_total
        atual = quantizar_moeda(total * acumulado / soma_itens)
        liquidos[item.pk] = atual - anterior
        anterior = atual
    return liquidos


def _conferir_recebimento(recebimento, pedido):
    itens_pedido = list(pedido.itens.order_by("pk"))
    contratados = _valores_liquidos_contratados(pedido, itens_pedido)
    anteriores = RecebimentoPedidoItem.objects.filter(
        recebimento__pedido=pedido, recebimento_id__lt=recebimento.pk,
    ).order_by().values("item_pedido_id").annotate(total=Sum("quantidade"))
    quantidades = {linha["item_pedido_id"]: linha["total"] for linha in anteriores}
    itens_recebidos = list(recebimento.itens.select_related("item_pedido").order_by("pk"))
    fiscal, comercial, detalhes = [], [], []
    if not (recebimento.numero_nota_fiscal and recebimento.arquivo_nota_fiscal and recebimento.valor_total_nota):
        fiscal.append("Informe número, arquivo e valor total da nota fiscal.")
    if not itens_recebidos:
        fiscal.append("Recebimento sem itens.")
    valor_materiais, valor_documentado_itens = ZERO, ZERO
    for linha in itens_recebidos:
        item = linha.item_pedido
        if item.pedido_id != pedido.pk or item.quantidade <= ZERO or linha.quantidade <= ZERO:
            fiscal.append("Há item do recebimento incompatível com o pedido.")
            continue
        quantidade_anterior = quantidades.get(item.pk, ZERO)
        quantidade_atual = quantidade_anterior + linha.quantidade
        quantidades[item.pk] = quantidade_atual
        preco_rateado = contratados[item.pk] / item.quantidade
        esperado = quantizar_moeda(preco_rateado * quantidade_atual) - quantizar_moeda(preco_rateado * quantidade_anterior)
        valor_materiais += esperado
        if linha.valor_recebido is None or linha.valor_recebido <= ZERO:
            fiscal.append(f"Informe o valor documentado de {item.descricao}.")
        else:
            valor_documentado_itens += linha.valor_recebido
            if linha.valor_recebido != esperado:
                comercial.append(f"{item.descricao}: valor da nota difere do valor comercial proporcional.")
        excedente = max(quantidade_atual - item.quantidade, ZERO) - max(quantidade_anterior - item.quantidade, ZERO)
        if excedente > ZERO:
            comercial.append(f"{item.descricao}: recebimento excedeu o pedido em {excedente} {item.unidade}.")
        detalhes.append({
            "item_pedido_id": item.pk, "descricao": item.descricao, "unidade": item.unidade,
            "quantidade_contratada": str(item.quantidade), "quantidade_recebida": str(linha.quantidade),
            "valor_unitario_aprovado": str(item.valor_unitario), "valor_esperado": str(esperado),
            "valor_documentado": str(linha.valor_recebido) if linha.valor_recebido is not None else None,
        })

    frete_nota = recebimento.valor_frete_nota or ZERO
    frete_anterior = pedido.liberacoes_financeiras.filter(
        recebimento_id__lt=recebimento.pk,
        status__in=(LiberacaoFinanceiraPedido.Status.AUTORIZADA, LiberacaoFinanceiraPedido.Status.COMPENSADA),
    ).aggregate(total=Sum("recebimento__valor_frete_nota"))["total"] or ZERO
    saldo_frete = max(pedido.frete - frete_anterior, ZERO)
    entrega_completa = bool(itens_pedido) and all(quantidades.get(item.pk, ZERO) >= item.quantidade for item in itens_pedido)
    frete_esperado = saldo_frete if entrega_completa else min(frete_nota, saldo_frete)
    if frete_nota != frete_esperado:
        comercial.append("Frete documentado diverge do saldo de frete contratado para a entrega.")
    if frete_nota < ZERO or recebimento.valor_total_nota != valor_documentado_itens + frete_nota:
        fiscal.append("O total da nota deve corresponder aos itens recebidos e ao frete discriminado.")
    esperado = valor_materiais + frete_esperado
    documentado = recebimento.valor_total_nota or ZERO
    diferenca = documentado - esperado
    return fiscal, comercial, {
        "recebimento_id": recebimento.pk, "pedido_id": pedido.pk,
        "numero_nota_fiscal": recebimento.numero_nota_fiscal,
        "valor_contratado": str(pedido.valor_total), "valor_esperado": str(esperado),
        "valor_documentado": str(documentado), "diferenca": str(diferenca),
        "diferenca_percentual": str(quantizar_moeda(diferenca * 100 / esperado)) if esperado else None,
        "frete_esperado": str(frete_esperado), "frete_documentado": str(frete_nota),
        "itens": detalhes,
    }


def _titulos_legados(pedido, recebimento):
    prefixos_legados = Q(referencia_externa__startswith="COMPRA_PEDIDO:") | Q(referencia_externa__startswith="COMPRA_PARCELA:")
    return list(TituloPagar.objects.select_for_update().filter(
        (Q(pedido=pedido) & prefixos_legados) | Q(recebimento=recebimento),
    ).order_by("pk"))


def _pendencia_de_duplicidade(pedido, recebimento, legados):
    if any(titulo.recebimento_id == recebimento.pk for titulo in legados):
        return "O recebimento já possui título. Faça a conciliação do vínculo financeiro existente."
    if any(titulo.status not in (TituloPagar.Status.PREVISTA, TituloPagar.Status.CANCELADO) for titulo in legados):
        return "Há títulos anteriores em aprovação ou pagamento. Concilie-os antes de gerar nova obrigação."
    if Pagamento.objects.filter(
        Q(titulo__pedido=pedido) | Q(titulo__recebimento__pedido=pedido) | Q(titulo__previsao_origem__pedido=pedido),
    ).exclude(
        titulo__referencia_externa__startswith="COMPRA_LIBERACAO:",
    ).exists():
        return "Há pagamento histórico no pedido. Concilie-o antes de gerar nova obrigação."
    return ""


def _compensacao(pedido, documentado):
    tipos, status = LiberacaoFinanceiraPedido.Tipo, LiberacaoFinanceiraPedido.Status
    antecipado = pedido.liberacoes_financeiras.filter(
        tipo=tipos.ANTECIPACAO, status=status.AUTORIZADA,
    ).aggregate(total=Sum("valor"))["total"] or ZERO
    consumido = pedido.liberacoes_financeiras.filter(
        tipo=tipos.RECEBIMENTO, status__in=(status.AUTORIZADA, status.COMPENSADA),
    ).aggregate(total=Sum("valor_compensado"))["total"] or ZERO
    return min(documentado, max(antecipado - consumido, ZERO))


def _parcelar_recebimento(pedido, recebimento, valor):
    parcelas = [
        (parcela, peso) for parcela in pedido.parcelas_previstas.order_by("ordem", "pk")
        if (peso := _valor_parcela_pedido(pedido, parcela)) > ZERO
    ]
    if not parcelas:
        return [(1, 1, "Pagamento único", valor, recebimento.vencimento_nota)]

    total_parcelas = len(parcelas)
    condicao = re.fullmatch(r"(\d+(?:/\d+)+)\s*dias?", pedido.condicao_pagamento.strip(), re.IGNORECASE)
    dias = [int(valor) for valor in condicao[1].split("/")] if condicao else []
    pesos = [peso for _, peso in parcelas]
    if max(pesos) - min(pesos) <= CENTAVO:
        base, resto = divmod(int(valor / CENTAVO), total_parcelas)
        valores = [(base + (indice >= total_parcelas - resto)) * CENTAVO for indice in range(total_parcelas)]
    else:
        valores = []
        total_pesos = sum(pesos, ZERO)
        acumulado = anterior = ZERO
        for peso in pesos:
            acumulado += peso
            atual = quantizar_moeda(valor * acumulado / total_pesos)
            valores.append(atual - anterior)
            anterior = atual

    resultado = []
    for ordem, ((parcela, _), valor_parcela) in enumerate(zip(parcelas, valores, strict=True), start=1):
        if valor_parcela <= ZERO:
            continue
        vencimento = _data_parcela_pedido(pedido, parcela)
        if recebimento.vencimento_nota:
            if ordem == 1:
                vencimento = recebimento.vencimento_nota
            elif len(dias) == total_parcelas:
                try:
                    vencimento = recebimento.vencimento_nota + timedelta(days=dias[ordem - 1] - dias[0])
                except OverflowError:
                    vencimento = None
        resultado.append((ordem, total_parcelas, parcela.descricao, valor_parcela, vencimento))
    return resultado


def _criar_titulos(liberacao, recebimento, pedido, valor, comercial, detalhes, usuario):
    fornecedor = pedido.fornecedor
    conferencia = TituloPagar.Conferencia.DIVERGENCIA if comercial else TituloPagar.Conferencia.CONFERIDO
    especificacao = "\n".join(f"{item['descricao']} · {item['quantidade_recebida']} {item['unidade']}" for item in detalhes["itens"])
    criados = []
    for ordem, total_parcelas, descricao_parcela, valor_parcela, vencimento in _parcelar_recebimento(pedido, recebimento, valor):
        referencia = f"COMPRA_LIBERACAO:{liberacao.pk}"
        if ordem != 1:
            referencia = f"{referencia}:{ordem}"
        titulo = TituloPagar.objects.create(
            numero=gerar_numero("TITULO"), referencia_externa=referencia,
            origem=TituloPagar.Origem.COMPRA, classificacao=TituloPagar.Classificacao.MATERIAL,
            pedido=pedido, recebimento=recebimento, obra=pedido.obra, fornecedor=fornecedor,
            plano_financeiro=pedido.processo.apropriacao, beneficiario_nome=fornecedor.nome_exibicao,
            beneficiario_documento=fornecedor.documento, beneficiario_banco=fornecedor.banco,
            beneficiario_agencia=fornecedor.agencia, beneficiario_conta_corrente=fornecedor.conta_corrente,
            beneficiario_operacao=fornecedor.operacao_bancaria, beneficiario_pix=fornecedor.pix,
            beneficiario_titular=fornecedor.titular_conta, origem_detalhe=f"Pedido {pedido.numero}",
            descricao=f"{pedido.numero} · NF {recebimento.numero_nota_fiscal}",
            especificacao_pagamento=especificacao, documento_numero=recebimento.numero_nota_fiscal,
            competencia=timezone.localdate(recebimento.criado_em),
            condicao_pagamento=pedido.condicao_pagamento, gatilho_pagamento="Recebimento",
            parcela_ordem=ordem, parcela_total=total_parcelas, parcela_descricao=descricao_parcela,
            vencimento=vencimento, valor_original=valor_parcela, conferencia=conferencia, criado_por=usuario,
        )
        registrar_evento(titulo, "SOLICITACAO_RECEBIMENTO", "Solicitação automática do recebimento de Compras.", usuario, detalhes)
        criados.append(titulo)
    return criados


def gerar_solicitacao_pendente(liberacao, recebimento, pedido, usuario):
    """Materializa a obrigação com pedido, recebimento e liberação já bloqueados."""
    fiscal, comercial, detalhes = _conferir_recebimento(recebimento, pedido)
    legados = _titulos_legados(pedido, recebimento)
    if pendencia := _pendencia_de_duplicidade(pedido, recebimento, legados):
        fiscal.append(pendencia)
    liberacao.valor_origem = Decimal(detalhes["valor_documentado"])
    liberacao.valor_esperado = Decimal(detalhes["valor_esperado"])
    liberacao.divergencias_comerciais = comercial
    liberacao.divergencia = " ".join(fiscal)
    if fiscal:
        liberacao.status = LiberacaoFinanceiraPedido.Status.DIVERGENTE
        liberacao.save()
        return liberacao

    for legado in legados:
        if legado.status == TituloPagar.Status.PREVISTA:
            legado.status = TituloPagar.Status.CANCELADO
            legado.cancelado_em = timezone.now()
            legado.save(update_fields=["status", "cancelado_em", "atualizado_em"])
            registrar_evento(legado, "SUBSTITUIDO_RECEBIMENTO", "Previsão anterior substituída pelo recebimento.", usuario)

    liberacao.valor_compensado = _compensacao(pedido, liberacao.valor_origem)
    liberacao.valor = liberacao.valor_origem - liberacao.valor_compensado
    liberacao.autorizado_em = timezone.now()
    criados = []
    if liberacao.valor:
        criados = _criar_titulos(liberacao, recebimento, pedido, liberacao.valor, comercial, detalhes, usuario)
        liberacao.titulo = criados[0]
        liberacao.status = LiberacaoFinanceiraPedido.Status.AUTORIZADA
    else:
        liberacao.status = LiberacaoFinanceiraPedido.Status.COMPENSADA
    liberacao.save()
    for titulo in criados:
        if titulo.vencimento and titulo.plano_financeiro_id:
            enviar_para_aprovacao(titulo, usuario=usuario)
    return liberacao


@transaction.atomic
def registrar_solicitacao_recebimento(recebimento, *, usuario=None):
    pedido, recebimento = _bloquear_recebimento(recebimento)
    if existente := LiberacaoFinanceiraPedido.objects.filter(recebimento=recebimento).first():
        return existente
    if _fluxo_condicional(pedido):
        return registrar_recebimento_para_liberacao(recebimento, usuario=usuario)
    liberacao = LiberacaoFinanceiraPedido.objects.create(
        pedido=pedido, recebimento=recebimento, tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
        referencia=f"RECEBIMENTO:{recebimento.pk}", criado_por=usuario,
    )
    return gerar_solicitacao_pendente(liberacao, recebimento, pedido, usuario)


def bloquear_pendencia_recebimento(recebimento):
    return LiberacaoFinanceiraPedido.objects.select_for_update().filter(
        recebimento=recebimento, valor_esperado__isnull=False,
        status=LiberacaoFinanceiraPedido.Status.DIVERGENTE, titulo__isnull=True,
    ).first()


@transaction.atomic
def reprocessar_solicitacao_recebimento(recebimento, *, usuario):
    if not possui_acao_financeiro(usuario, "EDITAR_TITULOS"):
        raise PermissionDenied("Permissão financeira de edição necessária.")
    pedido, recebimento = _bloquear_recebimento(recebimento)
    liberacao = bloquear_pendencia_recebimento(recebimento)
    if not liberacao:
        raise ValidationError("O recebimento não possui pendência fiscal reprocessável.")
    return gerar_solicitacao_pendente(liberacao, recebimento, pedido, usuario)
