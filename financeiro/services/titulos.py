from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from compras.models import PedidoCompra
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.numeracao import gerar_numero
from financeiro.services.notificacoes import notificar_aprovadores
from financeiro.services.regras import distribuir_valor_parcelas


def bloquear_titulo(titulo):
    """Dentro de uma transação, usa a ordem de bloqueios da integração de Compras."""
    origem = TituloPagar.objects.values("pedido_id", "recebimento_id").get(pk=titulo.pk)
    vinculo = Q(titulo_id=titulo.pk)
    if origem["recebimento_id"]:
        vinculo |= Q(recebimento_id=origem["recebimento_id"])
    liberacoes = LiberacaoFinanceiraPedido.objects.filter(vinculo)
    pedido_id = origem["pedido_id"] or liberacoes.values_list("pedido_id", flat=True).first()
    liberacao = None
    if pedido_id:
        PedidoCompra.objects.select_for_update().get(pk=pedido_id)
        liberacao = liberacoes.filter(pedido_id=pedido_id).order_by("pk").select_for_update().first()
    return TituloPagar.objects.select_for_update().get(pk=titulo.pk), liberacao


def reabrir_aprovacao(titulo, *, usuario, motivo):
    """Invalida o ciclo de um título bloqueado e mantém as decisões anteriores."""
    if titulo.status not in {
        TituloPagar.Status.AGUARDANDO_APROVACAO, TituloPagar.Status.APROVADO, TituloPagar.Status.REJEITADO,
    }:
        return
    titulo.ciclo_aprovacao += 1
    titulo.status = TituloPagar.Status.AGUARDANDO_APROVACAO
    titulo.save(update_fields=["ciclo_aprovacao", "status", "atualizado_em"])
    registrar_evento(titulo, "APROVACAO_REABERTA", motivo, usuario, {"ciclo": titulo.ciclo_aprovacao})
    notificar_aprovadores(titulo)


@transaction.atomic
def criar_titulos_manuais(
    *, usuario=None, quantidade_parcelas=1, intervalo_dias=30, solicitacao_avulsa=None, **dados,
):
    """Cria uma ou mais Contas a Pagar manuais.

    Lançamento manual usa fornecedor cadastrado, obra obrigatória e parcelas
    independentes. Cada parcela segue aprovação e pagamento integral próprios.
    """
    materiais = dados.pop("materiais", None)
    dados["classificacao"] = dados.pop("tipo_pagamento", None) or "OUTRO"
    fornecedor = dados.get("fornecedor")
    if fornecedor and not dados.get("beneficiario_nome"):
        dados["beneficiario_nome"] = getattr(fornecedor, "nome_exibicao", None) or str(fornecedor)
    if not dados.get("obra"):
        raise ValueError("A obra é obrigatória para Conta a Pagar.")
    if not fornecedor:
        raise ValueError("Selecione um beneficiário / fornecedor cadastrado.")
    if not dados.get("vencimento"):
        raise ValueError("Informe a data de vencimento.")
    if not (dados.get("especificacao_pagamento") or "").strip():
        raise ValueError("Informe o que está sendo pago.")

    quantidade = int(quantidade_parcelas or 1)
    intervalo = int(intervalo_dias or 30)
    valores = distribuir_valor_parcelas(dados["valor_original"], quantidade)
    primeiro_vencimento = dados.get("vencimento")
    grupo = uuid4().hex[:12] if quantidade > 1 else ""
    criados = []

    for indice, valor in enumerate(valores, start=1):
        parcela_dados = dict(dados)
        parcela_dados["valor_original"] = valor
        if primeiro_vencimento and quantidade > 1:
            parcela_dados["vencimento"] = primeiro_vencimento + timedelta(days=intervalo * (indice - 1))
        titulo = TituloPagar.objects.create(
            numero=gerar_numero("TITULO"),
            origem=TituloPagar.Origem.MANUAL,
            origem_detalhe=(f"Lançamento manual parcelado {grupo}" if grupo else "Lançamento manual"),
            status=TituloPagar.Status.AGUARDANDO_APROVACAO,
            ciclo_aprovacao=1,
            parcela_ordem=indice,
            parcela_total=quantidade,
            parcela_descricao=(f"Parcela {indice}/{quantidade}" if quantidade > 1 else "Pagamento único"),
            criado_por=usuario,
            solicitacao_avulsa=solicitacao_avulsa,
            **parcela_dados,
        )
        if materiais is not None:
            titulo.materiais.set(materiais)
        registrar_evento(
            titulo,
            "CRIADO_MANUAL",
            "Conta a Pagar criada manualmente e enviada para aprovação.",
            usuario,
            {"grupo_manual": grupo, "parcela": indice, "total_parcelas": quantidade},
        )
        criados.append(titulo)
    return criados


@transaction.atomic
def criar_titulo_manual(*, usuario=None, **dados):
    """Compatibilidade: cria pagamento manual único e devolve a Conta criada."""
    return criar_titulos_manuais(usuario=usuario, quantidade_parcelas=1, **dados)[0]


@transaction.atomic
def atualizar_titulo(titulo, *, usuario, dados, motivo="Dados da Conta a Pagar atualizados.", documentos_alterados=False):
    titulo, liberacao = bloquear_titulo(titulo)
    if titulo.esta_pago:
        raise ValueError("Conta paga não pode ser alterada. Estorne o pagamento antes de qualquer ajuste financeiro.")
    dados = dados.copy()
    if liberacao and liberacao.valor_esperado is not None and "obra" in dados and dados["obra"] != titulo.obra:
        raise ValueError("A obra desta conta deve corresponder ao recebimento que a originou.")
    valor_anterior = titulo.valor_liquido
    materiais = dados.pop("materiais", None)
    classificacao = dados.pop("tipo_pagamento", None)
    # A listagem usa beneficiario_nome (snapshot), não o FK fornecedor.
    # Ao trocar o fornecedor de uma conta manual, ambos precisam acompanhar
    # o novo cadastro, mesmo que o formulário envie o snapshot anterior.
    novo_fornecedor = dados.get("fornecedor", titulo.fornecedor)
    fornecedor_alterado = (
        novo_fornecedor is not None
        and getattr(novo_fornecedor, "pk", None) != titulo.fornecedor_id
    )
    if fornecedor_alterado and not titulo.integrada:
        dados["beneficiario_nome"] = (
            getattr(novo_fornecedor, "nome_exibicao", None) or str(novo_fornecedor)
        )
        dados["beneficiario_documento"] = (
            getattr(novo_fornecedor, "documento", "") or ""
        ).strip()
    if not titulo.integrada and classificacao:
        dados['classificacao'] = classificacao
    criticos = {
        "valor_original", "desconto", "juros", "multa", "outros_acrescimos",
        "vencimento", "competencia", "condicao_pagamento", "fornecedor", "plano_financeiro", "beneficiario_nome", "beneficiario_documento",
        "beneficiario_banco", "beneficiario_agencia", "beneficiario_conta_corrente",
        "beneficiario_operacao", "beneficiario_pix", "beneficiario_titular", "obra", "classificacao",
        "descricao", "especificacao_pagamento", "documento_numero", "data_emissao", "meio_pagamento", "arquivo_documento",
    }
    campos_criticos_alterados = []
    for campo, valor in dados.items():
        if campo in {"quantidade_parcelas", "intervalo_dias"}:
            continue
        if getattr(titulo, campo) != valor:
            if campo in criticos:
                campos_criticos_alterados.append(campo)
            setattr(titulo, campo, valor)

    if titulo.fornecedor_id and not titulo.beneficiario_nome:
        titulo.beneficiario_nome = getattr(titulo.fornecedor, "nome_exibicao", None) or str(titulo.fornecedor)

    titulo.save()
    if materiais is not None:
        novos_materiais = list(materiais)
        if set(titulo.materiais.values_list("pk", flat=True)) != {material.pk for material in novos_materiais}:
            campos_criticos_alterados.append("materiais")
            titulo.materiais.set(novos_materiais)
    if documentos_alterados:
        campos_criticos_alterados.append("anexos")
    if campos_criticos_alterados:
        reabrir_aprovacao(titulo, usuario=usuario, motivo="Dados relevantes da Conta a Pagar foram alterados.")
    registrar_evento(titulo, "ATUALIZADO", motivo, usuario, {
        "valor_liquido_anterior": format(valor_anterior, ".2f"),
        "valor_liquido_posterior": format(titulo.valor_liquido, ".2f"),
        "campos_criticos_alterados": sorted(campos_criticos_alterados),
    })
    return titulo


@transaction.atomic
def cancelar_titulo(titulo, *, usuario, motivo):
    titulo, liberacao = bloquear_titulo(titulo)
    if titulo.status == TituloPagar.Status.PAGO or Pagamento.objects.filter(
        titulo=titulo, status=Pagamento.Status.EFETIVADO,
    ).exists():
        raise ValueError("Conta paga não pode ser cancelada. Estorne o pagamento primeiro.")
    if titulo.status == TituloPagar.Status.CANCELADO:
        return titulo
    if liberacao and liberacao.tipo == LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO:
        demais_antecipacoes = LiberacaoFinanceiraPedido.objects.filter(
            pedido_id=liberacao.pedido_id,
            tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
        ).exclude(pk=liberacao.pk).aggregate(total=Sum("valor"))["total"] or 0
        compensado = LiberacaoFinanceiraPedido.objects.filter(
            pedido_id=liberacao.pedido_id,
            tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
            status__in=[LiberacaoFinanceiraPedido.Status.AUTORIZADA, LiberacaoFinanceiraPedido.Status.COMPENSADA],
        ).aggregate(total=Sum("valor_compensado"))["total"] or 0
        if compensado > demais_antecipacoes:
            raise ValueError("Antecipação já compensada em recebimento; reverta a conciliação antes de cancelar.")
    titulo.status = TituloPagar.Status.CANCELADO
    titulo.cancelado_em = timezone.now()
    titulo.save(update_fields=["status", "cancelado_em", "atualizado_em"])
    registrar_evento(titulo, "CANCELADO", motivo or "Conta a Pagar cancelada.", usuario)
    if liberacao:
        if liberacao.valor_esperado is not None and liberacao.recebimento_id:
            referencia = f"COMPRA_LIBERACAO:{liberacao.pk}"
            vigentes = (
                TituloPagar.objects.filter(pedido_id=liberacao.pedido_id, recebimento_id=liberacao.recebimento_id)
                .filter(Q(referencia_externa=referencia) | Q(referencia_externa__startswith=f"{referencia}:"))
                .exclude(status=TituloPagar.Status.CANCELADO)
            )
            total = vigentes.aggregate(total=Sum("valor_original"))["total"]
            if total is not None:
                liberacao.valor = total
                liberacao.save(update_fields=["valor"])
                return titulo
        liberacao.status = LiberacaoFinanceiraPedido.Status.CANCELADA
        liberacao.motivo_cancelamento = motivo or "Título da liberação cancelado."
        liberacao.cancelado_por = usuario
        liberacao.cancelado_em = timezone.now()
        liberacao.save(update_fields=["status", "motivo_cancelamento", "cancelado_por", "cancelado_em"])
    return titulo
