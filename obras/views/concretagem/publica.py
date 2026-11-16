"""Página pública (sem login) para a concreteira responder a solicitação.

A chave de acesso é o UUID `token_confirmacao`, nunca o pk. O GET só exibe
os dados; a resposta exige POST, para que pré-visualizações de e-mail ou
antivírus que abrem links não aceitem nada sozinhos. A resposta é única: se
já houver resposta, a página só informa o estado atual.
"""
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from cadastros.models import DadosEmpresa
from obras.models import Concretagem
from obras.services.concretagem import fluxo, notificacoes


@require_http_methods(["GET", "POST"])
def publica(request, token):
    conc = get_object_or_404(
        Concretagem.objects.select_related("obra", "concreteira"), token_confirmacao=token,
    )
    erro = ""
    resultado = ""
    if request.method == "POST":
        acao = request.POST.get("acao")
        observacao = (request.POST.get("observacao") or "").strip()[:1000]
        try:
            if acao == "aceitar":
                conc = fluxo.aceitar(conc, None, observacao)
                resultado = "aceito"
            elif acao == "recusar":
                conc = fluxo.rejeitar(conc, observacao)
                resultado = "recusado"
            elif acao == "reagendar":
                conc = fluxo.pedir_reagendamento(
                    conc,
                    fluxo.parse_data(request.POST.get("data")),
                    fluxo.parse_hora(request.POST.get("horario")),
                    (request.POST.get("solicitante") or "").strip(),
                    observacao,
                )
                resultado = "reagendamento"
            else:
                erro = "Escolha uma opção."
        except fluxo.FluxoError as exc:
            erro = str(exc)
            conc.refresh_from_db()
        if resultado:
            notificacoes.resposta_concreteira(conc, request)
    return render(request, "obras/concretagem/publica.html", {
        "conc": conc,
        "itens": conc.itens_planejados.select_related("local"),
        "aguardando": conc.aguardando_resposta,
        "resultado": resultado,
        "erro": erro,
        "empresa": DadosEmpresa.atual(),
    })
