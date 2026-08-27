from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import NecessidadeCompra, ProcessoCompra, ProcessoCompraAtividade, SolicitacaoCotacaoFornecedor

from .auditoria import registrar_evento
from .numeracao import gerar_numero
from .notificacoes import notificar_novo_processo_para_cotacao


@transaction.atomic
def criar_processo(
    *,
    item_cronograma,
    titulo,
    usuario,
    atividades,
    itens,
    comprador=None,
    fornecedores_sugeridos=None,
    descricao="",
    observacao="",
    iniciar_cotacao=True,
):
    obra_id = item_cronograma.cronograma_obra.obra_id

    ativos = ProcessoCompra.objects.filter(item_cronograma=item_cronograma).exclude(
        status__in=[ProcessoCompra.Status.CANCELADO, ProcessoCompra.Status.REPROVADO, ProcessoCompra.Status.CONTRATADO]
    )
    if ativos.exists():
        existente = ativos.order_by("-criado_em").first()
        raise ValidationError(
            f"Já existe um processo ativo para este suprimento ({existente.numero}). Conclua/cancele-o antes de abrir outro."
        )

    atividades = list(atividades)
    itens = list(itens)

    if not atividades:
        raise ValidationError("Selecione pelo menos uma atividade relacionada à compra.")
    if not itens:
        raise ValidationError("Inclua pelo menos um item para iniciar a compra.")

    for atividade in atividades:
        if atividade.obra_id != obra_id:
            raise ValidationError(
                "Todas as atividades devem pertencer à mesma obra do suprimento."
            )

    processo = ProcessoCompra.objects.create(
        numero=gerar_numero("PROCESSO"),
        obra_id=obra_id,
        item_cronograma=item_cronograma,
        titulo=titulo or item_cronograma.item,
        descricao=descricao,
        comprador=comprador or usuario,
        observacao=observacao,
        status=(ProcessoCompra.Status.SOLICITACAO_COTACAO if iniciar_cotacao else ProcessoCompra.Status.RASCUNHO),
        criado_por=usuario,
    )

    fornecedores_sugeridos = list(fornecedores_sugeridos or [])
    if iniciar_cotacao and not fornecedores_sugeridos:
        raise ValidationError("Selecione pelo menos um fornecedor para solicitar cotação.")
    if fornecedores_sugeridos:
        processo.fornecedores_sugeridos.set(fornecedores_sugeridos)
        SolicitacaoCotacaoFornecedor.objects.bulk_create(
            [
                SolicitacaoCotacaoFornecedor(
                    processo=processo,
                    fornecedor=fornecedor,
                    status=SolicitacaoCotacaoFornecedor.Status.PENDENTE_ENVIO,
                )
                for fornecedor in fornecedores_sugeridos
            ],
            ignore_conflicts=True,
        )

    # As atividades são vínculo do PROCESSO, não de cada linha de item.
    # O usuário seleciona esse conjunto uma única vez na abertura.
    atividades_por_id = {atividade.pk: atividade for atividade in atividades}

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
        material = item.get("material")
        if material is None:
            raise ValidationError("Selecione um material válido do catálogo.")
        if not material.ativo:
            raise ValidationError(f"O material {material} está inativo no cadastro.")
        necessidades.append(
            NecessidadeCompra(
                processo=processo,
                atividade_origem=None,
                material=material,
                descricao=material.nome,
                especificacao=material.especificacao,
                unidade=material.unidade.sigla,
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
        (
            f"Compra criada com {len(atividades_por_id)} atividade(s) e {len(necessidades)} item(ns). "
            f"Fornecedores indicados: {', '.join(f.nome for f in fornecedores_sugeridos) if fornecedores_sugeridos else 'não informado'}."
        ),
    )
    if iniciar_cotacao:
        registrar_evento(processo, "PEDIDO_ENVIADO", usuario, "Pedido de compra enviado ao Suprimentos.")
        registrar_evento(
            processo,
            "SOLICITACAO_COTACAO_CRIADA",
            usuario,
            f"Solicitações de cotação preparadas para {len(fornecedores_sugeridos)} fornecedor(es): "
            f"{', '.join(f.nome for f in fornecedores_sugeridos)}. Aguardando registro do envio.",
        )
        notificar_novo_processo_para_cotacao(processo)
    return processo


@transaction.atomic
def incluir_necessidade(
    *,
    processo,
    material,
    quantidade,
    usuario,
    observacao="",
):
    if processo.etapa_atual != processo.Etapa.COTACAO or processo.status in {
        processo.Status.CANCELADO,
        processo.Status.REPROVADO,
        processo.Status.CONTRATADO,
    }:
        raise ValidationError("Itens só podem ser incluídos enquanto o processo estiver na etapa de cotação.")

    quantidade = Decimal(str(quantidade))
    if quantidade <= 0:
        raise ValidationError("A quantidade deve ser maior que zero.")
    if not processo.vinculos_atividades.exists():
        raise ValidationError(
            "O processo precisa possuir ao menos uma atividade relacionada antes de receber itens."
        )
    if material is None or not material.ativo:
        raise ValidationError("Selecione um material ativo do catálogo.")

    necessidade = NecessidadeCompra.objects.create(
        processo=processo,
        atividade_origem=None,
        material=material,
        descricao=material.nome,
        especificacao=material.especificacao,
        unidade=material.unidade.sigla,
        quantidade_necessaria=quantidade,
        quantidade_incluida=quantidade,
        observacao=(observacao or "").strip(),
    )
    registrar_evento(
        processo,
        "NECESSIDADE_ADICIONADA",
        usuario,
        f"Item adicionado do catálogo: {material.codigo or material.nome} · {material.nome}",
        {
            "necessidade_id": necessidade.pk,
            "material_id": material.pk,
            "quantidade": str(quantidade),
        },
    )
    return necessidade
