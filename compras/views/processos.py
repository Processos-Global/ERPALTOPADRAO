from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_safe

from obras.models import Obra
from planejamento.models import ItemCronogramaSuprimento
from usuarios.models import AcaoCompra, NivelPermissao

from compras.forms import (
    AnaliseTecnicaLoteForm,
    AprovacaoForm,
    DecisaoComercialLoteForm,
    CompraAvulsaForm,
    ItemCompraAberturaFormSet,
    ItemCompraAberturaGrandeFornecedorFormSet,
    NecessidadeCompraForm,
    ProcessoCompraForm,
    PropostaCompletaForm,
    SolicitacaoCotacaoEnvioForm,
)
from compras.models import (
    AdjudicacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    AprovacaoCompra,
    GrandeFornecedorItem,
    GrandeFornecedorParticipante,
    NecessidadeCompra,
    PedidoCompra,
    PedidoCompraAnexo,
    ProcessoCompra,
    RecebimentoPedido,
    SolicitacaoCotacaoFornecedor,
)
from compras.services.permissoes import (
    compras_acao_required,
    possui_acao_compras,
    possui_permissao_compras,
)
from compras.services.processos import criar_processo, criar_processo_avulso
from compras.services.comercial import (
    calcular_desconto_adjudicacao,
    item_tecnicamente_aprovado,
    processo_exige_compatibilizacao,
)
from compras.services.pedidos import transicoes_status_permitidas
from compras.services.cobertura_estoque import resumir_cobertura_necessidade
from compras.services.integracao_planejamento import data_necessaria_processo
from compras.services.valores import calcular_total_proposta
from compras.services.pdf_solicitacao import gerar_pdf_pedido_compra
from compras.services.pdf_solicitacao_cotacao import gerar_pdf_solicitacao_cotacao


# ============================================================
# QUERYSETS BASE
# ============================================================


def _contar_relacao_por_processo(modelo, referencia, campo="pk"):
    contagem = (
        modelo.objects.filter(**{referencia: OuterRef("pk")})
        .order_by()
        .values(referencia)
        .annotate(total=Count(campo, distinct=campo != "pk"))
        .values("total")
    )
    return Coalesce(Subquery(contagem, output_field=IntegerField()), 0)


def _qs_processos():
    return (
        ProcessoCompra.objects
        .select_related(
            "obra",
            "comprador",
            "item_cronograma",
        )
        .annotate(
            qtd_itens=_contar_relacao_por_processo(NecessidadeCompra, "processo_id"),
            qtd_fornecedores=_contar_relacao_por_processo(CotacaoFornecedor, "processo_id", "fornecedor_id"),
            qtd_itens_grande_fornecedor=_contar_relacao_por_processo(GrandeFornecedorItem, "fluxo__processo_id"),
            qtd_fornecedores_grande_fornecedor=_contar_relacao_por_processo(
                GrandeFornecedorParticipante, "fluxo__processo_id"
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
    quantidade_por_item = defaultdict(lambda: zero)
    for adjudicacao in adjudicacoes:
        quantidade_por_item[adjudicacao.item_cotado_id] += adjudicacao.quantidade

    # --------------------------------------------------------
    # ITENS POR COTAÇÃO / NECESSIDADE
    # --------------------------------------------------------

    itens_por_cotacao_necessidade = {}
    itens_por_id = {}

    todos_itens = []

    for cotacao in cotacoes:

        total = zero

        itens = list(
            cotacao.itens.all()
        )

        negociacoes_com_frete = []

        for item in itens:
            itens_por_id[item.pk] = item

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

            try:
                negociacao_item = item.negociacao
            except Exception:
                negociacao_item = None

            if (
                negociacao_item is not None
                and negociacao_item.frete_negociado is not None
            ):
                negociacoes_com_frete.append(negociacao_item)

        frete_aprovacao = cotacao.frete or zero
        if negociacoes_com_frete:
            negociacao_frete = max(
                negociacoes_com_frete,
                key=lambda n: (n.atualizado_em, n.pk),
            )
            frete_aprovacao = negociacao_frete.frete_negociado

        desconto_proposta = cotacao.desconto_proposta or zero
        cotacao.frete_aprovacao = frete_aprovacao
        cotacao.subtotal_proposta = total
        cotacao.desconto_proposta_aplicado = min(desconto_proposta, total)
        cotacao.total_proposta = calcular_total_proposta(
            subtotal=total,
            desconto=desconto_proposta,
            frete=cotacao.frete or zero,
        )
        cotacao.total_proposta_aprovacao = calcular_total_proposta(
            subtotal=total,
            desconto=desconto_proposta,
            frete=frete_aprovacao or zero,
        )
        # Compatibilidade com usos legados do atributo dinâmico.
        cotacao.total_proposta_com_frete = cotacao.total_proposta
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
            desconto_final = zero
            cotado_valido = False
            elegivel_aprovacao = False
            if item is not None:
                valor_final = (
                    negociacao.valor_final_unitario
                    if negociacao is not None
                    else item.valor_unitario_cotado
                )
                cotado_valido = bool(
                    valor_final is not None
                    and valor_final > zero
                    and item.quantidade > zero
                )

                if cotado_valido:
                    desconto_final = calcular_desconto_adjudicacao(
                        item,
                        item.quantidade,
                        valor_final,
                    )
                    total_final = max(
                        (valor_final * item.quantidade) - desconto_final,
                        zero,
                    )

                elegivel_aprovacao = bool(
                    cotado_valido
                    and cotacao.enviada_aprovacao_em
                    and item_tecnicamente_aprovado(item, usar_prefetch=True)
                )

            ofertas.append(
                {
                    "cotacao": cotacao,
                    "item": item,
                    "menor_preco": False,
                    "negociacao": negociacao,
                    "valor_final": valor_final,
                    "total_final": total_final,
                    "desconto_final": desconto_final,
                    "cotado_valido": cotado_valido,
                    "elegivel_aprovacao": elegivel_aprovacao,
                }
            )

        valores_validos = [
            oferta["item"].valor_unitario_cotado
            for oferta in ofertas
            if (
                oferta["item"] is not None
                and oferta["item"].valor_unitario_cotado is not None
                and oferta["item"].valor_unitario_cotado > zero
            )
        ]
        menor_preco = min(valores_validos) if valores_validos else None
        for oferta in ofertas:
            oferta["menor_preco"] = bool(
                oferta["item"] is not None
                and oferta["item"].valor_unitario_cotado is not None
                and oferta["item"].valor_unitario_cotado > zero
                and menor_preco is not None
                and oferta["item"].valor_unitario_cotado == menor_preco
            )

        valores_finais_elegiveis = [
            oferta["valor_final"]
            for oferta in ofertas
            if (
                oferta["elegivel_aprovacao"]
                and oferta["valor_final"] is not None
                and oferta["valor_final"] > zero
            )
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

        quantidade_selecionada = quantidade_por_item.get(item.pk, zero)

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

        item_cotado = itens_por_id.get(adjudicacao.item_cotado_id) or adjudicacao.item_cotado

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
    from datetime import UTC, datetime, time

    from compras.services.sla import indicador_processo, resumir_sla_listagem

    qs = _aplicar_filtros(request, ProcessoCompra.objects.all())
    referencia = timezone.now()
    hoje = timezone.localdate(referencia)
    _, sla_resumo = resumir_sla_listagem(qs, referencia)
    status_terminais = {
        ProcessoCompra.Status.CONTRATADO,
        ProcessoCompra.Status.REPROVADO,
        ProcessoCompra.Status.CANCELADO,
    }
    # A contagem anterior comparava a data do timestamp retornado pelo banco (UTC).
    limite_contratados = datetime.combine(hoje - timedelta(days=30), time.min, tzinfo=UTC)
    totais_por_status = {
        linha["status"]: linha for linha in qs.order_by().values("status").annotate(
            total=Count("pk"),
            atrasados=Count("pk", filter=Q(
                item_cronograma__prazo_limite_contratacao__lt=hoje,
                data_contratacao_concluida__isnull=True,
            )),
            recentes=Count("pk", filter=Q(data_contratacao_concluida__gte=limite_contratados)),
        )
    }
    ativos = [linha for status, linha in totais_por_status.items() if status not in status_terminais]

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

    # Limita apenas os cartões renderizados, sem afetar totais, SLA ou filtros.
    # A listagem completa continua disponível e paginada.
    limite_cartoes_coluna = 30
    qs_ids = qs.order_by("-atualizado_em", "-pk").values_list("pk", flat=True)
    colunas = []
    ids_exibidos = []
    for chave, titulo, statuses, descricao in definicoes:
        quantidade_total = sum(totais_por_status.get(status, {}).get("total", 0) for status in statuses)
        ids_coluna = []
        for status in statuses:
            if status not in totais_por_status:
                continue
            disponiveis = limite_cartoes_coluna - len(ids_coluna)
            if disponiveis <= 0:
                break
            ids_coluna.extend(qs_ids.filter(status=status)[:disponiveis])
        ids_exibidos.extend(ids_coluna)
        colunas.append({
            "chave": chave,
            "titulo": titulo,
            "descricao": descricao,
            "quantidade_total": quantidade_total,
            "ids_exibidos": ids_coluna,
        })

    cartoes_por_id = {
        processo.pk: processo
        for processo in _qs_processos().filter(pk__in=ids_exibidos).prefetch_related("transicoes_sla")
    } if ids_exibidos else {}
    for processo in cartoes_por_id.values():
        processo.sla = indicador_processo(processo, referencia)
    for coluna in colunas:
        coluna["processos"] = [
            cartoes_por_id[pk] for pk in coluna.pop("ids_exibidos") if pk in cartoes_por_id
        ]

    return render(
        request,
        "compras/dashboard.html",
        {
            "ativos": sum(linha["total"] for linha in ativos),
            "atrasados": sum(linha["atrasados"] for linha in ativos),
            "aguardando": totais_por_status.get(ProcessoCompra.Status.AGUARDANDO_APROVACAO, {}).get("total", 0),
            "ajustes": totais_por_status.get(ProcessoCompra.Status.AJUSTE_SOLICITADO, {}).get("total", 0),
            "contratados": totais_por_status.get(ProcessoCompra.Status.CONTRATADO, {}).get("recentes", 0),
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
            "sla_resumo": sla_resumo,
            "pode_administrar_sla": possui_acao_compras(request.user, AcaoCompra.ADMINISTRAR),
        },
    )


# ============================================================
# LISTA DE PROCESSOS
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def lista_processos(request):
    from compras.services.sla import indicador_processo, resumir_sla_listagem

    referencia = timezone.now()
    qs, sla_resumo = resumir_sla_listagem(
        _aplicar_filtros(request, _qs_processos()),
        referencia,
        situacao_etapa=(request.GET.get("sla") or "").strip(),
    )
    qs = qs.order_by("-criado_em", "-pk").prefetch_related("transicoes_sla")
    pagina = Paginator(qs, 30).get_page(request.GET.get("page"))
    pagina.object_list = list(pagina.object_list)
    for processo_item in pagina:
        processo_item.sla = indicador_processo(processo_item, referencia)
    return render(
        request,
        "compras/processos_lista.html",
        {
            "processos": pagina.object_list,
            "pagina": pagina,
            "sla_resumo": sla_resumo,
            "pode_administrar_sla": possui_acao_compras(request.user, AcaoCompra.ADMINISTRAR),
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


@require_safe
@compras_acao_required(AcaoCompra.VISUALIZAR)
def cobertura_necessidade(request, pk, necessidade_id):
    necessidade = get_object_or_404(
        NecessidadeCompra.objects.select_related("processo__obra", "material").filter(
            processo_id=pk, material_id__isnull=False,
        ).exclude(situacao=NecessidadeCompra.Situacao.CANCELADA),
        pk=necessidade_id,
    )
    return render(request, "compras/necessidade_cobertura.html", {
        "necessidade": necessidade,
        "cobertura": resumir_cobertura_necessidade(necessidade),
    })


@require_safe
@compras_acao_required(AcaoCompra.VISUALIZAR)
def historico_processo(request, pk):
    processo = get_object_or_404(ProcessoCompra.objects.only("pk", "numero", "titulo"), pk=pk)
    return _render_secao_processo(request, processo, "Histórico do processo", "compras/_processo_historico.html", {
        "historico": processo.historico.select_related("usuario")[:100],
    })


def _render_secao_processo(request, processo, titulo, template, contexto):
    if request.GET.get("fragmento") == "1":
        return render(request, template, {"processo": processo, **contexto})
    return render(request, "compras/processo_secao.html", {
        "processo": processo, "titulo": titulo, "template_secao": template, **contexto,
    })


@require_safe
@compras_acao_required(AcaoCompra.VISUALIZAR)
def pedidos_processo(request, pk):
    from compras.services.sla import indicador_pedido

    processo = get_object_or_404(ProcessoCompra.objects.only("pk", "numero", "titulo"), pk=pk)
    contratacoes = list(
        processo
        .contratacoes
        .filter(
            cancelada=False, documento__isnull=False,
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
            "fornecedor", "prazo_sla", "processo__item_cronograma__cronograma_obra",
        )
        .annotate(ultimo_recebimento_em=Subquery(
            RecebimentoPedido.objects.filter(pedido_id=OuterRef("pk"))
            .order_by("-criado_em", "-pk").values("criado_em")[:1],
        ))
        .prefetch_related(
            "itens",
            Prefetch("anexos", queryset=PedidoCompraAnexo.objects.select_related("enviado_por")),
        )
        .order_by(
            "fornecedor__nome"
        )
    )

    # Centraliza, para consulta, todos os arquivos já anexados ao processo.
    # A tela de Pedidos apenas exibe esses arquivos; não exige nova seleção
    # de fornecedor nem novo upload nesta etapa.
    documentos_processo = []

    cotacoes_com_documento = (processo.cotacoes.exclude(documento="")
                              .exclude(documento__isnull=True).select_related("fornecedor", "criado_por"))
    for cotacao in cotacoes_com_documento:
        if cotacao.documento:
            documentos_processo.append(
                {
                    "etapa": "Cotação",
                    "pk": cotacao.pk,
                    "rota_download": "compras:baixar_documento_cotacao",
                    "fornecedor": cotacao.fornecedor,
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
                    "pk": contratacao.pk,
                    "rota_download": "compras:baixar_documento_contratacao",
                    "fornecedor": contratacao.fornecedor,
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
                    "pk": anexo.pk,
                    "rota_download": "compras:baixar_anexo_pedido",
                    "fornecedor": pedido.fornecedor,
                    "nome": anexo.nome_arquivo,
                    "responsavel": anexo.enviado_por,
                    "data": anexo.criado_em,
                }
            )

    documentos_processo.sort(
        key=lambda item: item["data"],
        reverse=True,
    )

    return _render_secao_processo(request, processo, "Pedidos", "compras/_processo_pedidos.html", {
        "sla_pedidos": [(pedido, indicador_pedido(pedido)) for pedido in pedidos],
        "documentos_processo": documentos_processo,
        "pode_gerenciar_pedidos": possui_acao_compras(request.user, AcaoCompra.GERENCIAR_PEDIDOS),
    })


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def detalhe_processo(
    request,
    pk,
):
    from compras.services.sla import indicador_processo

    processo = get_object_or_404(
        ProcessoCompra.objects
        .select_related(
            "obra",
            "comprador",
            "item_cronograma__cronograma_obra",
        ),
        pk=pk,
    )

    if processo.fluxo_grande_fornecedor:
        return redirect("compras:grande_fornecedor_matriz", pk=processo.pk)

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
        "pode_excecao_estoque": possui_acao_compras(
            request.user, AcaoCompra.EXCECAO_ESTOQUE
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

    valores_adjudicados = (
        AdjudicacaoCompra.objects.filter(necessidade_id=OuterRef("pk"), cancelada=False)
        .order_by()
        .values("necessidade_id")
        .annotate(total=Sum("quantidade"))
        .values("total")
    )
    necessidades = list(
        processo
        .necessidades
        .exclude(situacao=NecessidadeCompra.Situacao.CANCELADA)
        .annotate(_quantidade_adjudicada=Coalesce(Subquery(valores_adjudicados), Decimal("0")))
        .select_related(
            "atividade_origem",
            "material__unidade",
        )
        .order_by(
            "descricao",
            "id",
        )
    )

    pode_editar_itens = (
        processo.etapa_atual == ProcessoCompra.Etapa.COTACAO
        and permissoes_compras["pode_solicitar"]
    )
    form_necessidade = None
    if pode_editar_itens:
        form_necessidade = NecessidadeCompraForm(processo=processo)
        material_choices = [opcao for opcao in form_necessidade.fields["material"].choices]
        form_necessidade.fields["material"].choices = material_choices

        for necessidade in necessidades:
            necessidade.form_edicao = NecessidadeCompraForm(
                processo=processo,
                initial={
                    "material": necessidade.material_id,
                    "quantidade": necessidade.quantidade_incluida,
                    "observacao": necessidade.observacao,
                },
            )
            necessidade.form_edicao.fields["material"].choices = material_choices

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

    cotacoes = list(
        processo
        .cotacoes
        .select_related(
            "fornecedor",
            "criado_por",
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

    form_envio_fornecedor = None
    form_proposta_nova = None
    pode_cadastrar_nova_proposta = False
    compatibilizacoes_forms = []
    form_decisao_lote = None

    fase_comercial_aberta = processo.etapa_atual in {
        ProcessoCompra.Etapa.COTACAO, ProcessoCompra.Etapa.COMPATIBILIZACAO,
        ProcessoCompra.Etapa.NEGOCIACAO, ProcessoCompra.Etapa.APROVACAO,
    }
    fase_analise_aberta = processo.etapa_atual in {
        ProcessoCompra.Etapa.COMPATIBILIZACAO, ProcessoCompra.Etapa.NEGOCIACAO, ProcessoCompra.Etapa.APROVACAO,
    }

    pode_cotar = fase_comercial_aberta and permissoes_compras["pode_cotar"]
    propostas_forms = []
    for cotacao in cotacoes:
        form = None
        if pode_cotar and not (
            cotacao.enviada_compatibilizacao_em or cotacao.enviada_negociacao_em or cotacao.enviada_aprovacao_em
        ):
            form = PropostaCompletaForm(processo=processo, cotacao=cotacao, necessidades=necessidades)
            fornecedor = form.fields["fornecedor"]
            fornecedor.choices = [(cotacao.fornecedor_id, fornecedor.label_from_instance(cotacao.fornecedor))]
        propostas_forms.append({"cotacao": cotacao, "form": form})

    if pode_cotar:
        form_envio_fornecedor = SolicitacaoCotacaoEnvioForm(processo=processo)
        form_proposta_nova = PropostaCompletaForm(
            processo=processo,
            necessidades=necessidades,
        )
        pode_cadastrar_nova_proposta = form_proposta_nova.fields["fornecedor"].queryset.exists()
    if pode_editar and fase_analise_aberta:
        if exige_compatibilizacao and permissoes_compras["pode_compatibilizar"]:
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
                        itens=list(cotacao.itens.all()),
                    ),
                }
                for cotacao in cotacoes_para_compatibilizar
            ]
        if permissoes_compras["pode_negociar"]:
            form_decisao_lote = DecisaoComercialLoteForm(processo=processo)

    aprovacao_aprovada = (
        processo.aprovacoes.filter(decisao=AprovacaoCompra.Decisao.APROVADO)
        .select_related("usuario", "alcada")
        .order_by("-criado_em", "-id")
        .first()
    )

    contexto = {
        "processo": processo,
        "sla": indicador_processo(processo),
        "data_necessaria_obra": data_necessaria_processo(processo),
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

        "pedidos_total": processo.pedidos.count(),

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
        "form_decisao_lote": form_decisao_lote,

        "form_necessidade": form_necessidade,

        "form_aprovacao": (
            AprovacaoForm(processo=processo)
            if pode_aprovar and cotacoes_em_aprovacao
            else None
        ),

        **dados_comerciais,
    }

    return render(
        request,
        "compras/processo_detalhe.html",
        contexto,
    )



@compras_acao_required(AcaoCompra.SOLICITAR)
def nova_compra_avulsa(request):
    form = CompraAvulsaForm(request.POST or None)
    formset = ItemCompraAberturaFormSet(request.POST or None, prefix="itens")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        itens = [f.cleaned_data for f in formset if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        try:
            processo = criar_processo_avulso(
                obra=form.cleaned_data["obra"],
                apropriacao=form.cleaned_data["apropriacao"],
                titulo=form.cleaned_data["titulo"],
                comprador=form.cleaned_data.get("comprador"),
                descricao=form.cleaned_data.get("descricao", ""),
                observacao=form.cleaned_data.get("observacao", ""),
                itens=itens,
                usuario=request.user,
                iniciar_cotacao=request.POST.get("acao") != "rascunho",
            )
            messages.success(request, f"Compra avulsa {processo.numero} criada com {len(itens)} item(ns).")
            return redirect("compras:detalhe_processo", pk=processo.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "compras/compra_avulsa_form.html", {"form": form, "formset": formset,
        "pode_excecao_estoque": possui_acao_compras(request.user, AcaoCompra.EXCECAO_ESTOQUE)})

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

    processos_existentes = []
    processos_ativos_existentes = []

    if item_inicial is not None:
        processos_existentes = list(
            ProcessoCompra.objects
            .filter(item_cronograma=item_inicial)
            .select_related("comprador")
            .order_by("-criado_em", "-id")
        )
        processos_ativos_existentes = [
            processo
            for processo in processos_existentes
            if processo.status not in {
                ProcessoCompra.Status.CANCELADO,
                ProcessoCompra.Status.REPROVADO,
                ProcessoCompra.Status.CONTRATADO,
            }
        ]

    # A abertura deve respeitar a mesma classificação nativa já usada pelo
    # Cronograma de Suprimentos, sem tentar reinterpretar o texto da categoria.
    eh_grande_fornecedor = bool(
        item_inicial and item_inicial.usa_fluxo_grande_fornecedor
    )
    FormSetAbertura = (
        ItemCompraAberturaGrandeFornecedorFormSet
        if eh_grande_fornecedor
        else ItemCompraAberturaFormSet
    )
    formset = FormSetAbertura(
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

                apropriacao=(
                    form.cleaned_data[
                        "apropriacao"
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

            if processo.fluxo_grande_fornecedor:
                return redirect("compras:grande_fornecedor_matriz", pk=processo.pk)
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
            "eh_grande_fornecedor": eh_grande_fornecedor,
            "permite_sem_atividade": getattr(form, "permite_sem_atividade", False),
            "processos_existentes": processos_existentes,
            "processos_ativos_existentes": processos_ativos_existentes,
            "pode_excecao_estoque": possui_acao_compras(request.user, AcaoCompra.EXCECAO_ESTOQUE),
        },
    )


@compras_acao_required(AcaoCompra.VISUALIZAR)
def pdf_pedido_compra(request, pedido_id):
    pedido = get_object_or_404(
        PedidoCompra.objects
        .select_related("obra", "fornecedor", "processo", "responsavel")
        .prefetch_related("itens"),
        pk=pedido_id,
    )
    try:
        conteudo = gerar_pdf_pedido_compra(pedido)
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("compras:lista_pedidos")

    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="pedido-{pedido.numero}.pdf"'
    return resposta


@compras_acao_required(AcaoCompra.VISUALIZAR)
def pdf_solicitacao_cotacao(request, pk):
    processo = get_object_or_404(
        ProcessoCompra.objects.select_related("obra", "item_cronograma", "criado_por", "comprador"),
        pk=pk,
    )
    try:
        fornecedor = None
        fornecedor_id = (request.GET.get("fornecedor") or "").strip()
        if fornecedor_id:
            if not fornecedor_id.isdigit():
                raise ValidationError("Fornecedor inválido.")
            from cadastros.models import Fornecedor
            fornecedor = Fornecedor.objects.filter(
                pk=int(fornecedor_id),
                solicitacoes_cotacao__processo=processo,
            ).first()
            if fornecedor is None:
                raise ValidationError("Fornecedor não vinculado à cotação deste processo.")
        conteudo = gerar_pdf_solicitacao_cotacao(processo, fornecedor=fornecedor)
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("compras:detalhe_processo", pk=processo.pk)

    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="cotacao-materiais-{processo.numero}.pdf"'
    return resposta


# ============================================================
# PEDIDOS
# ============================================================


@compras_acao_required(
    AcaoCompra.VISUALIZAR
)
def lista_pedidos(request):
    from compras.services.sla import indicador_pedido

    pedidos = (
        PedidoCompra.objects
        .select_related(
            "obra",
            "fornecedor",
            "processo__item_cronograma__cronograma_obra",
            "prazo_sla",
        )
        .prefetch_related(
            "itens",
            Prefetch("anexos", queryset=PedidoCompraAnexo.objects.select_related("enviado_por")),
            "recebimentos__usuario",
            "recebimentos__itens__item_pedido",
        )
        .filter(processo__fluxo_grande_fornecedor=False)
        .order_by(
            "-criado_em", "-pk"
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

    pagina = Paginator(pedidos, 25).get_page(request.GET.get("page"))
    pagina.object_list = list(pagina.object_list)
    for pedido in pagina:
        pedido.indicador_prazo = indicador_pedido(pedido)
        ultimo_recebimento = next(iter(pedido.recebimentos.all()), None)
        pedido.ultimo_recebimento_em = ultimo_recebimento.criado_em if ultimo_recebimento else None
        pedido.transicoes_status_permitidas = transicoes_status_permitidas(pedido)

    return render(
        request,
        "compras/pedidos_lista.html",
        {
            "pedidos": pagina.object_list,
            "pagina": pagina,

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
