from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from compras.models import (
    ContratacaoCompra,
    CotacaoFornecedor,
    PedidoCompraAnexo,
    RecebimentoPedido,
)
from compras.services.permissoes import compras_acao_required
from usuarios.models import AcaoCompra


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


@compras_acao_required(AcaoCompra.VISUALIZAR)
def baixar_documento_cotacao(request, pk):
    cotacao = get_object_or_404(CotacaoFornecedor, pk=pk)
    return _responder_arquivo(cotacao.documento)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def baixar_documento_contratacao(request, pk):
    contratacao = get_object_or_404(ContratacaoCompra, pk=pk)
    return _responder_arquivo(contratacao.documento)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def baixar_anexo_pedido(request, pk):
    anexo = get_object_or_404(PedidoCompraAnexo, pk=pk)
    return _responder_arquivo(anexo.arquivo)


@compras_acao_required(AcaoCompra.VISUALIZAR)
def baixar_nota_fiscal_recebimento(request, pk):
    recebimento = get_object_or_404(RecebimentoPedido, pk=pk)
    return _responder_arquivo(recebimento.arquivo_nota_fiscal)
