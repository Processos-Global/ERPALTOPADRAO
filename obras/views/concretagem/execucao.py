"""Execução em campo, ficha de moldagem e laudos.

Todas as ações são POST e voltam para o detalhe na aba correspondente
(`#aba-...`). As regras ficam nos services; aqui só há permissão, leitura
do formulário e mensagens.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from obras.forms import (
    CaminhaoForm, FichaMoldagemForm, LaudoForm, SerieMoldagemForm, SobraForm, UtilizacaoForm,
)
from obras.models import (
    CaminhaoConcretagem, Concretagem, FichaMoldagem, LocalUsoObra, SerieMoldagem, SobraConcreto, UtilizacaoConcreto,
)
from obras.services.concretagem import campo, drive, ficha, fluxo, laudos
from obras.services.concretagem.permissoes import gerente_required, pode_editar_concretagem, preencher_required, ver_required

from .anexos import validar_arquivo


def _conc(pk):
    return get_object_or_404(Concretagem.objects.select_related("obra", "concreteira", "engenheiro"), pk=pk)


def _voltar(pk, aba):
    return redirect(reverse("obras:concretagem_detalhe", args=[pk]) + f"#aba-{aba}")


def _erros(request, form):
    for campo_nome, lista in form.errors.items():
        rotulo = form.fields[campo_nome].label if campo_nome in form.fields else ""
        for erro in lista:
            messages.error(request, f"{rotulo}: {erro}" if rotulo else erro)


def _executar(request, funcao, sucesso):
    try:
        resultado = funcao()
    except fluxo.FluxoError as exc:
        messages.error(request, str(exc))
        return None
    if sucesso:
        messages.success(request, sucesso)
    return resultado


# ---------------------------------------------------------------------------
# Caminhões
# ---------------------------------------------------------------------------

@require_POST
@preencher_required
def caminhao_salvar(request, pk, caminhao_pk=None):
    conc = _conc(pk)
    instancia = get_object_or_404(CaminhaoConcretagem, pk=caminhao_pk, concretagem=conc, ativo=True) if caminhao_pk else None
    form = CaminhaoForm(request.POST, instance=instancia)
    nf = request.FILES.get("foto_nf")
    if nf:
        try:
            validar_arquivo(nf)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _voltar(pk, "campo")
    if not form.is_valid():
        _erros(request, form)
        return _voltar(pk, "campo")
    cam = _executar(request, lambda: campo.salvar_caminhao(conc, form.save(commit=False), request.user), "Caminhão salvo.")
    if cam and nf:
        drive.criar_anexo(conc, "NOTA_FISCAL", nf, request.user, caminhao=cam)
        if drive.drive_habilitado():
            messages.info(request, "A foto da NF está sendo enviada ao Drive em segundo plano.")
    return _voltar(pk, "campo")


@require_POST
@preencher_required
def caminhao_remover(request, pk, caminhao_pk):
    conc = _conc(pk)
    cam = get_object_or_404(CaminhaoConcretagem, pk=caminhao_pk, concretagem=conc, ativo=True)
    _executar(request, lambda: campo.remover_caminhao(conc, cam, request.user), f"{cam.rotulo} removido.")
    return _voltar(pk, "campo")


# ---------------------------------------------------------------------------
# Utilização e sobra
# ---------------------------------------------------------------------------

@require_POST
@preencher_required
def uso_salvar(request, pk, uso_pk=None):
    conc = _conc(pk)
    instancia = get_object_or_404(UtilizacaoConcreto, pk=uso_pk, concretagem=conc, ativo=True) if uso_pk else None
    form = UtilizacaoForm(request.POST, instance=instancia, conc=conc)
    if form.is_valid():
        _executar(request, lambda: campo.salvar_utilizacao(conc, form.save(commit=False), request.user), "Uso registrado.")
    else:
        _erros(request, form)
    return _voltar(pk, "campo")


@require_POST
@preencher_required
def uso_remover(request, pk, uso_pk):
    conc = _conc(pk)
    uso = get_object_or_404(UtilizacaoConcreto, pk=uso_pk, concretagem=conc, ativo=True)
    _executar(request, lambda: campo.remover_lancamento(conc, uso, request.user, f"Uso de {uso.volume_utilizado} m³"), "Uso removido.")
    return _voltar(pk, "campo")


@require_POST
@preencher_required
def sobra_salvar(request, pk, sobra_pk=None):
    conc = _conc(pk)
    instancia = get_object_or_404(SobraConcreto, pk=sobra_pk, concretagem=conc, ativo=True) if sobra_pk else None
    form = SobraForm(request.POST, instance=instancia, conc=conc)
    if form.is_valid():
        _executar(request, lambda: campo.salvar_sobra(conc, form.save(commit=False), request.user), "Sobra registrada.")
    else:
        _erros(request, form)
    return _voltar(pk, "campo")


@require_POST
@preencher_required
def sobra_remover(request, pk, sobra_pk):
    conc = _conc(pk)
    sobra = get_object_or_404(SobraConcreto, pk=sobra_pk, concretagem=conc, ativo=True)
    _executar(request, lambda: campo.remover_lancamento(conc, sobra, request.user, f"Sobra de {sobra.volume_sobra} m³"), "Sobra removida.")
    return _voltar(pk, "campo")


# ---------------------------------------------------------------------------
# Ficha de moldagem
# ---------------------------------------------------------------------------

def _exigir_moldagem_editavel(request, conc):
    """Ficha editável na execução e depois dela, até a conclusão."""
    if conc.status == Concretagem.Status.CONFIRMADA:
        return
    if conc.status in (Concretagem.Status.EXECUTADA, Concretagem.Status.AGUARDANDO_LAUDOS) and pode_editar_concretagem(request.user, conc):
        return
    raise PermissionDenied("A ficha de moldagem não pode ser alterada nesta etapa.")


@require_POST
@preencher_required
def ficha_cabecalho_salvar(request, pk):
    conc = _conc(pk)
    _exigir_moldagem_editavel(request, conc)
    instancia, _ = FichaMoldagem.objects.get_or_create(concretagem=conc)
    form = FichaMoldagemForm(request.POST, instance=instancia)
    if form.is_valid():
        form.save()
        fluxo.registrar_historico(conc, request.user, fluxo.A.EDICAO, "Cabeçalho da ficha de moldagem atualizado.")
        messages.success(request, "Cabeçalho da ficha salvo.")
    else:
        _erros(request, form)
    return _voltar(pk, "moldagem")


@require_POST
@preencher_required
def serie_salvar(request, pk, caminhao_pk):
    conc = _conc(pk)
    _exigir_moldagem_editavel(request, conc)
    cam = get_object_or_404(CaminhaoConcretagem, pk=caminhao_pk, concretagem=conc, ativo=True)
    serie, _ = SerieMoldagem.objects.get_or_create(caminhao=cam)
    form = SerieMoldagemForm(request.POST, instance=serie)
    fotos = request.FILES.getlist("etiquetas")
    try:
        for foto in fotos:
            validar_arquivo(foto, so_imagem=True)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(pk, "moldagem")
    if not form.is_valid():
        _erros(request, form)
        return _voltar(pk, "moldagem")
    serie = form.save(commit=False)
    serie.atualizado_por = request.user
    serie.save()
    for foto in fotos:
        drive.criar_anexo(conc, "ETIQUETA_CP", foto, request.user, caminhao=cam)
    fluxo.registrar_historico(conc, request.user, fluxo.A.EDICAO, f"Série de moldagem do {cam.rotulo} atualizada.")
    messages.success(request, f"Série do {cam.rotulo} salva.")
    return _voltar(pk, "moldagem")


@ver_required
def ficha_pdf(request, pk):
    conc = _conc(pk)
    try:
        conteudo = ficha.gerar_pdf(conc)
    except Exception:
        messages.error(request, "Não foi possível gerar a ficha de moldagem. Tente novamente.")
        return _voltar(pk, "moldagem")
    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{ficha.nome_arquivo(conc)}"'
    return resposta


@require_POST
@preencher_required
def ficha_enviar_drive(request, pk):
    conc = _conc(pk)
    ficha.agendar_geracao(conc, request.user)
    messages.success(request, "A ficha de moldagem está sendo gerada e enviada ao Drive em segundo plano. Pode continuar usando o sistema.")
    return _voltar(pk, "moldagem")


# ---------------------------------------------------------------------------
# Transições da execução
# ---------------------------------------------------------------------------

@require_POST
@preencher_required
def finalizar(request, pk):
    conc = _conc(pk)
    resultado = _executar(
        request, lambda: fluxo.finalizar_execucao(conc, request.user, conc.ocorrencias),
        "Etapa avançada: execução finalizada.",
    )
    if resultado:
        ficha.agendar_geracao(resultado, request.user)
        messages.info(request, "A ficha de moldagem está sendo gerada e enviada ao Drive em segundo plano.")
    return _voltar(pk, "moldagem" if resultado else "campo")


@require_POST
@preencher_required
def voltar_etapa(request, pk):
    conc = _conc(pk)
    resultado = _executar(request, lambda: fluxo.voltar_etapa(conc, request.user), None)
    if resultado:
        messages.success(request, f"Concretagem voltou para “{resultado.get_status_display()}”.")
    return _voltar(pk, "campo" if resultado and resultado.status == "CONFIRMADA" else "laudos")


@require_POST
@preencher_required
def cps_enviados(request, pk):
    conc = _conc(pk)
    _executar(
        request, lambda: fluxo.marcar_cps_enviados(conc, request.user, request.POST.get("enviado_por_nome")),
        "CPs registrados como enviados ao laboratório. Agora é só lançar os laudos.",
    )
    return _voltar(pk, "laudos")


@require_POST
@preencher_required
def laudo_salvar(request, pk):
    conc = _conc(pk)
    form = LaudoForm(request.POST, request.FILES)
    if not form.is_valid():
        _erros(request, form)
        return _voltar(pk, "laudos")
    arquivo = form.cleaned_data.get("arquivo")
    if arquivo:
        try:
            validar_arquivo(arquivo)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _voltar(pk, "laudos")
    d = form.cleaned_data
    laudo = _executar(
        request,
        lambda: laudos.lancar(conc, d["idade_dias"], d["resistencia_mpa"], request.user,
                              d["enviado_por_nome"], d["observacao"], arquivo),
        None,
    )
    if laudo:
        if laudo.aprovado:
            messages.success(request, f"Laudo de {laudo.idade_dias} dias lançado: aprovado ({laudo.percentual_fck}% do fck).")
        else:
            messages.warning(
                request,
                f"Laudo de {laudo.idade_dias} dias ABAIXO do mínimo: {laudo.resistencia_mpa} MPa "
                f"(mínimo {laudo.limite_minimo_mpa} MPa). O engenheiro e a equipe de concretagem foram avisados.",
            )
    return _voltar(pk, "laudos")


@require_POST
@gerente_required
def concluir(request, pk):
    conc = _conc(pk)
    _executar(request, lambda: fluxo.concluir(conc, request.user, request.POST.get("justificativa")), "Concretagem concluída.")
    return _voltar(pk, "laudos")


# ---------------------------------------------------------------------------
# Contexto das abas de execução (usado pelo detalhe)
# ---------------------------------------------------------------------------
ETAPAS_COM_EXECUCAO = (
    Concretagem.Status.CONFIRMADA, Concretagem.Status.EXECUTADA,
    Concretagem.Status.AGUARDANDO_LAUDOS, Concretagem.Status.CONCLUIDA,
)


def contexto_execucao(request, conc, pode_preencher, eh_gerente):
    from obras.models import LaudoConcretagem
    from obras.models.concretagem import LIMITES_FCK

    S = Concretagem.Status
    if conc.status not in ETAPAS_COM_EXECUCAO and not conc.caminhoes.exists():
        return {"mostrar_execucao": False}
    caminhoes = list(conc.caminhoes.filter(ativo=True).select_related("serie_moldagem").order_by("ordem"))
    anexos = list(conc.anexos.filter(ativo=True).select_related("caminhao", "laudo", "enviado_por"))
    for cam in caminhoes:
        cam.notas = [a for a in anexos if a.caminhao_id == cam.pk and a.etapa == "NOTA_FISCAL"]
        cam.etiquetas = [a for a in anexos if a.caminhao_id == cam.pk and a.etapa == "ETIQUETA_CP"]
        cam.saldo = campo.resumo_volume(conc, cam)["saldo"]
        serie = getattr(cam, "serie_moldagem", None)
        cam.pendencias_ficha = serie.pendencias() if serie else ["série de moldagem"]
    laudos_idade = laudos.laudos_por_idade(conc)
    for laudo in laudos_idade.values():
        laudo.arquivos = [a for a in anexos if a.laudo_id == laudo.pk]
    ficha_obj = FichaMoldagem.objects.filter(concretagem=conc).first() or FichaMoldagem(concretagem=conc)
    editavel = conc.status == S.CONFIRMADA and pode_preencher
    moldagem_editavel = pode_preencher and (
        conc.status == S.CONFIRMADA
        or (conc.status in (S.EXECUTADA, S.AGUARDANDO_LAUDOS) and pode_editar_concretagem(request.user, conc))
    )
    resumo = campo.resumo_volume(conc)

    # --- Avisos por aba: círculo no nome da aba; borda vermelha só no item específico.
    em_campo = conc.status == S.CONFIRMADA
    for cam in caminhoes:
        cam.falta_saldo = em_campo and cam.saldo > campo.TOLERANCIA
        cam.falta_nf = conc.status in ETAPAS_NF and not cam.notas
        cam.falta_ficha = conc.status in (S.CONFIRMADA, S.EXECUTADA, S.AGUARDANDO_LAUDOS) and bool(cam.pendencias_ficha)
    falta_destino = em_campo and resumo["saldo"] > campo.TOLERANCIA
    aguardando = conc.status == S.AGUARDANDO_LAUDOS
    tem_intermediario = bool(set(laudos_idade).intersection(laudos.IDADES_INTERMEDIARIAS))
    linhas_laudo = []
    for idade, label in LaudoConcretagem.Idade.choices:
        laudo = laudos_idade.get(idade)
        falta = aguardando and laudo is None and (idade == 28 or not tem_intermediario)
        reprovado = laudo is not None and not laudo.aprovado and conc.status != S.CONCLUIDA
        linhas_laudo.append({
            "idade": idade, "label": label, "limite": int(LIMITES_FCK[idade] * 1000) / 10,
            "laudo": laudo, "falta": falta or reprovado,
        })
    anexos_pendentes = sum(1 for a in anexos if not a.no_drive and not a.so_na_ficha)
    falta_envio_cps = conc.status == S.EXECUTADA
    return {
        "aviso_campo": (em_campo and (not caminhoes or falta_destino)) or any(c.falta_nf for c in caminhoes),
        "pode_anexar_nf": pode_preencher and conc.status in ETAPAS_NF,
        "falta_destino": falta_destino,
        "aviso_moldagem": any(c.falta_ficha for c in caminhoes),
        "aviso_laudos": falta_envio_cps or any(l["falta"] for l in linhas_laudo),
        "falta_envio_cps": falta_envio_cps,
        "aviso_anexos": anexos_pendentes > 0 or any(c.falta_nf for c in caminhoes),
        "mostrar_execucao": True,
        "resumo": resumo,
        "caminhoes": caminhoes,
        "usos": conc.utilizacoes.filter(ativo=True).select_related("local", "caminhao"),
        "sobras": conc.sobras.filter(ativo=True).select_related("caminhao", "obra_destino", "local_destino"),
        "form_caminhao": CaminhaoForm(),
        "form_uso": UtilizacaoForm(conc=conc),
        "form_sobra": SobraForm(conc=conc),
        "form_ficha": FichaMoldagemForm(instance=ficha_obj),
        "form_serie": SerieMoldagemForm(),
        "execucao_aberta": editavel,
        "moldagem_editavel": moldagem_editavel,
        "pendencias_finalizar": campo.pendencias_finalizar(conc) if conc.status == S.CONFIRMADA else [],
        "fichas_pdf": [a for a in anexos if a.etapa == "FICHA_MOLDAGEM"],
        "laudos_idade": linhas_laudo,
        "pode_lancar_laudo": pode_preencher and laudos.pode_lancar(conc),
        "pendencias_conclusao": laudos.pendencias_conclusao(conc) if conc.status == S.AGUARDANDO_LAUDOS else [],
        "laudo_reprovado": any(not l.aprovado for l in laudos_idade.values()),
        "laudos_arquivos": [a for a in anexos if a.etapa == "LAUDO"],
        "total_etiquetas": sum(len(c.etiquetas) for c in caminhoes),
        "anexos_pendentes": anexos_pendentes,
        "anexos_pendentes_lista": sorted((a for a in anexos if not a.no_drive and not a.so_na_ficha), key=lambda a: a.criado_em),
        "tipos_local": LocalUsoObra.Tipo.choices,
    }


# ---------------------------------------------------------------------------
# Etiquetas dos CPs por AJAX (envio uma a uma, com prévia ao vivo)
# ---------------------------------------------------------------------------

def etiqueta_json(conc, anexo):
    return {
        "id": anexo.pk,
        "nome": anexo.nome_original,
        "no_drive": anexo.no_drive or anexo.so_na_ficha,
        "situacao": anexo.situacao_drive,
        "miniatura": reverse("obras:concretagem_anexo_miniatura", args=[conc.pk, anexo.pk]),
        "abrir": reverse("obras:concretagem_anexo_abrir", args=[conc.pk, anexo.pk]),
        "remover": reverse("obras:concretagem_anexo_remover", args=[conc.pk, anexo.pk]),
    }


@require_POST
@preencher_required
def etiqueta_enviar(request, pk, caminhao_pk):
    from django.http import JsonResponse

    conc = _conc(pk)
    try:
        _exigir_moldagem_editavel(request, conc)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=403)
    cam = get_object_or_404(CaminhaoConcretagem, pk=caminhao_pk, concretagem=conc, ativo=True)
    foto = request.FILES.get("foto")
    if not foto:
        return JsonResponse({"ok": False, "erro": "Nenhuma foto recebida."}, status=400)
    try:
        validar_arquivo(foto, so_imagem=True)
    except ValueError as exc:
        return JsonResponse({"ok": False, "erro": str(exc)}, status=400)
    anexo = drive.criar_anexo(conc, "ETIQUETA_CP", foto, request.user, caminhao=cam)
    fluxo.registrar_historico(conc, request.user, fluxo.A.ANEXO, f"Foto de etiqueta adicionada ao {cam.rotulo}.")
    return JsonResponse({"ok": True, "etiqueta": etiqueta_json(conc, anexo)})


ETAPAS_NF = (
    Concretagem.Status.CONFIRMADA, Concretagem.Status.EXECUTADA, Concretagem.Status.AGUARDANDO_LAUDOS,
)


@require_POST
@preencher_required
def caminhao_nf(request, pk, caminhao_pk):
    """Anexa a foto/PDF da NF a um caminhão já registrado (também depois de finalizar)."""
    conc = _conc(pk)
    cam = get_object_or_404(CaminhaoConcretagem, pk=caminhao_pk, concretagem=conc, ativo=True)
    if conc.status not in ETAPAS_NF and not (conc.status == Concretagem.Status.CONCLUIDA and pode_editar_concretagem(request.user, conc)):
        messages.error(request, "Não é possível anexar notas fiscais nesta etapa.")
        return _voltar(pk, request.POST.get("aba") or "campo")
    arquivo = request.FILES.get("foto_nf")
    if not arquivo:
        messages.error(request, "Selecione a foto ou o PDF da nota fiscal.")
        return _voltar(pk, request.POST.get("aba") or "campo")
    try:
        validar_arquivo(arquivo)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _voltar(pk, request.POST.get("aba") or "campo")
    numero = (request.POST.get("numero_nota_fiscal") or "").strip()[:30]
    if numero and numero != cam.numero_nota_fiscal:
        cam.numero_nota_fiscal = numero
        cam.save(update_fields=["numero_nota_fiscal", "atualizado_em"])
    drive.criar_anexo(conc, "NOTA_FISCAL", arquivo, request.user, caminhao=cam)
    fluxo.registrar_historico(conc, request.user, fluxo.A.ANEXO, f"Nota fiscal anexada ao {cam.rotulo}.")
    messages.success(request, f"Nota fiscal do {cam.rotulo} anexada." + (" Enviando ao Drive em segundo plano." if drive.drive_habilitado() else ""))
    return _voltar(pk, request.POST.get("aba") or "campo")
