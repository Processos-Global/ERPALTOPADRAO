import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from compras.models import (
    GrandeFornecedorProcesso,
    ParcelaGrandeFornecedor,
    PedidoCompra,
)
from financeiro.models import DespesaRecorrente, PrevisaoFinanceira, TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.numeracao import gerar_numero


STATUS_PROTEGIDOS = {
    TituloPagar.Status.AGUARDANDO_APROVACAO,
    TituloPagar.Status.APROVADO,
    TituloPagar.Status.PAGO,
}


def _nome_fornecedor(fornecedor):
    if not fornecedor:
        return ""
    return getattr(fornecedor, "nome_exibicao", None) or str(fornecedor)


def _valor_parcela_pedido(pedido, parcela):
    if parcela.valor is not None:
        return parcela.valor
    if parcela.percentual is not None:
        return (pedido.valor_total * parcela.percentual / Decimal("100")).quantize(Decimal("0.01"))
    return Decimal("0")


def _data_parcela_pedido(pedido, parcela):
    if parcela.data_prevista:
        return parcela.data_prevista
    if parcela.dias is not None:
        return pedido.data + timedelta(days=parcela.dias)
    if parcela.evento_gatilho == parcela.Gatilho.ENTREGA:
        return pedido.previsao_entrega_atual or pedido.previsao_entrega_original
    return None


def _gatilho_parcela_pedido(parcela):
    rotulo = parcela.get_evento_gatilho_display()
    if parcela.dias is not None:
        return f"{parcela.dias} dia(s)"
    return rotulo


def _status_integrado_atual(conta, *, cancelado=False, liberado=False):
    if conta and conta.status == TituloPagar.Status.PAGO:
        return conta.status
    if cancelado:
        return TituloPagar.Status.CANCELADO
    if conta and conta.status in STATUS_PROTEGIDOS:
        return conta.status
    if liberado:
        return TituloPagar.Status.AGUARDANDO_APROVACAO
    return TituloPagar.Status.PREVISTA


def _upsert_conta_integrada(*, referencia, defaults, cancelado=False, liberado=False):
    conta = TituloPagar.objects.filter(referencia_externa=referencia).first()
    criada = conta is None
    if criada:
        conta = TituloPagar(
            numero=gerar_numero("TITULO"),
            referencia_externa=referencia,
            status=TituloPagar.Status.PREVISTA,
        )

    for campo, valor in defaults.items():
        # Se a origem ainda não conhece a data, preserva um vencimento que o
        # Financeiro tenha definido manualmente. Quando a origem passar a
        # informar uma data, ela volta a ser a fonte oficial.
        if campo == "vencimento" and valor is None and not criada and conta.vencimento:
            continue
        setattr(conta, campo, valor)

    conta.status = _status_integrado_atual(conta, cancelado=cancelado, liberado=liberado)
    conta.save()
    if criada:
        registrar_evento(conta, "CRIADO_INTEGRACAO", "Conta criada automaticamente pela origem integrada.", None)
    return conta


@transaction.atomic
def sincronizar_contas_pedido(pedido):
    """Transforma a condição de pagamento de Compras em Contas a Pagar.

    Uma parcela = uma conta. Pedido sem parcelas = uma conta única. Nenhuma NF
    cria uma segunda obrigação; as NFs continuam vinculadas ao próprio pedido.
    """
    parcelas = list(pedido.parcelas_previstas.all().order_by("ordem", "id"))
    refs_ativas = []
    total_parcelas = len(parcelas)
    cancelado = pedido.status == PedidoCompra.Status.CANCELADO
    beneficiario = _nome_fornecedor(pedido.fornecedor)

    if parcelas:
        for indice, parcela in enumerate(parcelas, start=1):
            valor = _valor_parcela_pedido(pedido, parcela)
            if valor <= 0:
                continue
            referencia = f"COMPRA_PARCELA:{parcela.pk}"
            refs_ativas.append(referencia)
            descricao_parcela = parcela.descricao or f"Parcela {indice}"
            _upsert_conta_integrada(
                referencia=referencia,
                cancelado=cancelado,
                defaults={
                    "origem": TituloPagar.Origem.COMPRA,
                    "origem_detalhe": f"Pedido {pedido.numero}",
                    "pedido": pedido,
                    "fornecedor": pedido.fornecedor,
                    "beneficiario_nome": beneficiario,
                    "obra": pedido.obra,
                    "descricao": f"{pedido.numero} · {descricao_parcela}",
                    "valor_original": valor,
                    "vencimento": _data_parcela_pedido(pedido, parcela),
                    "parcela_ordem": indice,
                    "parcela_total": total_parcelas,
                    "parcela_descricao": descricao_parcela,
                    "gatilho_pagamento": _gatilho_parcela_pedido(parcela),
                    "condicao_pagamento": pedido.condicao_pagamento or "",
                },
            )
    elif pedido.valor_total and pedido.valor_total > 0:
        referencia = f"COMPRA_PEDIDO:{pedido.pk}"
        refs_ativas.append(referencia)
        _upsert_conta_integrada(
            referencia=referencia,
            cancelado=cancelado,
            defaults={
                "origem": TituloPagar.Origem.COMPRA,
                "origem_detalhe": f"Pedido {pedido.numero}",
                "pedido": pedido,
                "fornecedor": pedido.fornecedor,
                "beneficiario_nome": beneficiario,
                "obra": pedido.obra,
                "descricao": f"Pedido {pedido.numero} · {beneficiario}",
                "valor_original": pedido.valor_total,
                "vencimento": pedido.previsao_entrega_atual or pedido.previsao_entrega_original,
                "parcela_ordem": 1,
                "parcela_total": 1,
                "parcela_descricao": "Pagamento único",
                "gatilho_pagamento": "Definir vencimento" if not (pedido.previsao_entrega_atual or pedido.previsao_entrega_original) else "Previsão de entrega",
                "condicao_pagamento": pedido.condicao_pagamento or "",
            },
        )

    prefixos = ["COMPRA_PARCELA:", "COMPRA_PEDIDO:"]
    contas_antigas = TituloPagar.objects.filter(origem=TituloPagar.Origem.COMPRA, pedido=pedido)
    for conta in contas_antigas:
        if conta.referencia_externa and any(conta.referencia_externa.startswith(p) for p in prefixos):
            if conta.referencia_externa not in refs_ativas and conta.status != TituloPagar.Status.PAGO:
                conta.status = TituloPagar.Status.CANCELADO
                conta.save(update_fields=["status", "atualizado_em"])

    # Previsões antigas de compras passam a ser substituídas pelas próprias contas futuras.
    PrevisaoFinanceira.objects.filter(pedido=pedido, origem=PrevisaoFinanceira.Origem.COMPRA).update(ativa=False)
    return TituloPagar.objects.filter(referencia_externa__in=refs_ativas)


# Alias para chamadas legadas.
sincronizar_previsoes_pedido = sincronizar_contas_pedido


def _valor_parcela_gf(fluxo, parcela):
    if parcela.valor is not None:
        return parcela.valor
    if parcela.percentual is not None:
        return (fluxo.valor_total_negociado * parcela.percentual / Decimal("100")).quantize(Decimal("0.01"))
    return Decimal("0")


@transaction.atomic
def sincronizar_contas_grande_fornecedor(fluxo):
    parcelas = list(fluxo.parcelas.prefetch_related("rateios").all().order_by("ordem", "id"))
    total_parcelas = len(parcelas)
    refs_ativas = []
    fornecedor_principal = fluxo.fornecedor_escolhido
    nome_principal = _nome_fornecedor(fornecedor_principal)

    for indice, parcela in enumerate(parcelas, start=1):
        valor_parcela = _valor_parcela_gf(fluxo, parcela)
        rateios = list(parcela.rateios.all())
        cancelado = parcela.status == ParcelaGrandeFornecedor.Status.CANCELADO
        liberado = parcela.status == ParcelaGrandeFornecedor.Status.LIBERADO

        if rateios:
            distribuido = Decimal("0")
            for rateio in rateios:
                distribuido += rateio.valor
                referencia = f"GF_RATEIO:{rateio.pk}"
                refs_ativas.append(referencia)
                _upsert_conta_integrada(
                    referencia=referencia,
                    cancelado=cancelado,
                    liberado=liberado,
                    defaults={
                        "origem": TituloPagar.Origem.GRANDE_FORNECEDOR,
                        "origem_detalhe": f"GF {fluxo.processo.numero}",
                        "fornecedor": None,
                        "beneficiario_nome": rateio.beneficiario_nome,
                        "beneficiario_documento": rateio.documento,
                        "obra": fluxo.processo.obra,
                        "descricao": f"{fluxo.processo.numero} · {parcela.descricao}",
                        "valor_original": rateio.valor,
                        "vencimento": parcela.data_prevista,
                        "parcela_ordem": indice,
                        "parcela_total": total_parcelas,
                        "parcela_descricao": parcela.descricao,
                        "gatilho_pagamento": parcela.get_gatilho_display(),
                        "condicao_pagamento": fluxo.condicao_pagamento_resumo or "",
                        "observacao": rateio.observacao,
                    },
                )

            saldo = max(valor_parcela - distribuido, Decimal("0"))
            ref_saldo = f"GF_SALDO:{parcela.pk}"
            if saldo > 0:
                refs_ativas.append(ref_saldo)
                _upsert_conta_integrada(
                    referencia=ref_saldo,
                    cancelado=cancelado,
                    liberado=False,
                    defaults={
                        "origem": TituloPagar.Origem.GRANDE_FORNECEDOR,
                        "origem_detalhe": f"GF {fluxo.processo.numero}",
                        "fornecedor": None,
                        "beneficiario_nome": "Beneficiário não definido",
                        "obra": fluxo.processo.obra,
                        "descricao": f"{fluxo.processo.numero} · saldo a distribuir · {parcela.descricao}",
                        "valor_original": saldo,
                        "vencimento": parcela.data_prevista,
                        "parcela_ordem": indice,
                        "parcela_total": total_parcelas,
                        "parcela_descricao": parcela.descricao,
                        "gatilho_pagamento": parcela.get_gatilho_display(),
                        "condicao_pagamento": fluxo.condicao_pagamento_resumo or "",
                    },
                )
            else:
                TituloPagar.objects.filter(referencia_externa=ref_saldo).exclude(status=TituloPagar.Status.PAGO).update(status=TituloPagar.Status.CANCELADO)
        elif valor_parcela > 0:
            referencia = f"GF_PARCELA:{parcela.pk}"
            refs_ativas.append(referencia)
            _upsert_conta_integrada(
                referencia=referencia,
                cancelado=cancelado,
                liberado=liberado,
                defaults={
                    "origem": TituloPagar.Origem.GRANDE_FORNECEDOR,
                    "origem_detalhe": f"GF {fluxo.processo.numero}",
                    "fornecedor": fornecedor_principal,
                    "beneficiario_nome": nome_principal or "Beneficiário não definido",
                    "obra": fluxo.processo.obra,
                    "descricao": f"{fluxo.processo.numero} · {parcela.descricao}",
                    "valor_original": valor_parcela,
                    "vencimento": parcela.data_prevista,
                    "parcela_ordem": indice,
                    "parcela_total": total_parcelas,
                    "parcela_descricao": parcela.descricao,
                    "gatilho_pagamento": parcela.get_gatilho_display(),
                    "condicao_pagamento": fluxo.condicao_pagamento_resumo or "",
                },
            )

    for conta in TituloPagar.objects.filter(origem=TituloPagar.Origem.GRANDE_FORNECEDOR, origem_detalhe=f"GF {fluxo.processo.numero}"):
        if conta.referencia_externa and conta.referencia_externa not in refs_ativas and conta.status != TituloPagar.Status.PAGO:
            conta.status = TituloPagar.Status.CANCELADO
            conta.save(update_fields=["status", "atualizado_em"])

    return TituloPagar.objects.filter(referencia_externa__in=refs_ativas)


@transaction.atomic
def sincronizar_conta_mao_obra(
    *,
    referencia,
    beneficiario_nome,
    obra,
    valor,
    vencimento,
    descricao,
    documento_numero="",
    beneficiario_documento="",
    fornecedor=None,
    parcela_ordem=None,
    parcela_total=None,
    parcela_descricao="",
    liberada=True,
    cancelada=False,
):
    """Ponto único de integração do módulo de M.O.

    O módulo que aprova a medição/solicitação deve chamar esta função com uma
    referência estável (ex.: `MEDICAO:123`). Chamadas repetidas atualizam a
    mesma Conta a Pagar, sem duplicação.
    """
    if not referencia:
        raise ValueError("A integração de M.O. exige uma referência externa estável.")
    return _upsert_conta_integrada(
        referencia=f"MO:{referencia}",
        cancelado=cancelada,
        liberado=liberada,
        defaults={
            "origem": TituloPagar.Origem.MAO_OBRA,
            "origem_detalhe": str(referencia),
            "fornecedor": fornecedor,
            "beneficiario_nome": beneficiario_nome,
            "beneficiario_documento": beneficiario_documento,
            "obra": obra,
            "descricao": descricao,
            "documento_numero": documento_numero,
            "valor_original": valor,
            "vencimento": vencimento,
            "parcela_ordem": parcela_ordem,
            "parcela_total": parcela_total,
            "parcela_descricao": parcela_descricao,
            "gatilho_pagamento": "Medição / solicitação aprovada",
        },
    )


@transaction.atomic
def sincronizar_todas_integracoes():
    total_compras = 0
    total_gf = 0
    for pedido in PedidoCompra.objects.exclude(status=PedidoCompra.Status.CANCELADO).prefetch_related("parcelas_previstas"):
        total_compras += sincronizar_contas_pedido(pedido).count()
    for fluxo in GrandeFornecedorProcesso.objects.select_related("processo", "fornecedor_escolhido").prefetch_related("parcelas__rateios"):
        total_gf += sincronizar_contas_grande_fornecedor(fluxo).count()
    return {"compras": total_compras, "grandes_fornecedores": total_gf}


def _data_segura(ano, mes, dia):
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(max(dia, 1), ultimo))


@transaction.atomic
def gerar_previsoes_recorrentes(inicio, fim, usuario=None):
    """Mantido somente para despesas ainda não formalizadas como Conta a Pagar."""
    criadas = 0
    recorrentes = DespesaRecorrente.objects.filter(ativo=True, inicio__lte=fim).order_by("id")
    for despesa in recorrentes:
        cursor = date(inicio.year, inicio.month, 1)
        while cursor <= fim:
            vencimento = _data_segura(cursor.year, cursor.month, despesa.dia_vencimento)
            if vencimento >= despesa.inicio and (not despesa.fim or vencimento <= despesa.fim) and inicio <= vencimento <= fim:
                _, criada = PrevisaoFinanceira.objects.get_or_create(
                    despesa_recorrente=despesa,
                    competencia=date(cursor.year, cursor.month, 1),
                    defaults={
                        "origem": PrevisaoFinanceira.Origem.RECORRENTE,
                        "certeza": PrevisaoFinanceira.Certeza.PREVISTO,
                        "descricao": despesa.descricao,
                        "obra": despesa.obra,
                        "fornecedor": despesa.fornecedor,
                        "plano_financeiro": despesa.plano_financeiro,
                        "data_prevista": vencimento,
                        "valor_previsto": despesa.valor,
                        "ativa": True,
                        "criado_por": usuario,
                    },
                )
                criadas += int(criada)
            cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return criadas
