from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from compras.models import PedidoCompraAnexo, RecebimentoPedido
from financeiro.models import AnexoTituloPagar, Pagamento, TituloPagar
from financeiro.services.permissoes import financeiro_acao_required


def _responder_arquivo(campo):
    if not campo or not campo.name:
        raise Http404("Arquivo não encontrado.")
    try:
        arquivo = campo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Arquivo não encontrado.")

    resposta = FileResponse(
        arquivo,
        as_attachment=False,
        filename=Path(campo.name).name,
    )
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Cache-Control"] = "private, no-store"
    return resposta


@financeiro_acao_required("VISUALIZAR")
def baixar_documento_titulo(request, pk):
    titulo = get_object_or_404(TituloPagar, pk=pk)
    return _responder_arquivo(titulo.arquivo_documento)


@financeiro_acao_required("VISUALIZAR")
def baixar_anexo_titulo(request, titulo_pk, anexo_pk):
    anexo = get_object_or_404(AnexoTituloPagar, pk=anexo_pk, titulo_id=titulo_pk)
    return _responder_arquivo(anexo.arquivo)


@financeiro_acao_required("VISUALIZAR")
def baixar_comprovante_pagamento(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    return _responder_arquivo(pagamento.comprovante)


@financeiro_acao_required("VISUALIZAR")
def baixar_anexo_pedido_titulo(request, titulo_pk, anexo_pk):
    titulo = get_object_or_404(TituloPagar.objects.select_related("pedido"), pk=titulo_pk)
    if not titulo.pedido_id:
        raise Http404("Conta sem pedido de compra vinculado.")
    anexo = get_object_or_404(PedidoCompraAnexo, pk=anexo_pk, pedido_id=titulo.pedido_id)
    return _responder_arquivo(anexo.arquivo)


@financeiro_acao_required("VISUALIZAR")
def baixar_nota_fiscal_pedido_titulo(request, titulo_pk, recebimento_pk):
    titulo = get_object_or_404(TituloPagar.objects.select_related("pedido"), pk=titulo_pk)
    if not titulo.pedido_id:
        raise Http404("Conta sem pedido de compra vinculado.")
    recebimento = get_object_or_404(RecebimentoPedido, pk=recebimento_pk, pedido_id=titulo.pedido_id)
    return _responder_arquivo(recebimento.arquivo_nota_fiscal)
