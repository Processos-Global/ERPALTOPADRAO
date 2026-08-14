from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import NecessidadeCompra, ProcessoCompra, ProcessoCompraAtividade

from .auditoria import registrar_evento
from .numeracao import gerar_numero


@transaction.atomic
def criar_processo(
    *,
    item_cronograma,
    titulo,
    usuario,
    atividades,
    itens,
    comprador=None,
    descricao="",
    observacao="",
    iniciar_cotacao=True,
):
    obra_id = item_cronograma.cronograma_obra.obra_id
    atividades = list(atividades)
    itens = list(itens)

    if not atividades:
        raise ValidationError("Selecione pelo menos uma atividade relacionada à compra.")
    if not itens:
        raise ValidationError("Inclua pelo menos um item para iniciar a compra.")

    atividade_ids = set()
    for atividade in atividades:
        if atividade.obra_id != obra_id:
            raise ValidationError("Todas as atividades devem pertencer à mesma obra do suprimento.")
        atividade_ids.add(atividade.pk)

    for item in itens:
        atividade = item["atividade"]
        if atividade.obra_id != obra_id:
            raise ValidationError("O item possui uma atividade de outra obra.")
        atividade_ids.add(atividade.pk)

    processo = ProcessoCompra.objects.create(
        numero=gerar_numero("PROCESSO"),
        obra_id=obra_id,
        item_cronograma=item_cronograma,
        titulo=titulo or item_cronograma.item,
        descricao=descricao,
        comprador=comprador or usuario,
        observacao=observacao,
        status=(ProcessoCompra.Status.EM_COTACAO if iniciar_cotacao else ProcessoCompra.Status.RASCUNHO),
        criado_por=usuario,
    )

    atividades_por_id = {atividade.pk: atividade for atividade in atividades}
    for item in itens:
        atividades_por_id[item["atividade"].pk] = item["atividade"]

    ProcessoCompraAtividade.objects.bulk_create(
        [
            ProcessoCompraAtividade(
                processo=processo,
                atividade=atividade,
                criado_por=usuario,
            )
            for atividade in atividades_por_id.values()
        ]
    )

    necessidades = []
    for item in itens:
        quantidade = Decimal(str(item["quantidade"]))
        if quantidade <= 0:
            raise ValidationError("A quantidade dos itens deve ser maior que zero.")
        necessidades.append(
            NecessidadeCompra(
                processo=processo,
                atividade_origem=item["atividade"],
                descricao=item["descricao"].strip(),
                especificacao=(item.get("especificacao") or "").strip(),
                unidade=item["unidade"],
                quantidade_necessaria=quantidade,
                quantidade_incluida=quantidade,
                observacao=(item.get("observacao") or "").strip(),
            )
        )
    NecessidadeCompra.objects.bulk_create(necessidades)

    registrar_evento(
        processo,
        "CRIACAO",
        usuario,
        f"Compra criada com {len(atividades_por_id)} atividade(s) e {len(necessidades)} item(ns).",
    )
    if iniciar_cotacao:
        registrar_evento(processo, "COTACAO_INICIADA", usuario, "Compra aberta diretamente na etapa de cotação.")
    return processo


@transaction.atomic
def incluir_necessidade(
    *,
    processo,
    atividade,
    descricao,
    unidade,
    quantidade,
    usuario,
    especificacao="",
    observacao="",
):
    quantidade = Decimal(str(quantidade))
    if quantidade <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    if atividade.obra_id != processo.obra_id:
        raise ValidationError("A atividade deve pertencer à mesma obra do processo.")

    ProcessoCompraAtividade.objects.get_or_create(
        processo=processo,
        atividade=atividade,
        defaults={"criado_por": usuario},
    )

    necessidade = NecessidadeCompra.objects.create(
        processo=processo,
        atividade_origem=atividade,
        descricao=descricao.strip(),
        especificacao=(especificacao or "").strip(),
        unidade=unidade,
        quantidade_necessaria=quantidade,
        quantidade_incluida=quantidade,
        observacao=(observacao or "").strip(),
    )
    registrar_evento(
        processo,
        "NECESSIDADE_ADICIONADA",
        usuario,
        f"Item adicionado: {necessidade.descricao}",
        {"necessidade_id": necessidade.pk, "quantidade": str(quantidade)},
    )
    return necessidade
