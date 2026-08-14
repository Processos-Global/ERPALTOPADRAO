from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import (
    AprovacaoCompra,
    CompatibilizacaoItem,
    ProcessoCompra,
)

from .adjudicacoes import validar_adjudicacao_completa
from .auditoria import registrar_evento
from .integracao_planejamento import sincronizar_data_real


# ============================================================
# COTAÇÃO
# ============================================================


@transaction.atomic
def concluir_cotacao(
    processo,
    usuario,
):
    """
    Finaliza a etapa de cotação e envia o processo
    para análise técnica.
    """

    p = (
        ProcessoCompra.objects
        .select_for_update()
        .get(
            pk=processo.pk
        )
    )

    # --------------------------------------------------------
    # ETAPA ATUAL
    # --------------------------------------------------------

    if (
        p.etapa_atual
        != p.Etapa.COTACAO
    ):
        raise ValidationError(
            (
                "O processo não está "
                "na etapa de cotação."
            )
        )

    # --------------------------------------------------------
    # VALIDAÇÃO DAS PROPOSTAS
    # --------------------------------------------------------

    possui_cotacao = (
        p.cotacoes.exists()
    )

    possui_item_cotado = (
        p.cotacoes
        .filter(
            itens__isnull=False
        )
        .exists()
    )

    if (
        not possui_cotacao
        or not possui_item_cotado
    ):
        raise ValidationError(
            (
                "Inclua ao menos uma proposta "
                "com item cotado antes de "
                "concluir a cotação."
            )
        )

    # --------------------------------------------------------
    # AVANÇO
    # --------------------------------------------------------

    p.data_cotacao_concluida = (
        timezone.now()
    )

    p.etapa_atual = (
        p.Etapa.COMPATIBILIZACAO
    )

    p.status = (
        p.Status.AGUARDANDO_COMPATIBILIZACAO
    )

    p.save(
        update_fields=[
            "data_cotacao_concluida",
            "etapa_atual",
            "status",
            "atualizado_em",
        ]
    )

    # --------------------------------------------------------
    # PLANEJAMENTO
    # --------------------------------------------------------

    sincronizar_data_real(
        p,
        "COTACAO",
        usuario,
    )

    # --------------------------------------------------------
    # AUDITORIA
    # --------------------------------------------------------

    registrar_evento(
        p,
        "COTACAO_CONCLUIDA",
        usuario,
        (
            "Cotação concluída e enviada "
            "para análise técnica."
        ),
    )

    return p


# ============================================================
# ANÁLISE TÉCNICA
# ============================================================


@transaction.atomic
def concluir_compatibilizacao(
    processo,
    usuario,
):
    """
    Finaliza a análise técnica.

    Cada necessidade ativa precisa possuir pelo menos
    uma solução tecnicamente aprovada ou aprovada
    com ressalva.
    """

    p = (
        ProcessoCompra.objects
        .select_for_update()
        .get(
            pk=processo.pk
        )
    )

    # --------------------------------------------------------
    # ETAPA ATUAL
    # --------------------------------------------------------

    if (
        p.etapa_atual
        != p.Etapa.COMPATIBILIZACAO
    ):
        raise ValidationError(
            (
                "O processo não está "
                "na etapa de análise técnica."
            )
        )

    # --------------------------------------------------------
    # NECESSIDADES OBRIGATÓRIAS
    # --------------------------------------------------------

    obrigatorias = list(
        p.necessidades
        .filter(
            situacao="ATIVA"
        )
        .values_list(
            "id",
            flat=True,
        )
    )

    if not obrigatorias:
        raise ValidationError(
            (
                "O processo não possui itens ativos "
                "para análise técnica."
            )
        )

    # --------------------------------------------------------
    # NECESSIDADES COM SOLUÇÃO VÁLIDA
    # --------------------------------------------------------

    validas = set(
        CompatibilizacaoItem.objects
        .filter(
            item_cotado__cotacao__processo=p,
            resultado__in=[
                CompatibilizacaoItem
                .Resultado
                .APROVADO,

                CompatibilizacaoItem
                .Resultado
                .APROVADO_COM_RESSALVA,
            ],
        )
        .values_list(
            "item_cotado__necessidade_id",
            flat=True,
        )
    )

    pendentes = [
        necessidade_id
        for necessidade_id in obrigatorias
        if necessidade_id not in validas
    ]

    if pendentes:
        raise ValidationError(
            (
                "Existe item obrigatório sem "
                "solução tecnicamente válida."
            )
        )

    # --------------------------------------------------------
    # AVANÇO
    # --------------------------------------------------------

    p.data_compatibilizacao_concluida = (
        timezone.now()
    )

    p.etapa_atual = (
        p.Etapa.NEGOCIACAO
    )

    p.status = (
        p.Status.EM_NEGOCIACAO
    )

    p.save(
        update_fields=[
            "data_compatibilizacao_concluida",
            "etapa_atual",
            "status",
            "atualizado_em",
        ]
    )

    # --------------------------------------------------------
    # PLANEJAMENTO
    # --------------------------------------------------------

    sincronizar_data_real(
        p,
        "COMPATIBILIZACAO",
        usuario,
    )

    # --------------------------------------------------------
    # AUDITORIA
    # --------------------------------------------------------

    registrar_evento(
        p,
        "COMPATIBILIZACAO_CONCLUIDA",
        usuario,
        (
            "Análise técnica concluída. "
            "Processo enviado para negociação."
        ),
    )

    return p


# ============================================================
# NEGOCIAÇÃO
# ============================================================


@transaction.atomic
def concluir_negociacao(
    processo,
    usuario,
):
    """
    Finaliza a negociação e envia o mapa comercial
    para decisão da gestão.

    Nenhuma necessidade ativa pode possuir saldo
    pendente.
    """

    p = (
        ProcessoCompra.objects
        .select_for_update()
        .get(
            pk=processo.pk
        )
    )

    # --------------------------------------------------------
    # ETAPA ATUAL
    # --------------------------------------------------------

    if (
        p.etapa_atual
        != p.Etapa.NEGOCIACAO
    ):
        raise ValidationError(
            (
                "O processo não está "
                "na etapa de negociação."
            )
        )

    # --------------------------------------------------------
    # EXISTÊNCIA DE SELEÇÃO
    # --------------------------------------------------------

    possui_adjudicacao = (
        p.adjudicacoes
        .filter(
            cancelada=False
        )
        .exists()
    )

    if not possui_adjudicacao:
        raise ValidationError(
            (
                "Selecione ao menos um fornecedor "
                "antes de concluir a negociação."
            )
        )

    # --------------------------------------------------------
    # SALDO
    # --------------------------------------------------------

    validar_adjudicacao_completa(
        p
    )

    # --------------------------------------------------------
    # AVANÇO
    # --------------------------------------------------------

    p.data_negociacao_concluida = (
        timezone.now()
    )

    p.etapa_atual = (
        p.Etapa.APROVACAO
    )

    p.status = (
        p.Status.AGUARDANDO_APROVACAO
    )

    p.save(
        update_fields=[
            "data_negociacao_concluida",
            "etapa_atual",
            "status",
            "atualizado_em",
        ]
    )

    # --------------------------------------------------------
    # PLANEJAMENTO
    # --------------------------------------------------------

    sincronizar_data_real(
        p,
        "NEGOCIACAO",
        usuario,
    )

    # --------------------------------------------------------
    # AUDITORIA
    # --------------------------------------------------------

    registrar_evento(
        p,
        "NEGOCIACAO_CONCLUIDA",
        usuario,
        (
            "Negociação concluída e enviada "
            "para aprovação da gestão."
        ),
    )

    return p


# ============================================================
# APROVAÇÃO FINAL
# ============================================================


@transaction.atomic
def decidir_aprovacao(
    processo,
    usuario,
    decisao,
    observacao="",
):
    """
    Registra a decisão final da gestão.

    NOVO FLUXO:

        COTAÇÃO
            ↓
        ANÁLISE TÉCNICA
            ↓
        NEGOCIAÇÃO
            ↓
        APROVAÇÃO
            ↓
        CONTRATADO

    Não existe mais uma etapa manual de formalização.

    Quando aprovado pela gestão:
    - status = CONTRATADO
    - etapa_atual = CONTRATADO
    - data_contratacao_concluida = agora

    Quando solicitado ajuste:
    - retorna para NEGOCIACAO
    - limpa a conclusão anterior da negociação

    A informação comercial aprovada passa a ser considerada
    a condição final da compra.
    """

    p = (
        ProcessoCompra.objects
        .select_for_update()
        .get(
            pk=processo.pk
        )
    )

    # --------------------------------------------------------
    # ETAPA ATUAL
    # --------------------------------------------------------

    if (
        p.etapa_atual
        != p.Etapa.APROVACAO
    ):
        raise ValidationError(
            (
                "O processo não está "
                "aguardando aprovação."
            )
        )

    # --------------------------------------------------------
    # DEFESA DE CONSISTÊNCIA
    #
    # Mesmo que alguém tente manipular a requisição,
    # nenhuma compra pode ser aprovada com saldo.
    # --------------------------------------------------------

    validar_adjudicacao_completa(
        p
    )

    # --------------------------------------------------------
    # OBSERVAÇÃO
    # --------------------------------------------------------

    observacao = (
        observacao
        or ""
    ).strip()

    # --------------------------------------------------------
    # CICLO DE APROVAÇÃO
    # --------------------------------------------------------

    ultimo_ciclo = (
        p.aprovacoes
        .order_by(
            "-ciclo"
        )
        .values_list(
            "ciclo",
            flat=True,
        )
        .first()
        or 0
    )

    ciclo = (
        ultimo_ciclo + 1
    )

    # --------------------------------------------------------
    # AJUSTE PRECISA DE MOTIVO
    # --------------------------------------------------------

    if (
        decisao
        == AprovacaoCompra
        .Decisao
        .AJUSTE_SOLICITADO
        and not observacao
    ):
        raise ValidationError(
            (
                "Informe o motivo do ajuste "
                "solicitado."
            )
        )

    # --------------------------------------------------------
    # REGISTRA A DECISÃO
    # --------------------------------------------------------

    aprovacao = (
        AprovacaoCompra.objects.create(
            processo=p,
            ciclo=ciclo,
            usuario=usuario,
            decisao=decisao,
            observacao=observacao,
        )
    )

    # ========================================================
    # APROVADO
    #
    # NOVA REGRA:
    # aprovação da gestão encerra o processo comercial.
    #
    # NÃO VAI MAIS PARA CONTRATACAO.
    # ========================================================

    if (
        decisao
        == AprovacaoCompra
        .Decisao
        .APROVADO
    ):

        agora = timezone.now()

        p.status = (
            p.Status.CONTRATADO
        )

        p.etapa_atual = (
            p.Etapa.CONTRATADO
        )

        p.data_contratacao_concluida = (
            agora
        )

        p.save(
            update_fields=[
                "status",
                "etapa_atual",
                "data_contratacao_concluida",
                "atualizado_em",
            ]
        )

        # ----------------------------------------------------
        # O marco de contratação passa a ser a aprovação final.
        #
        # Mantemos "CONTRATACAO" aqui porque o cronograma de
        # suprimentos provavelmente possui esse marco e agora
        # ele representa o encerramento comercial.
        # ----------------------------------------------------

        sincronizar_data_real(
            p,
            "CONTRATACAO",
            usuario,
        )

        registrar_evento(
            p,
            "APROVACAO",
            usuario,
            (
                "Compra aprovada pela gestão. "
                "Processo comercial concluído "
                "e marcado como contratado."
            ),
            {
                "ciclo": ciclo,
                "decisao": decisao,
            },
        )

        registrar_evento(
            p,
            "PROCESSO_CONTRATADO",
            usuario,
            (
                "Processo concluído automaticamente "
                "após aprovação da gestão."
            ),
            {
                "aprovacao_id": aprovacao.pk,
            },
        )

        return aprovacao

    # ========================================================
    # AJUSTE SOLICITADO
    # ========================================================

    if (
        decisao
        == AprovacaoCompra
        .Decisao
        .AJUSTE_SOLICITADO
    ):

        p.status = (
            p.Status.AJUSTE_SOLICITADO
        )

        p.etapa_atual = (
            p.Etapa.NEGOCIACAO
        )

        # A negociação precisa ser novamente concluída
        # antes de retornar para aprovação.

        p.data_negociacao_concluida = (
            None
        )

        p.save(
            update_fields=[
                "status",
                "etapa_atual",
                "data_negociacao_concluida",
                "atualizado_em",
            ]
        )

        registrar_evento(
            p,
            "APROVACAO",
            usuario,
            (
                "A gestão solicitou ajuste. "
                "O processo retornou para negociação."
            ),
            {
                "ciclo": ciclo,
                "decisao": decisao,
            },
        )

        return aprovacao

    # ========================================================
    # OUTRAS DECISÕES
    #
    # Mantemos o comportamento já existente do projeto
    # para decisões diferentes de APROVADO e AJUSTE_SOLICITADO.
    # ========================================================

    p.status = (
        p.Status.AGUARDANDO_APROVACAO
    )

    p.etapa_atual = (
        p.Etapa.APROVACAO
    )

    p.save(
        update_fields=[
            "status",
            "etapa_atual",
            "atualizado_em",
        ]
    )

    registrar_evento(
        p,
        "APROVACAO",
        usuario,
        (
            f"Decisão da gestão: "
            f"{aprovacao.get_decisao_display()}."
        ),
        {
            "ciclo": ciclo,
            "decisao": decisao,
        },
    )

    return aprovacao