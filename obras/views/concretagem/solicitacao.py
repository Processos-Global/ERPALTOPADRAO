from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from obras.forms import ConcretagemForm, extrair_itens
from obras.models import (
    Concretagem, ContatoEmailConcreteira, EnderecoEntregaSalvo, EnvioMensagemConcretagem, LocalUsoObra, Obra,
)
from obras.services.concretagem import drive, fluxo, mensagem, notificacoes
from obras.views.concretagem.execucao import contexto_execucao
from obras.services.concretagem.permissoes import (
    contexto_permissoes, gerente_required, pode_editar_concretagem, preencher_required, ver_required,
)

S = Concretagem.Status
A = fluxo.A


def _get(pk):
    return get_object_or_404(
        Concretagem.objects.select_related("obra", "concreteira", "engenheiro", "criado_por", "aceite_manual_por"),
        pk=pk,
    )


def _salvar_endereco(form, obra, usuario):
    if not form.cleaned_data.get("salvar_endereco"):
        return
    endereco = form.cleaned_data["endereco_entrega"]
    nome = form.cleaned_data.get("nome_endereco") or endereco[:160]
    EnderecoEntregaSalvo.objects.get_or_create(
        obra=obra, endereco=endereco,
        defaults={"nome": nome, "link_maps": form.cleaned_data.get("link_maps_entrega", ""), "criado_por": usuario},
    )


def _contexto_form(request, form, conc=None, itens=None):
    obra_id = form["obra"].value() or (conc.obra_id if conc else None)
    obra_sel = Obra.objects.filter(pk=obra_id).first() if obra_id else None
    if itens is None and conc is not None:
        itens = [
            {"local": i.local, "descricao": i.descricao, "volume_previsto": i.volume_previsto}
            for i in conc.itens_planejados.select_related("local")
        ]
    return {
        "form": form,
        "conc": conc,
        "obra_sel": obra_sel,
        "itens": itens or [],
        "locais": LocalUsoObra.objects.filter(obra=obra_sel, ativo=True) if obra_sel else [],
        "enderecos": EnderecoEntregaSalvo.objects.filter(ativo=True).order_by("nome"),
        "tipos_local": LocalUsoObra.Tipo.choices,
        **contexto_permissoes(request.user),
    }


@preencher_required
def nova(request):
    inicial = {}
    obra_get = request.GET.get("obra")
    if obra_get and obra_get.isdigit():
        inicial["obra"] = int(obra_get)
    if request.GET.get("data"):
        inicial["data_programada"] = request.GET["data"]
    if request.method != "POST":
        inicial.setdefault("engenheiro", request.user.pk)
    form = ConcretagemForm(request.POST or None, initial=inicial)
    itens = None
    if request.method == "POST":
        obra = None
        if form.is_valid():
            obra = form.cleaned_data["obra"]
        itens, erros = extrair_itens(request.POST, obra)
        for erro in erros:
            messages.error(request, erro)
        if form.is_valid() and not erros:
            with transaction.atomic():
                conc = fluxo.criar_concretagem(form.save(commit=False), itens, request.user)
                _salvar_endereco(form, obra, request.user)
            messages.success(request, f"Concretagem {conc.codigo} criada em rascunho.")
            return redirect("obras:concretagem_detalhe", pk=conc.pk)
    return render(request, "obras/concretagem/form.html", _contexto_form(request, form, itens=itens))


@preencher_required
def editar(request, pk):
    conc = _get(pk)
    if conc.status != S.RASCUNHO:
        messages.warning(request, "Só é possível editar a solicitação em rascunho. Use “Reagendar” para alterar a data.")
        return redirect("obras:concretagem_detalhe", pk=conc.pk)
    form = ConcretagemForm(request.POST or None, instance=conc)
    itens = None
    if request.method == "POST":
        itens, erros = extrair_itens(request.POST, conc.obra)
        for erro in erros:
            messages.error(request, erro)
        if form.is_valid() and not erros:
            with transaction.atomic():
                conc = form.save(commit=False)
                conc.atualizado_por = request.user
                conc.save()
                fluxo.salvar_itens(conc, itens)
                _salvar_endereco(form, conc.obra, request.user)
                aviso = " (alteração após encerramento)" if conc.terminal else ""
                fluxo.registrar_historico(conc, request.user, A.EDICAO, f"Solicitação editada{aviso}.")
            messages.success(request, "Solicitação atualizada.")
            return redirect("obras:concretagem_detalhe", pk=conc.pk)
    return render(request, "obras/concretagem/form.html", _contexto_form(request, form, conc=conc, itens=itens))


@ver_required
def detalhe(request, pk):
    conc = _get(pk)
    itens = list(conc.itens_planejados.select_related("local"))
    etapas = []
    passou_atual = False
    for valor in Concretagem.ETAPAS:
        atual = conc.status == valor
        etapas.append({
            "valor": valor, "label": S(valor).label, "atual": atual,
            "feita": not passou_atual and not atual and conc.status != S.CANCELADA,
        })
        if atual:
            passou_atual = True
    if conc.status == S.CONCLUIDA:
        for e in etapas:
            e["feita"] = True
    # A mensagem (com o link público) só existe na página depois de liberada:
    # em rascunho nada é renderizado, então não há o que copiar.
    liberada = conc.status == S.SOLICITADA
    texto = mensagem.gerar_texto(conc, request) if liberada else ""
    perms = contexto_permissoes(request.user)
    return render(request, "obras/concretagem/detalhe.html", {
        "conc": conc,
        "itens": itens,
        "volume_itens": sum((i.volume_previsto for i in itens), 0),
        "etapas": etapas,
        "pendencias_envio": fluxo.pendencias_envio(conc) if conc.status == S.RASCUNHO else [],
        "texto_mensagem": texto,
        "link_whatsapp": mensagem.link_whatsapp(texto) if texto else "",
        "link_publico": mensagem.link_publico(conc, request) if liberada else "",
        "destinatarios": mensagem.destinatarios_sugeridos(conc) if conc.concreteira_id else [],
        "pode_bombista": conc.com_bomba and not conc.terminal and conc.status != S.RASCUNHO,
        "envios": conc.envios_mensagem.select_related("enviado_por")[:20],
        **_avisos_solicitacao(conc),
        "historico": conc.historicos.select_related("usuario")[:100],
        "pode_reagendar": fluxo.pode_reagendar(conc),
        "pode_editar": pode_editar_concretagem(request.user, conc),
        "pode_cancelar": fluxo.pode_cancelar(conc),
        "drive_habilitado": drive.drive_habilitado(),
        **perms,
        **contexto_execucao(request, conc, perms["pode_preencher"], perms["eh_gerente"]),
    })


def _avisos_solicitacao(conc):
    """Pendências das abas Solicitação e Envio (círculo de aviso + borda nos campos)."""
    faltando = fluxo.campos_faltando_envio(conc) if conc.status == S.RASCUNHO else {}
    bombista_falta = (
        conc.com_bomba and not conc.nome_bombista
        and conc.status in (S.SOLICITADA, S.CONFIRMADA, S.EXECUTADA)
    )
    return {
        "falta": faltando,
        "bombista_falta": bombista_falta,
        "aviso_solicitacao": bool(faltando) or bombista_falta,
        "aviso_envio": conc.status == S.SOLICITADA and not conc.confirmacao_cliente and not conc.envios_mensagem.exists(),
    }


def _acao(request, pk, funcao, sucesso):
    conc = _get(pk)
    try:
        funcao(conc)
    except fluxo.FluxoError as exc:
        messages.error(request, str(exc))
    else:
        if sucesso:
            messages.success(request, sucesso)
    return redirect("obras:concretagem_detalhe", pk=pk)


def _destinatarios_post(request, conc):
    """E-mails marcados + extras digitados. Levanta ValueError se algum for inválido."""
    extras = (request.POST.get("emails_extras") or "").replace(";", ",").split(",")
    destinatarios = mensagem.validar_emails(request.POST.getlist("emails") + extras)
    if request.POST.get("salvar_extras") and conc.concreteira_id:
        for email in mensagem.validar_emails(extras):
            ContatoEmailConcreteira.objects.get_or_create(fornecedor_id=conc.concreteira_id, email=email)
    return destinatarios


def _disparar_email(request, conc, destinatarios):
    if mensagem.enviar_email(conc, destinatarios, request):
        lista = ", ".join(destinatarios)
        EnvioMensagemConcretagem.objects.create(
            concretagem=conc, canal=EnvioMensagemConcretagem.Canal.EMAIL,
            destinatario=lista[:500], enviado_por=request.user,
        )
        fluxo.registrar_historico(conc, request.user, A.ENVIO_MENSAGEM, f"E-mail enviado para {lista}.")
        messages.success(request, f"E-mail enviado para {lista}.")
        return True
    messages.error(
        request,
        "Não foi possível enviar o e-mail (falha no servidor de e-mail). "
        "A solicitação continua liberada: tente de novo em “Enviar por e-mail” ou use o WhatsApp.",
    )
    return False


@require_POST
@preencher_required
def solicitar(request, pk):
    """Libera a solicitação e, se houver e-mails marcados, já envia o e-mail à concreteira."""
    conc = _get(pk)
    try:
        destinatarios = _destinatarios_post(request, conc)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("obras:concretagem_detalhe", pk=pk)
    try:
        conc = fluxo.solicitar(conc, request.user)
    except fluxo.FluxoError as exc:
        messages.error(request, str(exc))
        return redirect("obras:concretagem_detalhe", pk=pk)
    messages.success(request, "Solicitação liberada para a concreteira.")
    drive.agendar_pasta(conc)
    notificacoes.solicitacao_enviada(conc)
    if destinatarios:
        _disparar_email(request, conc, destinatarios)
    return redirect("obras:concretagem_detalhe", pk=pk)


@require_POST
@preencher_required
def salvar_bombista(request, pk):
    conc = _get(pk)
    nome = (request.POST.get("nome_bombista") or "").strip()[:200]
    if not conc.com_bomba or conc.terminal or conc.status == S.RASCUNHO:
        messages.error(request, "Não é possível informar o bombista nesta etapa.")
    else:
        conc.nome_bombista = nome
        conc.atualizado_por = request.user
        conc.save(update_fields=["nome_bombista", "atualizado_por", "atualizado_em"])
        fluxo.registrar_historico(conc, request.user, A.EDICAO, f"Bombista informado: {nome or '(removido)'}.")
        messages.success(request, "Bombista salvo.")
    return redirect("obras:concretagem_detalhe", pk=pk)


@require_POST
@preencher_required
def registrar_envio(request, pk):
    conc = _get(pk)
    canal = request.POST.get("canal")
    if canal not in (EnvioMensagemConcretagem.Canal.WHATSAPP, EnvioMensagemConcretagem.Canal.COPIADO):
        messages.error(request, "Canal inválido.")
    elif conc.status != S.SOLICITADA:
        messages.error(request, "Libere a solicitação antes de registrar o envio.")
    else:
        EnvioMensagemConcretagem.objects.create(concretagem=conc, canal=canal, enviado_por=request.user)
        fluxo.registrar_historico(
            conc, request.user, A.ENVIO_MENSAGEM,
            f"Mensagem enviada por {EnvioMensagemConcretagem.Canal(canal).label}.",
        )
        messages.success(request, "Envio registrado.")
    return redirect("obras:concretagem_detalhe", pk=pk)


@require_POST
@preencher_required
def enviar_email(request, pk):
    conc = _get(pk)
    if conc.status != S.SOLICITADA:
        messages.error(request, "Libere a solicitação antes de enviar o e-mail.")
        return redirect("obras:concretagem_detalhe", pk=pk)
    try:
        destinatarios = _destinatarios_post(request, conc)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("obras:concretagem_detalhe", pk=pk)
    if not destinatarios:
        messages.error(request, "Selecione ou informe ao menos um e-mail.")
        return redirect("obras:concretagem_detalhe", pk=pk)
    _disparar_email(request, conc, destinatarios)
    return redirect("obras:concretagem_detalhe", pk=pk)


@require_POST
@gerente_required
def aceitar_manual(request, pk):
    observacao = (request.POST.get("observacao") or "").strip()

    def executar(conc):
        conc = fluxo.aceitar(conc, request.user, observacao)
        notificacoes.resposta_concreteira(conc, request)
    return _acao(request, pk, executar, "Solicitação aceita manualmente. Concretagem confirmada.")


@require_POST
@preencher_required
def reagendar(request, pk):
    def executar(conc):
        data = fluxo.parse_data(request.POST.get("data"))
        horario = fluxo.parse_hora(request.POST.get("horario"))
        fluxo.reagendar(conc, request.user, data, horario, (request.POST.get("motivo") or "").strip())
    return _acao(request, pk, executar, "Concretagem voltou para envio. Revise e libere a solicitação novamente.")


@require_POST
@preencher_required
def cancelar(request, pk):
    conc = _get(pk)
    if not pode_editar_concretagem(request.user, conc):
        raise PermissionDenied
    motivo = request.POST.get("motivo")
    return _acao(request, pk, lambda c: fluxo.cancelar(c, request.user, motivo), "Concretagem cancelada.")


@require_POST
@preencher_required
def criar_pasta_drive(request, pk):
    conc = _get(pk)
    if drive.garantir_pasta(conc):
        messages.success(request, "Pasta da concretagem disponível no Drive.")
    else:
        messages.error(request, "Não foi possível criar a pasta no Drive. Verifique se a pasta raiz está compartilhada com a conta de serviço.")
    return redirect("obras:concretagem_detalhe", pk=pk)
