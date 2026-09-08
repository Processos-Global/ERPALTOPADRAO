from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from obras.models import Obra
from planejamento.models import ItemCronogramaSuprimento
from usuarios.models import AcaoCompra, NivelPermissao

from compras.forms import (
    AdjudicacaoForm,
    AnaliseTecnicaLoteForm,
    AprovacaoForm,
    CompatibilizacaoForm,
    DocumentoContratacaoForm,
    CotacaoFornecedorForm,
    CotacaoItemForm,
    DecisaoComercialLoteForm,
    ItemCompraAberturaFormSet,
    NecessidadeCompraForm,
    NegociacaoForm,
    ProcessoCompraForm,
    PropostaCompletaForm,
    SolicitacaoCotacaoEnvioForm,
)
from compras.models import (
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    AprovacaoCompra,
    PedidoCompra,
    ProcessoCompra,
    SolicitacaoCotacaoFornecedor,
)
from compras.services.permissoes import (
    compras_acao_required,
    possui_acao_compras,
    possui_permissao_compras,
)
from compras.services.processos import criar_processo
from compras.services.comercial import item_tecnicamente_aprovado, processo_exige_compatibilizacao
from compras.services.pedidos import transicoes_status_permitidas
from compras.services.pdf_solicitacao import gerar_pdf_solicitacao_aprovada


# ============================================================
# QUERYSETS BASE
# ============================================================


def _qs_processos():
    return (
        ProcessoCompra.objects
        .select_related(
            "obra",
            "comprador",
            "item_cronograma",
        )
        .annotate(
            qtd_itens=Count(
                "necessidades",
                distinct=True,
            ),
            qtd_fornecedores=Count(
                "cotacoes__fornecedor",
                distinct=True,
            ),
        )
    )


def _aplicar_filtros(request, qs):
    obra = request.GET.get("obra")
    status = request.GET.get("status")
    etapa = request.GET.get("etapa")

    busca = (
        request.GET.get("q")
        or ""
    ).strip()

    if obra:
        qs = qs.filter(
            obra_id=obra
        )

    if status:
        qs = qs.filter(
            status=status
        )

    if etapa:
        qs = qs.filter(
            etapa_atual=etapa
        )

    if busca:
        qs = qs.filter(
            Q(
                numero__icontains=busca
            )
            | Q(
                titulo__icontains=busca
            )
            | Q(
                item_cronograma__item__icontains=busca
            )
            | Q(
                obra__nome__icontains=busca
            )
        )

    return qs


# ============================================================
# DADOS COMERCIAIS
# ============================================================


def _montar_dados_comerciais(
    processo,
    necessidades,
    cotacoes,
    adjudicacoes,
):
    """
    Prepara estruturas de leitura para o template sem
    colocar regra comercial no HTML.
    """

    zero = Decimal("0")

    cotacoes = list(
        cotacoes
    )

    adjudicacoes = list(
        adjudicacoes
    )

    # --------------------------------------------------------
    # ITENS POR COTAÇÃO / NECESSIDADE
    # --------------------------------------------------------

    itens_por_cotacao_necessidade = {}

    todos_itens = []

    for cotacao in cotacoes:

        total = zero

        itens = list(
            cotacao.itens.all()
        )

        for item in itens:

            todos_itens.append(
                item
            )

            itens_por_cotacao_necessidade[
                (
                    cotacao.pk,
                    item.necessidade_id,
                )
            ] = item

            total += (
                item.valor_total_cotado
            )

        cotacao.total_proposta = total
        cotacao.total_proposta_com_frete = total + (cotacao.frete or zero)
        cotacao.qtd_itens_proposta = len(itens)

    # --------------------------------------------------------
    # MATRIZ DE COTAÇÃO
    # --------------------------------------------------------

    matriz_cotacao = []

    for necessidade in necessidades:

        ofertas = []

        for cotacao in cotacoes:

            item = (
                itens_por_cotacao_necessidade
                .get(
                    (
                        cotacao.pk,
                        necessidade.pk,
                    )
                )
            )

            negociacao = None
            if item is not None:
                try:
                    negociacao = item.negociacao
                except Exception:
                    negociacao = None

            valor_final = None
            total_final = None
            elegivel_aprovacao = False
            if item is not None:
                valor_final = (
                    negociacao.valor_final_unitario
                    if negociacao is not None
                    else item.valor_unitario_cotado
                )
                total_final = valor_final * item.quantidade
                elegivel_aprovacao = bool(cotacao.enviada_aprovacao_em) and item_tecnicamente_aprovado(item)

            ofertas.append(
                {
                    "cotacao": cotacao,
                    "item": item,
                    "menor_preco": False,
                    "negociacao": negociacao,
                    "valor_final": valor_final,
                    "total_final": total_final,
                    "elegivel_aprovacao": elegivel_aprovacao,
                }
            )

        valores_validos = [
            oferta["item"].valor_unitario_cotado
            for oferta in ofertas
            if oferta["item"] is not None
        ]
        menor_preco = min(valores_validos) if valores_validos else None
        for oferta in ofertas:
            oferta["menor_preco"] = bool(
                oferta["item"] is not None
                and menor_preco is not None
                and oferta["item"].valor_unitario_cotado == menor_preco
            )

        valores_finais_elegiveis = [
            oferta["valor_final"]
            for oferta in ofertas
            if oferta["elegivel_aprovacao"] and oferta["valor_final"] is not None
        ]
        menor_valor_final = min(valores_finais_elegiveis) if valores_finais_elegiveis else None
        for oferta in ofertas:
            oferta["menor_valor_final"] = bool(
                oferta["elegivel_aprovacao"]
                and menor_valor_final is not None
                and oferta["valor_final"] == menor_valor_final
            )

        matriz_cotacao.append(
            {
                "necessidade": necessidade,
                "ofertas": ofertas,
                "menor_preco": menor_preco,
                "menor_valor_final": menor_valor_final,
            }
        )

    prazos_validos = [c.prazo_entrega_dias for c in cotacoes if c.prazo_entrega_dias is not None]
    menor_prazo = min(prazos_validos) if prazos_validos else None
    avaliacoes_validas = [c.fornecedor.avaliacao for c in cotacoes if c.fornecedor.avaliacao is not None]
    melhor_avaliacao = max(avaliacoes_validas) if avaliacoes_validas else None

    for cotacao in cotacoes:
        cotacao.menor_prazo = bool(
            menor_prazo is not None and cotacao.prazo_entrega_dias == menor_prazo
        )
        cotacao.melhor_avaliado = bool(
            melhor_avaliacao is not None and cotacao.fornecedor.avaliacao == melhor_avaliacao
        )

    # --------------------------------------------------------
    # MAPA DE ITENS
    # --------------------------------------------------------

    mapa_itens = []

    for item in todos_itens:

        compat = None

        compatibilizacoes = list(
            item.compatibilizacoes.all()
        )

        if compatibilizacoes:
            compat = (
                compatibilizacoes[0]
            )

        try:
            negociacao = (
                item.negociacao
            )
        except Exception:
            negociacao = None

        valor_final = (
            negociacao.valor_final_unitario
            if negociacao
            else item.valor_unitario_cotado
        )

        quantidade_selecionada = sum(
            (
                adjudicacao.quantidade
                for adjudicacao in adjudicacoes
                if (
                    adjudicacao.item_cotado_id
                    == item.pk
                )
            ),
            zero,
        )

        mapa_itens.append(
            {
                "item": item,
                "compat": compat,
                "negociacao": negociacao,
                "valor_final": valor_final,
                "quantidade_selecionada": (
                    quantidade_selecionada
                ),
                "valor_selecionado": (
                    quantidade_selecionada
                    * valor_final
                ),
            }
        )

    # --------------------------------------------------------
    # FORNECEDORES ADJUDICADOS
    # --------------------------------------------------------

    fornecedores = defaultdict(
        lambda: {
            "valor": zero,
            "quantidade": zero,
            "itens": 0,
        }
    )

    valor_total_selecionado = zero

    for adjudicacao in adjudicacoes:

        valor = (
            adjudicacao.valor_total
        )

        valor_total_selecionado += (
            valor
        )

        bucket = fornecedores[
            adjudicacao.cotacao.fornecedor_id
        ]

        bucket["fornecedor"] = (
            adjudicacao
            .cotacao
            .fornecedor
        )

        bucket["valor"] += (
            valor
        )

        bucket["quantidade"] += (
            adjudicacao.quantidade
        )

        bucket["itens"] += 1

        if not bucket.get(
            "condicao_pagamento"
        ):
            bucket[
                "condicao_pagamento"
            ] = (
                adjudicacao
                .condicao_pagamento_final
            )

        if bucket.get(
            "prazo_entrega_dias"
        ) is None:
            bucket[
                "prazo_entrega_dias"
            ] = (
                adjudicacao
                .prazo_entrega_dias_final
            )

    resumo_fornecedores = sorted(
        fornecedores.values(),
        key=lambda item: (
            -item["valor"],
            item[
                "fornecedor"
            ].nome.lower(),
        ),
    )

    # --------------------------------------------------------
    # RESUMO DETALHADO PARA APROVAÇÃO DO GESTOR
    # --------------------------------------------------------

    resumo_aprovacao_itens = []
    valor_total_cotado_aprovacao = zero
    valor_total_final_aprovacao = zero

    for adjudicacao in adjudicacoes:

        item_cotado = adjudicacao.item_cotado

        compat = None
        compatibilizacoes = list(
            item_cotado.compatibilizacoes.all()
        )
        if compatibilizacoes:
            compat = compatibilizacoes[0]

        valor_unitario_cotado = (
            item_cotado.valor_unitario_cotado
        )
        valor_unitario_final = (
            adjudicacao.valor_unitario_final
        )

        # O total cotado é uma referência usando exatamente a
        # quantidade que foi selecionada para compra. O total
        # final usa a adjudicação congelada, incluindo eventual
        # desconto final aplicado na escolha comercial.
        valor_cotado_referencia = (
            adjudicacao.quantidade
            * valor_unitario_cotado
        )
        valor_final = adjudicacao.valor_total
        economia = (
            valor_cotado_referencia
            - valor_final
        )

        economia_percentual = zero
        if valor_cotado_referencia > zero:
            economia_percentual = (
                economia
                / valor_cotado_referencia
            ) * Decimal("100")

        valor_total_cotado_aprovacao += (
            valor_cotado_referencia
        )
        valor_total_final_aprovacao += valor_final

        resumo_aprovacao_itens.append(
            {
                "adjudicacao": adjudicacao,
                "necessidade": adjudicacao.necessidade,
                "fornecedor": adjudicacao.cotacao.fornecedor,
                "item_cotado": item_cotado,
                "compat": compat,
                "quantidade": adjudicacao.quantidade,
                "valor_unitario_cotado": valor_unitario_cotado,
                "valor_unitario_final": valor_unitario_final,
                "valor_cotado_referencia": valor_cotado_referencia,
                "valor_final": valor_final,
                "economia": economia,
                "economia_percentual": economia_percentual,
                "houve_alteracao_valor": (
                    valor_unitario_final
                    != valor_unitario_cotado
                    or (adjudicacao.desconto_final or zero) > zero
                ),
                "condicao_pagamento": (
                    adjudicacao.condicao_pagamento_final
                ),
                "prazo_entrega_dias": (
                    adjudicacao.prazo_entrega_dias_final
                ),
            }
        )

    economia_total_aprovacao = (
        valor_total_cotado_aprovacao
        - valor_total_final_aprovacao
    )

    economia_percentual_aprovacao = zero
    if valor_total_cotado_aprovacao > zero:
        economia_percentual_aprovacao = (
            economia_total_aprovacao
            / valor_total_cotado_aprovacao
        ) * Decimal("100")

    # --------------------------------------------------------
    # ATENDIMENTO
    # --------------------------------------------------------

    quantidade_total = sum(
        (
            necessidade.quantidade_incluida
            for necessidade in necessidades
        ),
        zero,
    )

    quantidade_adjudicada = sum(
        (
            necessidade.quantidade_adjudicada
            for necessidade in necessidades
        ),
        zero,
    )

    percentual_atendido = zero

    if quantidade_total > zero:
        percentual_atendido = (
            quantidade_adjudicada
            / quantidade_total
        ) * Decimal("100")

    return {
        "matriz_cotacao": matriz_cotacao,
        "mapa_itens": mapa_itens,
        "resumo_fornecedores": (
            resumo_fornecedores
        ),
        "resumo_aprovacao_itens": (
            resumo_aprovacao_itens
        ),
        "valor_total_cotado_aprovacao": (
            valor_total_cotado_aprovacao
        ),
        "valor_total_final_aprovacao": (
            valor_total_final_aprovacao
        ),
        "economia_total_aprovacao": (
            economia_total_aprovacao
        ),
        "economia_percentual_aprovacao": (
            economia_percentual_aprovacao
        ),
        "valor_total_selecionado": (
            valor_total_selecionado
        ),
        "quantidade_total": (
            quantidade_total
        ),
        "quantidade_adjudicada": (
            quantidade_adjudicada
        ),
        "percentual_atendido": min(
            percentual_atendido,
            Decimal("100"),
        ),
    }


# ============================================================
# DASHBOARD
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def dashboard(request):

    qs = (
        _aplicar_filtros(
            request,
            _qs_processos(),
        )
        .order_by(
            "-atualizado_em"
        )
    )

    hoje = timezone.localdate()

    # Estados terminais não devem ser considerados processos ativos.
    ativos = qs.exclude(
        status__in=[
            ProcessoCompra.Status.CONTRATADO,
            ProcessoCompra.Status.REPROVADO,
            ProcessoCompra.Status.CANCELADO,
        ]
    )

    atrasados = ativos.filter(
        item_cronograma__prazo_limite_contratacao__lt=hoje,
        data_contratacao_concluida__isnull=True,
    )

    aguardando = qs.filter(
        status=ProcessoCompra.Status.AGUARDANDO_APROVACAO
    )

    ajustes = qs.filter(
        status=ProcessoCompra.Status.AJUSTE_SOLICITADO
    )

    contratados = qs.filter(
        status=ProcessoCompra.Status.CONTRATADO,
        data_contratacao_concluida__date__gte=(
            hoje - timedelta(days=30)
        ),
    )

    # O Kanban é organizado pelos STATUS reais do processo.
    # Isso é importante porque alguns estados relevantes, como
    # AJUSTE_SOLICITADO, compartilham uma etapa com outro momento
    # do fluxo (o ajuste retorna para COTAÇÃO), mas precisam ficar
    # visualmente separados no painel.
    definicoes = [
        (
            "RASCUNHO",
            "Rascunho",
            [
                ProcessoCompra.Status.RASCUNHO,
            ],
            "Processos ainda não iniciados",
        ),
        (
            "COTACAO",
            "Cotação",
            [
                ProcessoCompra.Status.PEDIDO_ENVIADO,
                ProcessoCompra.Status.SOLICITACAO_COTACAO,
                ProcessoCompra.Status.AGUARDANDO_COTACAO,
                ProcessoCompra.Status.EM_COTACAO,
            ],
            "Levantamento e recebimento de propostas",
        ),
        (
            "COMPATIBILIZACAO",
            "Análise técnica",
            [
                ProcessoCompra.Status.AGUARDANDO_COMPATIBILIZACAO,
                ProcessoCompra.Status.EM_COMPATIBILIZACAO,
            ],
            "Validação técnica das ofertas",
        ),
        (
            "NEGOCIACAO",
            "Negociação",
            [
                ProcessoCompra.Status.EM_NEGOCIACAO,
            ],
            "Negociação comercial",
        ),
        (
            "APROVACAO",
            "Aprovação",
            [
                ProcessoCompra.Status.AGUARDANDO_APROVACAO,
            ],
            "Aguardando decisão do gestor",
        ),
        (
            "AJUSTE",
            "Ajuste solicitado",
            [
                ProcessoCompra.Status.AJUSTE_SOLICITADO,
            ],
            "Retornou para cotação e novo ciclo",
        ),
        (
            "CONTRATACAO",
            "Em contratação",
            [
                ProcessoCompra.Status.APROVADO,
                ProcessoCompra.Status.EM_CONTRATACAO,
            ],
            "Pedidos emitidos aguardando confirmação dos fornecedores",
        ),
        (
            "FINALIZADO",
            "Finalizado",
            [
                ProcessoCompra.Status.CONTRATADO,
            ],
            "Todos os fornecedores confirmaram os pedidos",
        ),
        (
            "ENCERRADOS",
            "Encerrados",
            [
                ProcessoCompra.Status.REPROVADO,
                ProcessoCompra.Status.CANCELADO,
            ],
            "Reprovados ou cancelados",
        ),
    ]

    colunas = [
        {
            "chave": chave,
            "titulo": titulo,
            "descricao": descricao,
            "processos": list(
                qs.filter(
                    status__in=statuses
                )
            ),
        }
        for (
            chave,
            titulo,
            statuses,
            descricao,
        ) in definicoes
    ]

    return render(
        request,
        "compras/dashboard.html",
        {
            "ativos": ativos.count(),
            "atrasados": atrasados.count(),
            "aguardando": aguardando.count(),
            "ajustes": ajustes.count(),
            "contratados": contratados.count(),
            "colunas": colunas,
            "obras": (
                Obra.objects
                .order_by("nome")
            ),
            "status_choices": (
                ProcessoCompra
                .Status
                .choices
            ),
            "etapa_choices": (
                ProcessoCompra
                .Etapa
                .choices
            ),
            "hoje": hoje,
        },
    )


# ============================================================
# LISTA DE PROCESSOS
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def lista_processos(request):

    qs = (
        _aplicar_filtros(
            request,
            _qs_processos(),
        )
        .order_by(
            "-criado_em"
        )
    )

    return render(
        request,
        "compras/processos_lista.html",
        {
            "processos": qs,
            "obras": (
                Obra.objects
                .order_by("nome")
            ),
            "status_choices": (
                ProcessoCompra
                .Status
                .choices
            ),
            "etapa_choices": (
                ProcessoCompra
                .Etapa
                .choices
            ),
        },
    )


# ============================================================
# DETALHE DO PROCESSO
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def detalhe_processo(
    request,
    pk,
):

    processo = get_object_or_404(
        ProcessoCompra.objects
        .select_related(
            "obra",
            "comprador",
            "item_cronograma",
        ),
        pk=pk,
    )

    pode_editar = (
        possui_permissao_compras(
            request.user,
            NivelPermissao.EDICAO,
        )
    )

    pode_aprovar = (
        possui_permissao_compras(
            request.user,
            NivelPermissao.APROVACAO,
        )
    )

    permissoes_compras = {
        "pode_visualizar": possui_acao_compras(
            request.user, AcaoCompra.VISUALIZAR
        ),
        "pode_solicitar": possui_acao_compras(
            request.user, AcaoCompra.SOLICITAR
        ),
        "pode_cotar": possui_acao_compras(
            request.user, AcaoCompra.COTAR
        ),
        "pode_compatibilizar": possui_acao_compras(
            request.user, AcaoCompra.COMPATIBILIZAR
        ),
        "pode_negociar": possui_acao_compras(
            request.user, AcaoCompra.NEGOCIAR
        ),
        "pode_aprovar": possui_acao_compras(
            request.user, AcaoCompra.APROVAR
        ),
        "pode_gerenciar_pedidos": possui_acao_compras(
            request.user, AcaoCompra.GERENCIAR_PEDIDOS
        ),
        "pode_receber_pedidos": possui_acao_compras(
            request.user, AcaoCompra.RECEBER_PEDIDOS
        ),
        "pode_cancelar_pedidos": possui_acao_compras(
            request.user, AcaoCompra.CANCELAR_PEDIDOS
        ),
        "pode_administrar": possui_acao_compras(
            request.user, AcaoCompra.ADMINISTRAR
        ),
    }

    vinculos = list(
        processo
        .vinculos_atividades
        .select_related(
            "atividade",
            "criado_por",
        )
        .order_by(
            "atividade__disciplina",
            "atividade__nome_tarefa",
        )
    )

    # ========================================================
    # CORREÇÃO:
    #
    # NecessidadeCompra não possui mais relacionamento "insumo".
    # Os relacionamentos válidos são:
    #
    # - processo
    # - atividade_origem
    # ========================================================

    necessidades = list(
        processo
        .necessidades
        .select_related(
            "atividade_origem",
        )
        .order_by(
            "descricao",
            "id",
        )
    )

    itens_prefetch = Prefetch(
        "itens",
        queryset=(
            CotacaoFornecedorItem.objects
            .select_related(
                "necessidade",
                "negociacao",
            )
            .prefetch_related(
                "compatibilizacoes"
            )
        ),
    )

    solicitacoes_cotacao = list(
        processo
        .solicitacoes_cotacao
        .select_related("fornecedor", "enviada_por")
        .order_by("fornecedor__nome")
    )

    form_envio_fornecedor = SolicitacaoCotacaoEnvioForm(processo=processo)

    cotacoes = list(
        processo
        .cotacoes
        .select_related(
            "fornecedor"
        )
        .prefetch_related(
            itens_prefetch
        )
        .order_by(
            "fornecedor__nome"
        )
    )

    exige_compatibilizacao = processo_exige_compatibilizacao(processo)
    cotacoes_em_aprovacao = [c for c in cotacoes if c.enviada_aprovacao_em]

    adjudicacoes = list(
        processo
        .adjudicacoes
        .filter(
            cancelada=False
        )
        .select_related(
            "necessidade",
            "cotacao__fornecedor",
            "item_cotado",
        )
        .order_by(
            "necessidade__descricao",
            "cotacao__fornecedor__nome",
        )
    )

    possui_saldo_pendente = any(
        (
            necessidade.situacao
            == "ATIVA"
            and necessidade.saldo > 0
        )
        for necessidade in necessidades
    )

    dados_comerciais = (
        _montar_dados_comerciais(
            processo,
            necessidades,
            cotacoes,
            adjudicacoes,
        )
    )

    contratacoes = list(
        processo
        .contratacoes
        .filter(
            cancelada=False
        )
        .select_related(
            "fornecedor",
            "formalizado_por",
        )
        .order_by(
            "fornecedor__nome"
        )
    )

    pedidos = list(
        processo
        .pedidos
        .select_related(
            "fornecedor"
        )
        .prefetch_related(
            "itens",
            "anexos",
        )
        .order_by(
            "fornecedor__nome"
        )
    )

    # Centraliza, para consulta, todos os arquivos já anexados ao processo.
    # A tela de Pedidos apenas exibe esses arquivos; não exige nova seleção
    # de fornecedor nem novo upload nesta etapa.
    documentos_processo = []

    for cotacao in cotacoes:
        if cotacao.documento:
            documentos_processo.append(
                {
                    "etapa": "Cotação",
                    "fornecedor": cotacao.fornecedor,
                    "documento": cotacao.documento,
                    "nome": cotacao.documento.name.rsplit("/", 1)[-1],
                    "responsavel": cotacao.criado_por,
                    "data": cotacao.atualizado_em,
                }
            )

    for contratacao in contratacoes:
        if contratacao.documento:
            documentos_processo.append(
                {
                    "etapa": "Formalização",
                    "fornecedor": contratacao.fornecedor,
                    "documento": contratacao.documento,
                    "nome": contratacao.documento.name.rsplit("/", 1)[-1],
                    "responsavel": contratacao.formalizado_por,
                    "data": contratacao.formalizado_em,
                }
            )

    for pedido in pedidos:
        for anexo in pedido.anexos.all():
            documentos_processo.append(
                {
                    "etapa": "Pedido",
                    "fornecedor": pedido.fornecedor,
                    "documento": anexo.arquivo,
                    "nome": anexo.nome_arquivo,
                    "responsavel": anexo.enviado_por,
                    "data": anexo.criado_em,
                }
            )

    documentos_processo.sort(
        key=lambda item: item["data"],
        reverse=True,
    )

    propostas_forms = [
        {
            "cotacao": cotacao,
            "form": PropostaCompletaForm(
                processo=processo,
                cotacao=cotacao,
            ),
        }
        for cotacao in cotacoes
    ]
    form_proposta_nova = None
    pode_cadastrar_nova_proposta = False
    form_analise_lote = None
    compatibilizacoes_forms = []
    form_decisao_lote = None

    fase_comercial_aberta = processo.etapa_atual in {
        ProcessoCompra.Etapa.COTACAO, ProcessoCompra.Etapa.COMPATIBILIZACAO,
        ProcessoCompra.Etapa.NEGOCIACAO, ProcessoCompra.Etapa.APROVACAO,
    }
    fase_analise_aberta = processo.etapa_atual in {
        ProcessoCompra.Etapa.COMPATIBILIZACAO, ProcessoCompra.Etapa.NEGOCIACAO, ProcessoCompra.Etapa.APROVACAO,
    }

    if pode_editar and fase_comercial_aberta:
        form_proposta_nova = PropostaCompletaForm(
            processo=processo,
        )
        pode_cadastrar_nova_proposta = form_proposta_nova.fields["fornecedor"].queryset.exists()
    if pode_editar and fase_analise_aberta:
        if exige_compatibilizacao:
            cotacoes_para_compatibilizar = [
                cotacao
                for cotacao in cotacoes
                if cotacao.enviada_compatibilizacao_em
                and not cotacao.enviada_negociacao_em
                and not cotacao.enviada_aprovacao_em
            ]
            compatibilizacoes_forms = [
                {
                    "cotacao": cotacao,
                    "form": AnaliseTecnicaLoteForm(
                        processo=processo,
                        cotacao=cotacao,
                    ),
                }
                for cotacao in cotacoes_para_compatibilizar
            ]
        form_decisao_lote = DecisaoComercialLoteForm(processo=processo)

    aprovacao_aprovada = (
        processo.aprovacoes.filter(decisao=AprovacaoCompra.Decisao.APROVADO)
        .select_related("usuario", "alcada")
        .order_by("-criado_em", "-id")
        .first()
    )

    contexto = {
        "processo": processo,
        "aprovacao_aprovada": aprovacao_aprovada,
        "vinculos": vinculos,
        "necessidades": necessidades,
        "cotacoes": cotacoes,
        "solicitacoes_cotacao": solicitacoes_cotacao,
        "meios_envio_cotacao": SolicitacaoCotacaoFornecedor.MeioEnvio.choices,
        "form_envio_fornecedor": form_envio_fornecedor,
        "adjudicacoes": adjudicacoes,
        "possui_saldo_pendente": (
            possui_saldo_pendente
        ),
        "fase_comercial_aberta": fase_comercial_aberta,
        "fase_analise_aberta": fase_analise_aberta,
        "exige_compatibilizacao": exige_compatibilizacao,
        "cotacoes_em_aprovacao": cotacoes_em_aprovacao,
        "compatibilizacoes_forms": compatibilizacoes_forms,

        "aprovacoes": (
            processo
            .aprovacoes
            .select_related(
                "usuario",
                "alcada",
            )
        ),

        "contratacoes": (
            contratacoes
        ),

        "pedidos": (
            pedidos
        ),

        "documentos_processo": (
            documentos_processo
        ),

        "historico": (
            processo
            .historico
            .select_related(
                "usuario"
            )[:100]
        ),

        "pode_editar": (
            pode_editar
        ),

        "pode_aprovar": (
            pode_aprovar
        ),

        "permissoes_compras": (
            permissoes_compras
        ),

        "propostas_forms": propostas_forms,
        "form_proposta_nova": form_proposta_nova,
        "pode_cadastrar_nova_proposta": pode_cadastrar_nova_proposta,
        "form_analise_lote": form_analise_lote,
        "form_decisao_lote": form_decisao_lote,

        "form_necessidade": (
            NecessidadeCompraForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_cotacao": (
            CotacaoFornecedorForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_item_cotacao": (
            CotacaoItemForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_compat": (
            CompatibilizacaoForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_negociacao": (
            NegociacaoForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_adjudicacao": (
            AdjudicacaoForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        "form_aprovacao": (
            AprovacaoForm(processo=processo)
            if pode_aprovar and cotacoes_em_aprovacao
            else None
        ),

        "form_documento_contratacao": (
            DocumentoContratacaoForm(
                processo=processo
            )
            if pode_editar
            else None
        ),

        **dados_comerciais,
    }

    return render(
        request,
        "compras/processo_detalhe.html",
        contexto,
    )


# ============================================================
# NOVO PROCESSO
# ============================================================


@compras_acao_required(
    AcaoCompra.SOLICITAR
)
def novo_processo(request):

    item_inicial = None

    item_id = (
        request.GET.get("item")
        or request.POST.get(
            "item_cronograma"
        )
        or request.POST.get(
            "item_origem"
        )
    )

    if item_id:

        item_inicial = (
            ItemCronogramaSuprimento.objects
            .select_related(
                "cronograma_obra__obra"
            )
            .filter(
                pk=item_id
            )
            .first()
        )

    form = ProcessoCompraForm(
        request.POST or None,
        item_inicial=item_inicial,
        initial={
            "item_cronograma": (
                item_inicial
            ),
            "titulo": (
                item_inicial.item
                if item_inicial
                else ""
            ),
        },
    )

    formset = ItemCompraAberturaFormSet(
        request.POST or None,
        prefix="itens",
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and formset.is_valid()
    ):

        itens = [
            linha.cleaned_data
            for linha in formset
            if (
                linha.cleaned_data
                and not linha.cleaned_data.get(
                    "DELETE"
                )
            )
        ]

        try:

            processo = criar_processo(
                item_cronograma=(
                    form.cleaned_data[
                        "item_cronograma"
                    ]
                ),

                titulo=(
                    form.cleaned_data[
                        "titulo"
                    ]
                ),

                descricao=(
                    form.cleaned_data[
                        "descricao"
                    ]
                ),

                comprador=(
                    form.cleaned_data[
                        "comprador"
                    ]
                ),

                atividades=(
                    form.cleaned_data[
                        "atividades"
                    ]
                ),

                itens=itens,

                observacao=(
                    form.cleaned_data[
                        "observacao"
                    ]
                ),

                usuario=(
                    request.user
                ),

                iniciar_cotacao=(
                    request.POST.get(
                        "acao"
                    )
                    != "rascunho"
                ),
            )

            messages.success(
                request,
                (
                    f"Compra {processo.numero} "
                    f"criada com "
                    f"{len(itens)} item(ns)."
                ),
            )

            return redirect(
                "compras:detalhe_processo",
                pk=processo.pk,
            )

        except ValidationError as exc:

            form.add_error(
                None,
                exc,
            )

    return render(
        request,
        "compras/processo_form.html",
        {
            "form": form,
            "formset": formset,
            "item_inicial": (
                item_inicial
            ),
        },
    )


@compras_acao_required(AcaoCompra.VISUALIZAR)
def pdf_solicitacao_aprovada(request, pk):
    processo = get_object_or_404(
        ProcessoCompra.objects.select_related("obra", "item_cronograma", "criado_por", "comprador"),
        pk=pk,
    )
    try:
        conteudo = gerar_pdf_solicitacao_aprovada(processo)
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("compras:detalhe_processo", pk=processo.pk)

    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="solicitacao-{processo.numero}-aprovada.pdf"'
    return resposta


# ============================================================
# PEDIDOS
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def lista_pedidos(request):

    pedidos = (
        PedidoCompra.objects
        .select_related(
            "obra",
            "fornecedor",
            "processo",
            "responsavel",
        )
        .prefetch_related("itens", "anexos", "recebimentos__usuario", "recebimentos__itens__item_pedido")
        .order_by(
            "-criado_em"
        )
    )

    obra = (
        request.GET.get("obra")
    )

    status = (
        request.GET.get("status")
    )

    busca = (
        request.GET.get("q")
        or ""
    ).strip()

    if obra:
        pedidos = pedidos.filter(
            obra_id=obra
        )

    if status:
        pedidos = pedidos.filter(
            status=status
        )

    if busca:

        pedidos = pedidos.filter(
            Q(
                numero__icontains=busca
            )
            | Q(
                processo__numero__icontains=busca
            )
            | Q(
                fornecedor__nome__icontains=busca
            )
        )

    pedidos = list(pedidos)
    for pedido in pedidos:
        pedido.transicoes_status_permitidas = transicoes_status_permitidas(pedido)

    return render(
        request,
        "compras/pedidos_lista.html",
        {
            "pedidos": (
                pedidos
            ),

            "obras": (
                Obra.objects
                .order_by(
                    "nome"
                )
            ),

            "status_choices": (
                PedidoCompra
                .Status
                .choices
            ),
        },
    )