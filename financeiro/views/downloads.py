from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from financeiro.models import Pagamento, TituloPagar
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
def baixar_comprovante_pagamento(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    return _responder_arquivo(pagamento.comprovante)
