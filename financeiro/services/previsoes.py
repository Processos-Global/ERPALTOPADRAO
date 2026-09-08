import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction

from compras.models import PedidoCompra
from financeiro.models import DespesaRecorrente, PrevisaoFinanceira


def _data_parcela(pedido, parcela):
    if parcela.data_prevista:
        return parcela.data_prevista
    if parcela.dias is not None:
        base = pedido.data
        from datetime import timedelta
        return base + timedelta(days=parcela.dias)
    return pedido.previsao_entrega_atual or pedido.previsao_entrega_original or pedido.data


def _valor_parcela(pedido, parcela):
    if parcela.valor is not None:
        return parcela.valor
    if parcela.percentual is not None:
        return (pedido.valor_total * parcela.percentual / Decimal("100")).quantize(Decimal("0.01"))
    return Decimal("0")


@transaction.atomic
def sincronizar_previsoes_pedido(pedido):
    parcelas = list(pedido.parcelas_previstas.all().order_by("ordem", "id"))
    ids_mantidos = []

    if not parcelas:
        previsao, _ = PrevisaoFinanceira.objects.update_or_create(
            pedido=pedido,
            parcela_pedido=None,
            origem=PrevisaoFinanceira.Origem.COMPRA,
            defaults={
                "certeza": PrevisaoFinanceira.Certeza.CONTRATADO,
                "descricao": f"Pedido {pedido.numero} · {pedido.fornecedor.nome_exibicao}",
                "obra": pedido.obra,
                "fornecedor": pedido.fornecedor,
                "data_prevista": pedido.data,
                "valor_previsto": pedido.valor_total,
                "ativa": pedido.status != PedidoCompra.Status.CANCELADO,
            },
        )
        ids_mantidos.append(previsao.pk)
    else:
        for parcela in parcelas:
            valor = _valor_parcela(pedido, parcela)
            if valor <= 0:
                continue
            previsao, _ = PrevisaoFinanceira.objects.update_or_create(
                parcela_pedido=parcela,
                defaults={
                    "pedido": pedido,
                    "origem": PrevisaoFinanceira.Origem.COMPRA,
                    "certeza": PrevisaoFinanceira.Certeza.CONTRATADO,
                    "descricao": parcela.descricao or f"Parcela {parcela.ordem} · {pedido.numero}",
                    "obra": pedido.obra,
                    "fornecedor": pedido.fornecedor,
                    "data_prevista": _data_parcela(pedido, parcela),
                    "valor_previsto": valor,
                    "ativa": pedido.status != PedidoCompra.Status.CANCELADO,
                },
            )
            ids_mantidos.append(previsao.pk)

    pedido.previsoes_financeiras.exclude(pk__in=ids_mantidos).filter(
        origem=PrevisaoFinanceira.Origem.COMPRA,
        titulos_gerados__isnull=True,
    ).update(ativa=False)
    return pedido.previsoes_financeiras.filter(pk__in=ids_mantidos)


def _data_segura(ano, mes, dia):
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(max(dia, 1), ultimo))


@transaction.atomic
def gerar_previsoes_recorrentes(inicio, fim, usuario=None):
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
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)
    return criadas
