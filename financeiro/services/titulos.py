from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from financeiro.models import TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.numeracao import gerar_numero
from financeiro.services.regras import distribuir_valor_parcelas


@transaction.atomic
def criar_titulos_manuais(*, usuario=None, quantidade_parcelas=1, intervalo_dias=30, **dados):
    """Cria uma ou mais Contas a Pagar manuais.

    Lançamento manual usa fornecedor cadastrado, obra obrigatória e parcelas
    independentes. Cada parcela segue aprovação e pagamento integral próprios.
    """
    materiais = dados.pop("materiais", None)
    dados.pop("tipo_pagamento", None)
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
def atualizar_titulo(titulo, *, usuario, dados, motivo="Dados da Conta a Pagar atualizados."):
    if titulo.status == TituloPagar.Status.PAGO:
        raise ValueError("Conta paga não pode ser alterada. Estorne o pagamento antes de qualquer ajuste financeiro.")
    materiais = dados.pop("materiais", None)
    dados.pop("tipo_pagamento", None)
    criticos = {
        "valor_original", "desconto", "juros", "multa", "outros_acrescimos",
        "vencimento", "fornecedor", "plano_financeiro", "beneficiario_nome", "beneficiario_documento", "obra",
    }
    alterou_critico = False
    for campo, valor in dados.items():
        if campo in {"quantidade_parcelas", "intervalo_dias"}:
            continue
        if getattr(titulo, campo) != valor:
            if campo in criticos:
                alterou_critico = True
            setattr(titulo, campo, valor)

    if titulo.fornecedor_id and not titulo.beneficiario_nome:
        titulo.beneficiario_nome = getattr(titulo.fornecedor, "nome_exibicao", None) or str(titulo.fornecedor)

    if alterou_critico and titulo.status in {TituloPagar.Status.APROVADO, TituloPagar.Status.REJEITADO}:
        titulo.ciclo_aprovacao += 1
        titulo.status = TituloPagar.Status.AGUARDANDO_APROVACAO
        registrar_evento(titulo, "APROVACAO_REABERTA", "A Conta a Pagar voltou para aprovação porque dados financeiros foram alterados.", usuario)

    titulo.save()
    if materiais is not None:
        titulo.materiais.set(materiais)
    registrar_evento(titulo, "ATUALIZADO", motivo, usuario)
    return titulo


@transaction.atomic
def cancelar_titulo(titulo, *, usuario, motivo):
    if titulo.status == TituloPagar.Status.PAGO:
        raise ValueError("Conta paga não pode ser cancelada. Estorne o pagamento primeiro.")
    titulo.status = TituloPagar.Status.CANCELADO
    titulo.cancelado_em = timezone.now()
    titulo.save(update_fields=["status", "cancelado_em", "atualizado_em"])
    registrar_evento(titulo, "CANCELADO", motivo or "Conta a Pagar cancelada.", usuario)
    return titulo
