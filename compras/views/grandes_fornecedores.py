from collections import OrderedDict
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import FileResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from cadastros.models import Fornecedor, Material
from core.validators import validar_documento_upload
from usuarios.models import AcaoCompra

from compras.models import (
    AprovacaoCompra,
    GrandeFornecedorItem,
    GrandeFornecedorOferta,
    GrandeFornecedorParticipante,
    HistoricoProcessoCompra,
    ParcelaGrandeFornecedor,
    ProcessoCompra,
)
from compras.services.grandes_fornecedores import (
    adicionar_item,
    adicionar_oferta_item,
    adicionar_parcela,
    adicionar_participante,
    adicionar_rateio,
    atualizar_item,
    atualizar_linha,
    avancar_para_negociacao,
    decidir_aprovacao,
    enviar_para_aprovacao,
    excluir_item,
    excluir_oferta_item,
    obter_ou_criar_fluxo,
    importar_itens_ficha_tecnica,
    sincronizar_itens_ficha_tecnica,
    vincular_item_manual_a_ficha,
    salvar_valor_oferta,
    selecionar_fornecedor_item,
    atualizar_status_operacional_item,
    atualizar_previsao_operacional_item,
)
from compras.services.permissoes import compras_acao_required, possui_acao_compras


def _processo(pk):
    processo = get_object_or_404(
        ProcessoCompra.objects.select_related(
            "obra", "item_cronograma", "comprador", "categoria_grande_fornecedor"
        ),
        pk=pk,
    )
    if not processo.fluxo_grande_fornecedor:
        raise ValidationError("Este processo não utiliza o fluxo de Grande Fornecedor.")
    return processo


def _erro_json(exc, status=400):
    texto = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    return JsonResponse({"ok": False, "erro": texto}, status=status)


def _pode_editar_matriz(usuario):
    return any(
        possui_acao_compras(usuario, acao)
        for acao in (AcaoCompra.COMPATIBILIZAR, AcaoCompra.NEGOCIAR, AcaoCompra.ADMINISTRAR)
    )


def _exigir_edicao(usuario):
    if not _pode_editar_matriz(usuario):
        raise PermissionDenied("Sem permissão para editar a matriz de Grande Fornecedor.")


@compras_acao_required(AcaoCompra.VISUALIZAR)
def matriz_grande_fornecedor(request, pk):
    processo = _processo(pk)
    fluxo = obter_ou_criar_fluxo(processo)

    pode_editar = _pode_editar_matriz(request.user) and processo.etapa_atual in {
        processo.Etapa.COMPATIBILIZACAO,
        processo.Etapa.NEGOCIACAO,
    } and processo.status not in {
        processo.Status.CANCELADO,
        processo.Status.REPROVADO,
        processo.Status.CONTRATADO,
        processo.Status.APROVADO,
        processo.Status.EM_CONTRATACAO,
    }

    # A Ficha Técnica é contínua: sempre que a matriz editável é aberta,
    # sincronizamos os itens já cadastrados da categoria GF deste processo.
    # A função é idempotente e não duplica itens já vinculados.
    resultado_sincronizacao = {
        "criados": 0,
        "atualizados": 0,
        "conflitos": [],
        "sem_ficha": False,
        "categoria": processo.categoria_grande_fornecedor,
    }
    if pode_editar and processo.categoria_grande_fornecedor_id:
        resultado_sincronizacao = sincronizar_itens_ficha_tecnica(
            processo=processo,
            usuario=request.user,
        )

    itens = list(
        fluxo.itens
        .select_related("material__unidade", "item_ficha_tecnica", "participante_aprovado__fornecedor", "pedido_item__pedido")
        .prefetch_related("ofertas__participante__fornecedor", "ofertas__historico")
        .all()
    )
    participantes = list(
        fluxo.participantes.select_related("fornecedor").order_by("fornecedor__nome", "id")
    )
    materiais = list(
        Material.objects.filter(ativo=True)
        .select_related("unidade")
        .order_by("nome", "especificacao", "codigo")
    )
    materiais_json = [
        {
            "id": material.pk,
            "label": f"{material.codigo or 'MAT'} · {material.descricao_completa}",
            "unidade": material.unidade.sigla,
        }
        for material in materiais
    ]
    fornecedores = Fornecedor.objects.filter(ativo=True).order_by("nome", "nome_fantasia")
    pedidos = list(
        processo.pedidos
        .exclude(status="CANCELADO")
        .select_related("fornecedor")
        .prefetch_related("itens")
        .order_by("fornecedor__nome", "id")
    )
    aprovacoes = processo.aprovacoes.select_related("usuario").order_by("-ciclo", "-id")[:10]

    # Estrutura pronta para o template: uma linha por material e uma coluna por fornecedor.
    matriz_linhas = []
    for item in itens:
        ofertas_por_participante = {o.participante_id: o for o in item.ofertas.all()}
        celulas = []
        for participante in participantes:
            oferta = ofertas_por_participante.get(participante.pk)
            celulas.append({
                "participante": participante,
                "oferta": oferta,
                "escolhida": item.participante_aprovado_id == participante.pk,
            })
        matriz_linhas.append({"item": item, "celulas": celulas})

    fornecedores_escolhidos = {
        item.participante_aprovado.fornecedor_id
        for item in itens
        if item.participante_aprovado_id
    }
    valor_escolhido = sum((item.valor_total for item in itens), Decimal("0"))
    categoria_ficha_processo = processo.categoria_grande_fornecedor
    itens_ficha_pendentes = []
    itens_manuais = [item for item in itens if not item.item_ficha_tecnica_id]
    ficha_tecnica_existe = True

    if categoria_ficha_processo is not None:
        try:
            ficha = processo.obra.ficha_tecnica
        except ObjectDoesNotExist:
            ficha_tecnica_existe = False
        else:
            from obras.models import ItemFichaTecnica

            ids_importados = {
                item.item_ficha_tecnica_id
                for item in itens
                if item.item_ficha_tecnica_id
            }
            itens_ficha_pendentes = list(
                ItemFichaTecnica.objects.filter(
                    aplicacao_categoria__ficha=ficha,
                    aplicacao_categoria__categoria=categoria_ficha_processo,
                    aplicacao_categoria__ativo=True,
                    ativo=True,
                )
                .exclude(pk__in=ids_importados)
                .select_related(
                    "tipo_item", "tipo_item__unidade_padrao", "unidade", "opcao_especificacao",
                    "aplicacao_categoria__categoria",
                    "aplicacao_categoria__ambiente__pavimento",
                )
                .order_by(
                    "aplicacao_categoria__ambiente__pavimento__ordem",
                    "ordem", "id",
                )
            )


    return render(
        request,
        "compras/grande_fornecedor_matriz.html",
        {
            "processo": processo,
            "fluxo": fluxo,
            "itens": itens,
            "matriz_linhas": matriz_linhas,
            "participantes": participantes,
            "materiais": materiais,
            "materiais_json": materiais_json,
            "fornecedores": fornecedores,
            "aprovacoes": aprovacoes,
            "pedidos": pedidos,
            "decisoes": AprovacaoCompra.Decisao,
            "gatilhos": ParcelaGrandeFornecedor.Gatilho.choices,
            "pode_editar": pode_editar,
            "pode_aprovar": possui_acao_compras(request.user, AcaoCompra.APROVAR),
            "qtd_fornecedores_escolhidos": len(fornecedores_escolhidos),
            "valor_escolhido": valor_escolhido,
            "categoria_ficha_processo": categoria_ficha_processo,
            "itens_ficha_pendentes": itens_ficha_pendentes,
            "itens_manuais": itens_manuais,
            "qtd_itens_ficha_pendentes": len(itens_ficha_pendentes),
            "ficha_tecnica_existe": ficha_tecnica_existe,
            "sincronizacao_ficha": resultado_sincronizacao,
        },
    )


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def importar_ficha_tecnica(request, pk):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    try:
        quantidade = importar_itens_ficha_tecnica(
            processo=processo,
            usuario=request.user,
        )
        messages.success(request, f"{quantidade} item(ns) importado(s) da Ficha Técnica.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def vincular_item_ficha(request, pk, item_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(
        GrandeFornecedorItem,
        pk=item_id,
        fluxo__processo=processo,
        item_ficha_tecnica__isnull=True,
    )
    try:
        from obras.models import ItemFichaTecnica
        item_ficha = get_object_or_404(
            ItemFichaTecnica.objects.select_related(
                "tipo_item__unidade_padrao", "unidade", "opcao_especificacao",
                "aplicacao_categoria__ficha",
                "aplicacao_categoria__ambiente__pavimento",
            ),
            pk=request.POST.get("item_ficha_tecnica"),
            aplicacao_categoria__ficha__obra=processo.obra,
            aplicacao_categoria__categoria=processo.categoria_grande_fornecedor,
            ativo=True,
        )
        vincular_item_manual_a_ficha(
            processo=processo,
            micro_item=micro,
            item_ficha=item_ficha,
            usuario=request.user,
        )
        messages.success(request, "Item manual vinculado à Ficha Técnica sem perder as ofertas já lançadas.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def incluir_item(request, pk):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    try:
        material = get_object_or_404(Material, pk=request.POST.get("material"), ativo=True)
        adicionar_item(
            processo=processo,
            material=material,
            quantidade=request.POST.get("quantidade"),
            pavimento=request.POST.get("pavimento", ""),
            local=request.POST.get("local", ""),
            usuario=request.user,
        )
        messages.success(request, "Item incluído na matriz.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def salvar_linha(request, pk, item_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(
        GrandeFornecedorItem.objects.select_related("fluxo__processo"),
        pk=item_id,
        fluxo__processo=processo,
    )
    try:
        material = get_object_or_404(Material, pk=request.POST.get("material"), ativo=True)
        micro = atualizar_linha(
            micro_item=micro,
            material=material,
            quantidade=request.POST.get("quantidade"),
            pavimento=request.POST.get("pavimento"),
            local=request.POST.get("local"),
            usuario=request.user,
        )
        return JsonResponse(
            {
                "ok": True,
                "item_id": micro.pk,
                "material": material.descricao_completa,
                "unidade": material.unidade.sigla,
                "quantidade": f"{micro.quantidade:.2f}",
                "pavimento": micro.pavimento,
                "local": micro.local,
                "valor_total": f"{micro.valor_total:.2f}",
            }
        )
    except ValidationError as exc:
        return _erro_json(exc)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def incluir_oferta(request, pk, item_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    try:
        fornecedor = get_object_or_404(Fornecedor, pk=request.POST.get("fornecedor"), ativo=True)
        adicionar_oferta_item(
            micro_item=micro,
            fornecedor=fornecedor,
            valor=request.POST.get("valor"),
            usuario=request.user,
        )
        messages.success(request, f"{fornecedor.nome_exibicao} adicionado ao material.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def excluir_oferta(request, pk, item_id, participante_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    participante = get_object_or_404(
        GrandeFornecedorParticipante, pk=participante_id, fluxo__processo=processo
    )
    try:
        excluir_oferta_item(
            micro_item=micro,
            participante=participante,
            usuario=request.user,
        )
        messages.success(request, "Oferta removida do material.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def excluir_linha(request, pk, item_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    try:
        excluir_item(micro_item=micro, usuario=request.user)
        messages.success(request, "Item removido da matriz.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def historico_item(request, pk, item_id):
    processo = _processo(pk)
    micro = get_object_or_404(
        GrandeFornecedorItem.objects.select_related("participante_aprovado__fornecedor"),
        pk=item_id,
        fluxo__processo=processo,
    )
    participante = micro.participante_aprovado
    oferta = None
    if participante:
        oferta = (
            GrandeFornecedorOferta.objects
            .filter(item=micro, participante=participante)
            .prefetch_related("historico__usuario")
            .first()
        )
    historico = [
        {
            "anterior": str(h.valor_anterior) if h.valor_anterior is not None else None,
            "novo": str(h.valor_novo),
            "diferenca": str(h.diferenca),
            "usuario": (h.usuario.get_full_name() or h.usuario.username) if h.usuario else "Sistema",
            "data": h.criado_em.strftime("%d/%m/%Y %H:%M"),
        }
        for h in (oferta.historico.all() if oferta else [])
    ]
    return JsonResponse(
        {
            "ok": True,
            "item": micro.item,
            "fornecedor": participante.fornecedor.nome_exibicao if participante else "—",
            "historico": historico,
        }
    )


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def enviar_aprovacao(request, pk):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    try:
        enviar_para_aprovacao(
            processo=processo,
            usuario=request.user,
            condicao_pagamento_resumo=request.POST.get("condicao_pagamento_resumo", ""),
        )
        messages.success(request, "Matriz enviada para aprovação do gestor.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.APROVAR)
@require_POST
def decidir(request, pk):
    processo = _processo(pk)
    try:
        _, pedidos = decidir_aprovacao(
            processo=processo,
            decisao=request.POST.get("decisao"),
            usuario=request.user,
            observacao=request.POST.get("observacao", ""),
            fornecedor=fornecedor,
            data_vencimento=parse_date(request.POST.get("data_vencimento") or ""),
            forma_pagamento=request.POST.get("forma_pagamento", ""),
        )
        if pedidos:
            messages.success(
                request,
                f"Processo aprovado. {len(pedidos)} pedido(s) separado(s) por fornecedor gerado(s).",
            )
        else:
            messages.success(request, "Decisão registrada.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
@require_POST
def salvar_status_micro_item(request, pk, item_id):
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    try:
        atualizar_item(
            micro_item=micro,
            campo="status",
            valor=request.POST.get("status"),
            usuario=request.user,
        )
        messages.success(request, f"Status de {micro.item} atualizado.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


# ---------------------------------------------------------------------------
# Compatibilidade com URLs/dados do fluxo anterior.
# ---------------------------------------------------------------------------

@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
@require_POST
def incluir_participante(request, pk):
    processo = _processo(pk)
    fornecedor = get_object_or_404(Fornecedor, pk=request.POST.get("fornecedor"), ativo=True)
    try:
        adicionar_participante(processo=processo, fornecedor=fornecedor, usuario=request.user)
        messages.success(request, f"{fornecedor.nome} vinculado ao processo.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
@require_POST
def salvar_item(request, pk, item_id):
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    try:
        atualizar_item(
            micro_item=micro,
            campo=request.POST.get("campo", ""),
            valor=request.POST.get("valor", ""),
            usuario=request.user,
        )
        return JsonResponse({"ok": True, "valor": str(getattr(micro, request.POST.get("campo", "")))})
    except ValidationError as exc:
        return _erro_json(exc)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def salvar_valor(request, pk, item_id, participante_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    participante = get_object_or_404(GrandeFornecedorParticipante, pk=participante_id, fluxo__processo=processo)
    try:
        oferta = salvar_valor_oferta(
            micro_item=micro,
            participante=participante,
            valor=request.POST.get("valor"),
            usuario=request.user,
        )
        ultimo = oferta.historico.first()
        return JsonResponse(
            {
                "ok": True,
                "valor": str(oferta.valor_atual),
                "valor_inicial": str(oferta.valor_inicial),
                "diferenca": str(ultimo.diferenca if ultimo else Decimal("0")),
                "historico": oferta.historico.count(),
                "valor_total_item": str(micro.valor_total),
                "escolhida": micro.participante_aprovado_id == participante.pk,
            }
        )
    except ValidationError as exc:
        return _erro_json(exc)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def historico_valor(request, pk, item_id, participante_id):
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    participante = get_object_or_404(
        GrandeFornecedorParticipante.objects.select_related("fornecedor"),
        pk=participante_id,
        fluxo__processo=processo,
    )
    oferta = (
        GrandeFornecedorOferta.objects
        .filter(item=micro, participante=participante)
        .prefetch_related("historico__usuario")
        .first()
    )
    historico = [
        {
            "anterior": str(h.valor_anterior) if h.valor_anterior is not None else None,
            "novo": str(h.valor_novo),
            "diferenca": str(h.diferenca),
            "usuario": (h.usuario.get_full_name() or h.usuario.username) if h.usuario else "Sistema",
            "data": h.criado_em.strftime("%d/%m/%Y %H:%M"),
        }
        for h in (oferta.historico.all() if oferta else [])
    ]
    return JsonResponse({"ok": True, "item": micro.item, "fornecedor": participante.fornecedor.nome, "historico": historico})


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
@require_POST
def anexar_contrato(request, pk, participante_id):
    processo = _processo(pk)
    participante = get_object_or_404(GrandeFornecedorParticipante, pk=participante_id, fluxo__processo=processo)
    arquivo = request.FILES.get("documento_contrato")
    if not arquivo:
        messages.error(request, "Selecione um arquivo.")
    else:
        try:
            validar_documento_upload(arquivo)
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            participante.documento_contrato = arquivo
            participante.save(update_fields=["documento_contrato"])
            messages.success(request, f"Documento de {participante.fornecedor.nome} anexado.")
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def baixar_contrato(request, pk, participante_id):
    processo = _processo(pk)
    participante = get_object_or_404(GrandeFornecedorParticipante, pk=participante_id, fluxo__processo=processo)
    if not participante.documento_contrato:
        return JsonResponse({"erro": "Documento não encontrado."}, status=404)
    arquivo = participante.documento_contrato.open("rb")
    nome = participante.documento_contrato.name.rsplit("/", 1)[-1]
    return FileResponse(arquivo, as_attachment=False, filename=nome)


@compras_acao_required(AcaoCompra.COMPATIBILIZAR)
@require_POST
def concluir_compatibilizacao(request, pk):
    processo = _processo(pk)
    try:
        avancar_para_negociacao(processo=processo, usuario=request.user)
        messages.success(request, "Matriz mantida na etapa comercial unificada.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.VISUALIZAR)
@require_POST
def selecionar_fornecedor_micro_item(request, pk, item_id):
    _exigir_edicao(request.user)
    processo = _processo(pk)
    micro = get_object_or_404(GrandeFornecedorItem, pk=item_id, fluxo__processo=processo)
    participante = get_object_or_404(
        GrandeFornecedorParticipante,
        pk=request.POST.get("participante"),
        fluxo__processo=processo,
    )
    try:
        selecionar_fornecedor_item(
            processo=processo,
            micro_item=micro,
            participante=participante,
            usuario=request.user,
        )
        return JsonResponse({"ok": True})
    except ValidationError as exc:
        return _erro_json(exc)


@compras_acao_required(AcaoCompra.NEGOCIAR)
@require_POST
def incluir_parcela(request, pk):
    processo = _processo(pk)
    try:
        adicionar_parcela(
            processo=processo,
            descricao=request.POST.get("descricao", ""),
            percentual=request.POST.get("percentual") or None,
            valor=request.POST.get("valor") or None,
            data_prevista=parse_date(request.POST.get("data_prevista") or ""),
            gatilho=request.POST.get("gatilho") or "DATA",
        )
        messages.success(request, "Condição de pagamento adicionada.")
    except (ValidationError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)


@compras_acao_required(AcaoCompra.NEGOCIAR)
@require_POST
def incluir_rateio(request, pk, parcela_id):
    processo = _processo(pk)
    parcela = get_object_or_404(ParcelaGrandeFornecedor, pk=parcela_id, fluxo__processo=processo)
    try:
        fornecedor = None
        fornecedor_id = request.POST.get("fornecedor")
        if fornecedor_id:
            fornecedor = get_object_or_404(Fornecedor, pk=fornecedor_id)
        adicionar_rateio(
            parcela=parcela,
            beneficiario_nome=request.POST.get("beneficiario_nome", ""),
            documento=request.POST.get("documento", ""),
            valor=request.POST.get("valor"),
            observacao=request.POST.get("observacao", ""),
            fornecedor=fornecedor,
            data_vencimento=parse_date(request.POST.get("data_vencimento") or ""),
        )
        messages.success(request, "Beneficiário incluído no rateio.")
    except (ValidationError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("compras:grande_fornecedor_matriz", pk=pk)



def _pode_operar_acompanhamento(usuario):
    return any(
        possui_acao_compras(usuario, acao)
        for acao in (AcaoCompra.GERENCIAR_PEDIDOS, AcaoCompra.RECEBER_PEDIDOS, AcaoCompra.ADMINISTRAR)
    )


def _voltar_acompanhamento():
    return redirect("compras:grandes_fornecedores")


@compras_acao_required(AcaoCompra.VISUALIZAR)
def painel_grandes_fornecedores_compras(request):
    from compras.services.grande_fornecedor_status import (
        STATUS_ACOMPANHAMENTO,
        status_por_recebimento,
        transicoes_manuais,
    )
    from obras.models import Obra

    qs = (
        GrandeFornecedorItem.objects
        .select_related(
            "fluxo__processo", "fluxo__processo__obra", "fluxo__processo__item_cronograma",
            "material__unidade", "participante_aprovado__fornecedor", "pedido_item__pedido__fornecedor",
        )
        .filter(fluxo__processo__fluxo_grande_fornecedor=True)
        .order_by("fluxo__processo__obra__nome", "fluxo__processo__numero", "pedido_item__pedido__numero", "ordem", "id")
    )
    obra = (request.GET.get("obra") or "").strip()
    status = (request.GET.get("status") or "").strip()
    busca = (request.GET.get("q") or "").strip()
    if obra:
        qs = qs.filter(fluxo__processo__obra_id=obra)
    if busca:
        qs = qs.filter(
            Q(fluxo__processo__titulo__icontains=busca)
            | Q(fluxo__processo__numero__icontains=busca)
            | Q(material__nome__icontains=busca)
            | Q(material__codigo__icontains=busca)
            | Q(participante_aprovado__fornecedor__nome__icontains=busca)
            | Q(participante_aprovado__fornecedor__nome_fantasia__icontains=busca)
            | Q(pedido_item__pedido__numero__icontains=busca)
            | Q(pavimento__icontains=busca)
            | Q(local__icontains=busca)
        )

    labels = dict(GrandeFornecedorItem.Status.choices)
    rows, pedidos_recebimento = [], OrderedDict()
    total_itens = total_recebidos = 0
    for item in qs:
        pedido_item = item.pedido_item
        pedido = pedido_item.pedido if pedido_item else None
        quantidade = pedido_item.quantidade if pedido_item else item.quantidade
        quantidade_recebida = pedido_item.quantidade_recebida if pedido_item else item.quantidade_recebida
        status_codigo = item.status
        if pedido_item:
            status_codigo = status_por_recebimento(pedido_item.quantidade, pedido_item.quantidade_recebida, item.status)
        if status and status_codigo != status:
            continue
        transicoes = [
            (codigo, labels[codigo]) for codigo in transicoes_manuais(status_codigo)
            if codigo in labels and codigo != GrandeFornecedorItem.Status.CANCELADO
        ]
        row = {
            "item": item, "processo": item.fluxo.processo, "material": item.material,
            "fornecedor": item.participante_aprovado.fornecedor if item.participante_aprovado_id else None,
            "pedido": pedido, "pedido_item": pedido_item, "quantidade": quantidade,
            "quantidade_recebida": quantidade_recebida, "status_codigo": status_codigo,
            "status_label": labels.get(status_codigo, status_codigo),
            "previsao": item.previsao_entrega or (pedido.previsao_entrega_atual if pedido else None),
            "transicoes": transicoes,
        }
        rows.append(row)
        if pedido:
            grupo = pedidos_recebimento.setdefault(pedido.pk, {"pedido": pedido, "rows": []})
            grupo["rows"].append(row)
        total_itens += 1
        if status_codigo == GrandeFornecedorItem.Status.ENTREGUE:
            total_recebidos += 1

    historico_por_item = {}
    if rows:
        processos_ids = {row["processo"].pk for row in rows}
        itens_ids = {row["item"].pk for row in rows}
        eventos = (
            HistoricoProcessoCompra.objects
            .select_related("usuario")
            .filter(
                processo_id__in=processos_ids,
                tipo__in=("GF_STATUS_ITEM", "GF_PREVISAO_ITEM"),
            )
            .order_by("-criado_em", "-id")
        )
        for evento in eventos:
            item_id = (evento.dados or {}).get("item_id")
            try:
                item_id = int(item_id)
            except (TypeError, ValueError):
                continue
            if item_id not in itens_ids:
                continue
            historico_por_item.setdefault(item_id, []).append(evento)

    for row in rows:
        row["historico"] = historico_por_item.get(row["item"].pk, [])

    return render(request, "compras/grandes_fornecedores.html", {
        "rows": rows, "pedidos_recebimento": list(pedidos_recebimento.values()),
        "obras": Obra.objects.order_by("nome"),
        "status_choices": [
            (codigo, labels[codigo]) for codigo in STATUS_ACOMPANHAMENTO if codigo in labels
        ],
        "filtros": {"obra": obra, "status": status, "q": busca},
        "pode_operar": _pode_operar_acompanhamento(request.user),
        "pode_status": any(possui_acao_compras(request.user, acao) for acao in (AcaoCompra.GERENCIAR_PEDIDOS, AcaoCompra.ADMINISTRAR)),
        "pode_receber": any(possui_acao_compras(request.user, acao) for acao in (AcaoCompra.RECEBER_PEDIDOS, AcaoCompra.ADMINISTRAR)),
        "total_itens": total_itens, "total_recebidos": total_recebidos,
        "total_pendentes": max(total_itens - total_recebidos, 0),
    })


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
@require_POST
def atualizar_status_item_grande_fornecedor_compras(request, item_id):
    from compras.services.grande_fornecedor_status import transicoes_manuais

    item = get_object_or_404(
        GrandeFornecedorItem.objects.select_related("fluxo__processo", "pedido_item"),
        pk=item_id,
        fluxo__processo__fluxo_grande_fornecedor=True,
    )

    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        item = atualizar_status_operacional_item(
            micro_item=item,
            novo_status=request.POST.get("status"),
            usuario=request.user,
        )
        evento = getattr(item, "_historico_evento", None)
        item.refresh_from_db(fields=["status"])

        if ajax:
            labels = dict(GrandeFornecedorItem.Status.choices)
            transicoes = [
                {"value": codigo, "label": labels.get(codigo, codigo)}
                for codigo in transicoes_manuais(item.status)
                if codigo in labels and codigo != GrandeFornecedorItem.Status.CANCELADO
            ]
            return JsonResponse({
                "ok": True,
                "item_id": item.pk,
                "status": item.status,
                "status_label": item.get_status_display(),
                "transicoes": transicoes,
                "mensagem": f"Status de {item.item} atualizado.",
                "historico": {
                    "descricao": evento.descricao if evento else "Status atualizado.",
                    "criado_em": timezone.localtime(evento.criado_em, ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M") if evento else "",
                    "usuario": evento.usuario.get_username() if evento and evento.usuario else "Sistema",
                },
            })

        messages.success(request, f"Status de {item.item} atualizado.")
    except ValidationError as exc:
        if ajax:
            return _erro_json(exc)
        messages.error(request, str(exc))

    return _voltar_acompanhamento()


@compras_acao_required(AcaoCompra.GERENCIAR_PEDIDOS)
@require_POST
def atualizar_previsao_item_grande_fornecedor_compras(request, item_id):
    item = get_object_or_404(GrandeFornecedorItem.objects.select_related("fluxo__processo", "pedido_item"), pk=item_id, fluxo__processo__fluxo_grande_fornecedor=True)
    previsao = parse_date(request.POST.get("previsao_entrega") or "")
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        item = atualizar_previsao_operacional_item(micro_item=item, previsao=previsao, usuario=request.user)
        evento = getattr(item, "_historico_evento", None)
        if ajax:
            return JsonResponse({
                "ok": True,
                "mensagem": f"Previsão de {item.item} atualizada.",
                "historico": {
                    "descricao": evento.descricao if evento else "Previsão atualizada.",
                    "criado_em": timezone.localtime(evento.criado_em, ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M") if evento else "",
                    "usuario": evento.usuario.get_username() if evento and evento.usuario else "Sistema",
                },
            })
        messages.success(request, f"Previsão de {item.item} atualizada.")
    except ValidationError as exc:
        if ajax:
            return _erro_json(exc)
        messages.error(request, str(exc))
    return _voltar_acompanhamento()


@compras_acao_required(AcaoCompra.RECEBER_PEDIDOS)
@require_POST
def receber_pedido_grande_fornecedor_compras(request, pedido_id):
    from compras.models import PedidoCompra
    from compras.services.pedidos import registrar_recebimento
    pedido = get_object_or_404(PedidoCompra.objects.select_related("processo").prefetch_related("itens"), pk=pedido_id, processo__fluxo_grande_fornecedor=True)
    quantidades, valores_itens = {}, {}
    for pedido_item in pedido.itens.all():
        qtd = request.POST.get(f"item_{pedido_item.pk}")
        valor = request.POST.get(f"valor_item_{pedido_item.pk}")
        if qtd not in (None, ""):
            quantidades[pedido_item.pk] = qtd
        if valor not in (None, ""):
            valores_itens[pedido_item.pk] = valor
    try:
        arquivo = request.FILES.get("arquivo_nota_fiscal")
        if arquivo:
            validar_documento_upload(arquivo)
        registrar_recebimento(
            pedido=pedido, quantidades=quantidades, valores_itens=valores_itens, usuario=request.user,
            numero_nota_fiscal=request.POST.get("numero_nota_fiscal", ""),
            valor_total_nota=request.POST.get("valor_total_nota", ""),
            arquivo_nota_fiscal=arquivo, observacao=request.POST.get("observacao", ""),
            dados_fiscais_opcionais=True,
        )
        messages.success(request, f"Recebimento do pedido {pedido.numero} registrado.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return _voltar_acompanhamento()
