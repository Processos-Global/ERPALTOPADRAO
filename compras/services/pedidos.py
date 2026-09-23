from collections import defaultdict
import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from compras.models import (
    HistoricoPrevisaoPedido,
    PedidoCompra,
    PedidoCompraItem,
    ParcelaPrevistaPedido,
    ProcessoCompra,
    RecebimentoPedido,
    RecebimentoPedidoItem,
)

from .auditoria import registrar_evento
from .comercial import (
    condicao_pagamento_final_fornecedor,
    desconto_proposta_final_fornecedor,
    frete_final_fornecedor,
    prazo_final_fornecedor,
    quantizar_moeda,
)
from .integracao_planejamento import limpar_data_real, sincronizar_data_real
from .grande_fornecedor_status import status_por_recebimento
from .historico_suprimentos import remover_historico_processo, sincronizar_historico_processo
from .numeracao import gerar_numero
from .valores import calcular_total_proposta

ZERO = Decimal("0")


def _quantidade_parcelas_da_condicao(condicao):
    """Extrai o número de parcelas da condição comercial salva em Compras."""
    texto = (condicao or "").strip()
    if not texto:
        return 1

    match = re.search(r"parcelado\s+em\s+(\d+)x", texto, flags=re.IGNORECASE)
    if match:
        return max(int(match.group(1)), 1)

    # Condições padronizadas como 30/60 ou 30/60/90 representam 2 e 3 parcelas.
    antes_dias = re.sub(r"\s*dias?\s*$", "", texto, flags=re.IGNORECASE)
    if re.fullmatch(r"\d+(?:\s*/\s*\d+)+", antes_dias):
        return len(re.findall(r"\d+", antes_dias))

    return 1


def _valores_parcelados(total, quantidade):
    total = Decimal(total or 0).quantize(Decimal("0.01"))
    quantidade = max(int(quantidade or 1), 1)
    base = (total / quantidade).quantize(Decimal("0.01"))
    valores = [base for _ in range(quantidade)]
    diferenca = total - sum(valores, Decimal("0"))
    valores[0] += diferenca
    return valores


def sincronizar_parcelas_previstas_condicao(pedido):
    """Mantém o parcelamento estruturado do pedido coerente com a condição comercial.

    O fluxo de Cotação/Negociação continua exatamente igual. Esta função apenas
    transforma condições como ``Parcelado em 3x`` e ``30/60/90 dias`` em registros
    de ParcelaPrevistaPedido, que o Financeiro já sabe consumir.
    """
    quantidade = _quantidade_parcelas_da_condicao(pedido.condicao_pagamento)
    atuais = list(pedido.parcelas_previstas.order_by("ordem", "id"))

    if quantidade <= 1:
        if atuais:
            pedido.parcelas_previstas.all().delete()
        return []

    valores = _valores_parcelados(pedido.valor_total, quantidade)

    # Mantém os mesmos IDs quando a quantidade de parcelas não mudou. Isso é
    # importante porque o Financeiro usa o ID da parcela como chave idempotente.
    if len(atuais) == quantidade:
        for indice, (parcela, valor) in enumerate(zip(atuais, valores), start=1):
            alterados = []
            descricao = f"Parcela {indice}/{quantidade}"
            if parcela.ordem != indice:
                parcela.ordem = indice
                alterados.append("ordem")
            if parcela.valor != valor:
                parcela.valor = valor
                alterados.append("valor")
            if parcela.percentual is not None:
                parcela.percentual = None
                alterados.append("percentual")
            if parcela.descricao != descricao:
                parcela.descricao = descricao
                alterados.append("descricao")
            if parcela.evento_gatilho != ParcelaPrevistaPedido.Gatilho.DATA:
                parcela.evento_gatilho = ParcelaPrevistaPedido.Gatilho.DATA
                alterados.append("evento_gatilho")
            if alterados:
                parcela.save(update_fields=alterados)
        return atuais

    # A quantidade comercial mudou: substitui a estrutura para refletir a nova
    # condição. Na sincronização seguinte o Financeiro cancela as referências
    # antigas ainda não pagas e cria as novas parcelas.
    pedido.parcelas_previstas.all().delete()
    parcelas = [
        ParcelaPrevistaPedido(
            pedido=pedido,
            ordem=indice,
            valor=valor,
            evento_gatilho=ParcelaPrevistaPedido.Gatilho.DATA,
            descricao=f"Parcela {indice}/{quantidade}",
        )
        for indice, valor in enumerate(valores, start=1)
    ]
    ParcelaPrevistaPedido.objects.bulk_create(parcelas)
    return parcelas


def _sincronizar_grande_fornecedor_pedido(pedido):
    """Sincroniza recebimentos do PedidoCompra com os microitens do fluxo especial.

    O PedidoCompra continua sendo o documento comercial e a origem dos
    recebimentos/NFs. O status operacional, entretanto, pertence a cada
    GrandeFornecedorItem e pode evoluir de forma independente.
    """
    if not getattr(pedido.processo, "fluxo_grande_fornecedor", False):
        return
    try:
        fluxo = pedido.processo.grande_fornecedor
    except Exception:
        return

    if pedido.status in {
        PedidoCompra.Status.CONFIRMADO,
        PedidoCompra.Status.EM_PRODUCAO,
        PedidoCompra.Status.PRONTO_EXPEDICAO,
        PedidoCompra.Status.EM_TRANSPORTE,
        PedidoCompra.Status.ENTREGA_PARCIAL,
        PedidoCompra.Status.ENTREGUE,
    } and not fluxo.fornecedor_confirmado_em:
        fluxo.fornecedor_confirmado_em = timezone.now()
        fluxo.save(update_fields=["fornecedor_confirmado_em", "atualizado_em"])

    for pedido_item in pedido.itens.select_related("item_grande_fornecedor").all():
        try:
            micro = pedido_item.item_grande_fornecedor
        except Exception:
            continue
        novo_status = status_por_recebimento(
            pedido_item.quantidade,
            pedido_item.quantidade_recebida,
            micro.status,
        )
        if pedido.status == PedidoCompra.Status.CANCELADO:
            novo_status = micro.Status.CANCELADO
        micro.quantidade_recebida = pedido_item.quantidade_recebida
        micro.status = novo_status
        micro.save(update_fields=["quantidade_recebida", "status", "atualizado_em"])


def _previsao_por_prazo(prazo_dias):
    if prazo_dias is None:
        return None
    return timezone.localdate() + timedelta(days=int(prazo_dias))


def _sincronizar_status_contratacao_processo(*, processo, usuario):
    """Mantém o processo coerente com a confirmação/cancelamento dos pedidos."""
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO}:
        return p

    # No fluxo de Grande Fornecedor, a aprovação do gestor seguida da emissão
    # dos pedidos é o marco de contratação. O acompanhamento posterior passa
    # a ser individual por item no Planejamento.
    if p.fluxo_grande_fornecedor:
        pedidos_ativos_gf = list(
            p.pedidos.exclude(status=PedidoCompra.Status.CANCELADO).only("id")
        )
        if pedidos_ativos_gf:
            mudou = p.status != p.Status.CONTRATADO or p.etapa_atual != p.Etapa.CONTRATADO
            p.status = p.Status.CONTRATADO
            p.etapa_atual = p.Etapa.CONTRATADO
            if not p.data_contratacao_concluida:
                p.data_contratacao_concluida = timezone.now()
            p.save(update_fields=[
                "status", "etapa_atual", "data_contratacao_concluida", "atualizado_em"
            ])
            if mudou:
                sincronizar_data_real(p, "CONTRATACAO", usuario)
                registrar_evento(
                    p,
                    "GF_CONTRATACAO_CONCLUIDA",
                    usuario,
                    "Pedidos de Grande Fornecedor gerados após aprovação do gestor.",
                )
            sincronizar_historico_processo(p)
            return p

    fornecedores_adjudicados = set(
        p.adjudicacoes.filter(cancelada=False).values_list("cotacao__fornecedor_id", flat=True)
    )
    pedidos_ativos = list(
        p.pedidos.exclude(status=PedidoCompra.Status.CANCELADO).only(
            "id", "fornecedor_id", "status"
        )
    )
    por_fornecedor = defaultdict(list)
    for pedido in pedidos_ativos:
        por_fornecedor[pedido.fornecedor_id].append(pedido)

    status_confirmados = {
        PedidoCompra.Status.CONFIRMADO,
        PedidoCompra.Status.EM_PRODUCAO,
        PedidoCompra.Status.PRONTO_EXPEDICAO,
        PedidoCompra.Status.EM_TRANSPORTE,
        PedidoCompra.Status.ENTREGA_PARCIAL,
        PedidoCompra.Status.ENTREGUE,
    }
    todos_confirmados = bool(fornecedores_adjudicados) and all(
        any(pedido.status in status_confirmados for pedido in por_fornecedor.get(fornecedor_id, []))
        for fornecedor_id in fornecedores_adjudicados
    )

    if todos_confirmados:
        mudou = p.status != p.Status.CONTRATADO or p.etapa_atual != p.Etapa.CONTRATADO
        p.status = p.Status.CONTRATADO
        p.etapa_atual = p.Etapa.CONTRATADO
        if not p.data_contratacao_concluida:
            p.data_contratacao_concluida = timezone.now()
        p.save(update_fields=[
            "status", "etapa_atual", "data_contratacao_concluida", "atualizado_em"
        ])
        if mudou:
            sincronizar_data_real(p, "CONTRATACAO", usuario)
            registrar_evento(
                p,
                "CONTRATACAO_CONCLUIDA",
                usuario,
                "Todos os pedidos ativos foram confirmados pelos fornecedores. Processo contratado.",
            )

        # Sempre sincroniza para manter valor/fornecedor do histórico coerentes
        # caso um pedido já contratado seja recalculado.
        sincronizar_historico_processo(p)
        return p

    estava_contratado = (
        p.status == p.Status.CONTRATADO
        or p.etapa_atual == p.Etapa.CONTRATADO
        or p.data_contratacao_concluida is not None
    )
    p.status = p.Status.EM_CONTRATACAO
    p.etapa_atual = p.Etapa.CONTRATACAO
    p.data_contratacao_concluida = None
    p.save(update_fields=[
        "status", "etapa_atual", "data_contratacao_concluida", "atualizado_em"
    ])
    if estava_contratado:
        limpar_data_real(p, "CONTRATACAO")
        remover_historico_processo(p)
        registrar_evento(
            p,
            "CONTRATACAO_REABERTA",
            usuario,
            "Processo retornou para Em contratação porque nem todos os fornecedores adjudicados possuem pedido ativo confirmado.",
        )
    return p


@transaction.atomic
def gerar_pedidos(processo, usuario, local_entrega=""):
    """
    Gera um pedido por fornecedor adjudicado.

    A operação é idempotente: se já existir pedido ativo para determinado
    fornecedor/processo, ele é reutilizado e não é duplicado.
    Formalização contratual é opcional e, quando existir, prevalece nos campos
    de condição/prazo/local.
    """
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.status not in {p.Status.APROVADO, p.Status.EM_CONTRATACAO, p.Status.CONTRATADO}:
        raise ValidationError("O processo precisa estar aprovado para gerar pedidos.")

    adjudicacoes = list(
        p.adjudicacoes
        .filter(cancelada=False)
        .select_related("cotacao__fornecedor", "necessidade", "item_cotado")
        .order_by("cotacao__fornecedor_id", "id")
    )
    if not adjudicacoes:
        raise ValidationError("Não existem itens adjudicados para gerar pedidos.")

    grupos = defaultdict(list)
    for adjudicacao in adjudicacoes:
        grupos[adjudicacao.cotacao.fornecedor_id].append(adjudicacao)

    pedidos_resultado = []
    for fornecedor_id, grupo in grupos.items():
        fornecedor = grupo[0].cotacao.fornecedor
        formalizacao = p.contratacoes.filter(fornecedor_id=fornecedor_id, cancelada=False).first()

        # Todos os itens aprovados do mesmo fornecedor compõem um único pedido.
        # Frete, condição e prazo também são calculados uma única vez por fornecedor.
        subtotal = quantizar_moeda(sum((a.valor_bruto for a in grupo), ZERO))
        descontos_itens = quantizar_moeda(sum((a.desconto_final or ZERO for a in grupo), ZERO))
        desconto_proposta = desconto_proposta_final_fornecedor(p, fornecedor_id)
        descontos = quantizar_moeda(descontos_itens + desconto_proposta)
        frete = frete_final_fornecedor(p, fornecedor_id)
        total = calcular_total_proposta(subtotal=subtotal, desconto=descontos, frete=frete)

        condicao = (
            (formalizacao.condicao_pagamento or "").strip()
            if formalizacao
            else ""
        ) or condicao_pagamento_final_fornecedor(p, fornecedor_id)

        prazo = formalizacao.prazo_entrega_dias if formalizacao else prazo_final_fornecedor(p, fornecedor_id)
        previsao = formalizacao.previsao_entrega if formalizacao else _previsao_por_prazo(prazo)
        destino = ((formalizacao.local_entrega or "").strip() if formalizacao else "") or (local_entrega or "").strip()

        existente = (
            PedidoCompra.objects
            .select_for_update()
            .filter(processo=p, fornecedor_id=fornecedor_id)
            .exclude(status=PedidoCompra.Status.CANCELADO)
            .order_by("id")
            .first()
        )
        if existente:
            necessidades_existentes = set(
                existente.itens.values_list("necessidade_id", flat=True)
            )
            faltantes = [
                adjudicacao
                for adjudicacao in grupo
                if adjudicacao.necessidade_id not in necessidades_existentes
            ]

            # Se a rotina for executada novamente e houver novos itens aprovados
            # para o MESMO fornecedor, eles entram no pedido já existente em vez
            # de gerar um segundo pedido para esse fornecedor.
            if faltantes:
                if existente.recebimentos.exists():
                    raise ValidationError(
                        f"O pedido {existente.numero} já possui recebimentos e não pode "
                        f"receber novos itens automaticamente. Revise o processo antes de continuar."
                    )
                PedidoCompraItem.objects.bulk_create([
                    PedidoCompraItem(
                        pedido=existente,
                        necessidade=a.necessidade,
                        descricao=a.necessidade.descricao,
                        especificacao=a.necessidade.especificacao,
                        unidade=a.necessidade.unidade,
                        quantidade=a.quantidade,
                        valor_unitario=a.valor_unitario_final,
                        desconto=a.desconto_final or ZERO,
                        valor_total=quantizar_moeda(a.valor_total),
                    )
                    for a in faltantes
                ])

                existente.subtotal = subtotal
                existente.descontos = descontos
                existente.frete = frete
                existente.valor_total = total
                existente.condicao_pagamento = condicao
                if existente.previsao_entrega_original is None:
                    existente.previsao_entrega_original = previsao
                existente.previsao_entrega_atual = previsao
                if destino:
                    existente.local_entrega = destino
                existente.save(update_fields=[
                    "subtotal", "descontos", "frete", "valor_total",
                    "condicao_pagamento", "previsao_entrega_original",
                    "previsao_entrega_atual", "local_entrega", "atualizado_em",
                ])
                registrar_evento(
                    p,
                    "PEDIDO_ATUALIZADO",
                    usuario,
                    f"Pedido {existente.numero} atualizado com novos itens do fornecedor {fornecedor.nome}.",
                    {"pedido_id": existente.pk, "itens_adicionados": len(faltantes)},
                )

            sincronizar_parcelas_previstas_condicao(existente)
            # O post_save do PedidoCompra sincroniza as parcelas já estruturadas
            # com o Financeiro.
            existente.save(update_fields=["atualizado_em"])
            pedidos_resultado.append(existente)
            continue

        pedido = PedidoCompra.objects.create(
            numero=gerar_numero("PEDIDO"),
            processo=p,
            obra=p.obra,
            fornecedor=fornecedor,
            subtotal=subtotal,
            descontos=descontos,
            frete=frete,
            valor_total=total,
            condicao_pagamento=condicao,
            previsao_entrega_original=previsao,
            previsao_entrega_atual=previsao,
            local_entrega=destino,
            responsavel=usuario,
        )

        PedidoCompraItem.objects.bulk_create([
            PedidoCompraItem(
                pedido=pedido,
                necessidade=a.necessidade,
                descricao=a.necessidade.descricao,
                especificacao=a.necessidade.especificacao,
                unidade=a.necessidade.unidade,
                quantidade=a.quantidade,
                valor_unitario=a.valor_unitario_final,
                desconto=a.desconto_final or ZERO,
                valor_total=quantizar_moeda(a.valor_total),
            )
            for a in grupo
        ])
        sincronizar_parcelas_previstas_condicao(pedido)
        # O primeiro post_save ocorre na criação do pedido, antes das parcelas.
        # Este save final dispara a integração financeira com a estrutura completa.
        pedido.save(update_fields=["atualizado_em"])
        pedidos_resultado.append(pedido)
        registrar_evento(
            p,
            "PEDIDO_CRIADO",
            usuario,
            f"Pedido {pedido.numero} criado para {fornecedor.nome}.",
            {"pedido_id": pedido.pk, "valor_total": str(total)},
        )

    # Emitir o pedido inicia a contratação. O aceite do fornecedor é o marco
    # que conclui a contratação do processo.
    _sincronizar_status_contratacao_processo(processo=p, usuario=usuario)

    return pedidos_resultado


# Status logísticos que o usuário pode informar manualmente.
# ENTREGA_PARCIAL e ENTREGUE são estados derivados exclusivamente dos
# recebimentos registrados, evitando divergência entre status e quantidades.
TRANSICOES_STATUS = {
    PedidoCompra.Status.PEDIDO_EMITIDO: {
        PedidoCompra.Status.CONFIRMADO,
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.CONFIRMADO: {
        PedidoCompra.Status.EM_PRODUCAO,
        PedidoCompra.Status.PRONTO_EXPEDICAO,
        PedidoCompra.Status.EM_TRANSPORTE,
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.EM_PRODUCAO: {
        PedidoCompra.Status.PRONTO_EXPEDICAO,
        PedidoCompra.Status.EM_TRANSPORTE,
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.PRONTO_EXPEDICAO: {
        PedidoCompra.Status.EM_TRANSPORTE,
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.EM_TRANSPORTE: {
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.ENTREGA_PARCIAL: {
        PedidoCompra.Status.CANCELADO,
    },
    PedidoCompra.Status.ENTREGUE: set(),
    PedidoCompra.Status.CANCELADO: set(),
}


STATUS_DERIVADOS_RECEBIMENTO = {
    PedidoCompra.Status.ENTREGA_PARCIAL,
    PedidoCompra.Status.ENTREGUE,
}


def transicoes_status_permitidas(pedido):
    """Retorna apenas as transições manuais válidas, na ordem visual do model."""
    permitidos = TRANSICOES_STATUS.get(pedido.status, set())
    return [
        (valor, rotulo)
        for valor, rotulo in PedidoCompra.Status.choices
        if valor in permitidos and valor != PedidoCompra.Status.CANCELADO
    ]


@transaction.atomic
def atualizar_status_pedido(*, pedido, novo_status, usuario, observacao=""):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if novo_status not in PedidoCompra.Status.values:
        raise ValidationError("Status de pedido inválido.")
    if novo_status in STATUS_DERIVADOS_RECEBIMENTO:
        raise ValidationError(
            "Entrega parcial e Entregue são definidos automaticamente ao registrar o recebimento."
        )
    if novo_status not in TRANSICOES_STATUS.get(p.status, set()):
        raise ValidationError(f"Não é permitido alterar de {p.get_status_display()} para {PedidoCompra.Status(novo_status).label}.")
    if novo_status == PedidoCompra.Status.CANCELADO:
        return cancelar_pedido(pedido=p, usuario=usuario, motivo=observacao)
    p.status = novo_status
    p.save(update_fields=["status", "atualizado_em"])
    _sincronizar_grande_fornecedor_pedido(p)
    registrar_evento(p.processo, "STATUS_PEDIDO", usuario, f"Pedido {p.numero}: {p.get_status_display()}.", {"pedido_id": p.pk})
    _sincronizar_status_contratacao_processo(processo=p.processo, usuario=usuario)
    return p


@transaction.atomic
def atualizar_previsao_entrega(*, pedido, previsao_nova, usuario, motivo=""):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if p.status in {PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE}:
        raise ValidationError("A previsão não pode ser alterada neste status.")
    if not previsao_nova:
        raise ValidationError("Informe a nova previsão de entrega.")
    anterior = p.previsao_entrega_atual
    HistoricoPrevisaoPedido.objects.create(
        pedido=p,
        previsao_anterior=anterior,
        previsao_nova=previsao_nova,
        motivo=(motivo or "").strip(),
        alterado_por=usuario,
    )
    if p.previsao_entrega_original is None:
        p.previsao_entrega_original = previsao_nova
    p.previsao_entrega_atual = previsao_nova
    p.save(update_fields=["previsao_entrega_original", "previsao_entrega_atual", "atualizado_em"])
    registrar_evento(p.processo, "PREVISAO_PEDIDO", usuario, f"Previsão do pedido {p.numero} alterada para {previsao_nova:%d/%m/%Y}.")
    return p


@transaction.atomic
def registrar_recebimento(
    *,
    pedido,
    quantidades,
    valores_itens,
    usuario,
    numero_nota_fiscal,
    valor_total_nota,
    arquivo_nota_fiscal,
    observacao="",
    dados_fiscais_opcionais=False,
):
    """
    Registra uma entrega física vinculada obrigatoriamente à respectiva Nota Fiscal.

    quantidades: dict {pedido_item_id: quantidade_recebida_nesta_entrega}
    valores_itens: dict {pedido_item_id: valor_total_do_item_na_nota}
    """
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if p.status in {PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE}:
        raise ValidationError("Este pedido não aceita novos recebimentos.")

    numero_nota_fiscal = (numero_nota_fiscal or "").strip() or None
    if not dados_fiscais_opcionais:
        if not numero_nota_fiscal:
            raise ValidationError("Informe o número da Nota Fiscal.")
        if not arquivo_nota_fiscal:
            raise ValidationError("Anexe o arquivo da Nota Fiscal.")
    if numero_nota_fiscal and RecebimentoPedido.objects.filter(
        pedido=p, numero_nota_fiscal=numero_nota_fiscal
    ).exists():
        raise ValidationError(f"A Nota Fiscal {numero_nota_fiscal} já foi registrada neste pedido.")

    total_nota = None
    if valor_total_nota not in (None, ""):
        try:
            total_nota = Decimal(str(valor_total_nota).replace(",", "."))
        except Exception as exc:
            raise ValidationError("Informe um valor total válido para a Nota Fiscal.") from exc
        if total_nota <= ZERO:
            raise ValidationError("O valor total da Nota Fiscal deve ser maior que zero.")
    elif not dados_fiscais_opcionais:
        raise ValidationError("Informe um valor total válido para a Nota Fiscal.")

    itens_receber = []
    for item in p.itens.select_for_update().all():
        valor_qtd = quantidades.get(item.pk, ZERO)
        try:
            quantidade = Decimal(str(valor_qtd or ZERO).replace(",", "."))
        except Exception as exc:
            raise ValidationError(f"Quantidade inválida para {item.descricao}.") from exc

        if quantidade < ZERO:
            raise ValidationError("Quantidade recebida não pode ser negativa.")
        if quantidade == ZERO:
            continue
        # O recebimento físico pode ultrapassar a quantidade originalmente
        # pedida. O pedido continua preservando a quantidade contratada e o
        # excedente fica registrado no recebimento/NF para conferência e
        # pagamento do que efetivamente foi entregue.

        valor_informado = valores_itens.get(item.pk)
        valor_recebido = None
        if valor_informado not in (None, ""):
            try:
                valor_recebido = Decimal(str(valor_informado).replace(",", "."))
            except Exception as exc:
                raise ValidationError(f"Valor recebido inválido para {item.descricao}.") from exc
            if valor_recebido <= ZERO:
                raise ValidationError(f"O valor recebido de {item.descricao} deve ser maior que zero.")
            valor_recebido = quantizar_moeda(valor_recebido)
        elif not dados_fiscais_opcionais:
            raise ValidationError(f"Informe o valor recebido do item {item.descricao}.")

        itens_receber.append((item, quantidade, valor_recebido))

    if not itens_receber:
        raise ValidationError("Informe ao menos uma quantidade recebida maior que zero.")

    recebimento = RecebimentoPedido.objects.create(
        pedido=p,
        numero_nota_fiscal=numero_nota_fiscal,
        arquivo_nota_fiscal=arquivo_nota_fiscal,
        valor_total_nota=quantizar_moeda(total_nota) if total_nota is not None else None,
        usuario=usuario,
        observacao=(observacao or "").strip(),
    )

    excedentes = []
    for item, quantidade, valor_recebido in itens_receber:
        quantidade_antes = item.quantidade_recebida
        item.quantidade_recebida += quantidade
        item.save(update_fields=["quantidade_recebida"])
        RecebimentoPedidoItem.objects.create(
            recebimento=recebimento,
            item_pedido=item,
            quantidade=quantidade,
            valor_recebido=valor_recebido,
        )

        excedente_antes = max(quantidade_antes - item.quantidade, ZERO)
        excedente_depois = max(item.quantidade_recebida - item.quantidade, ZERO)
        excedente_nesta_entrega = excedente_depois - excedente_antes
        if excedente_nesta_entrega > ZERO:
            excedentes.append({
                "item_id": item.pk,
                "descricao": item.descricao,
                "quantidade": str(excedente_nesta_entrega),
                "unidade": item.unidade,
            })

    completo = not p.itens.filter(quantidade_recebida__lt=models.F("quantidade")).exists()
    if completo:
        p.status = PedidoCompra.Status.ENTREGUE
        p.recebido_em = timezone.now()
        p.recebido_por = usuario
        p.save(update_fields=["status", "recebido_em", "recebido_por", "atualizado_em"])
    else:
        p.status = PedidoCompra.Status.ENTREGA_PARCIAL
        p.save(update_fields=["status", "atualizado_em"])

    _sincronizar_grande_fornecedor_pedido(p)

    registrar_evento(
        p.processo,
        "RECEBIMENTO_PEDIDO",
        usuario,
        f"Recebimento registrado no pedido {p.numero}" + (f" - NF {numero_nota_fiscal}." if numero_nota_fiscal else "."),
        {
            "pedido_id": p.pk,
            "recebimento_id": recebimento.pk,
            "numero_nota_fiscal": numero_nota_fiscal,
            "valor_total_nota": str(recebimento.valor_total_nota),
            "excedentes": excedentes,
        },
    )
    return recebimento


@transaction.atomic
def cancelar_pedido(*, pedido, usuario, motivo):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento do pedido.")
    if p.status == PedidoCompra.Status.ENTREGUE:
        raise ValidationError("Pedido entregue não pode ser cancelado.")
    if p.status == PedidoCompra.Status.CANCELADO:
        return p
    p.status = PedidoCompra.Status.CANCELADO
    p.cancelado_por = usuario
    p.cancelado_em = timezone.now()
    p.motivo_cancelamento = motivo
    p.save(update_fields=["status", "cancelado_por", "cancelado_em", "motivo_cancelamento", "atualizado_em"])
    registrar_evento(p.processo, "PEDIDO_CANCELADO", usuario, f"Pedido {p.numero} cancelado: {motivo}", {"pedido_id": p.pk})
    return p