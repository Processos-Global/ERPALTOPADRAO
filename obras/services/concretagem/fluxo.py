"""Regras de negócio do ciclo de vida da concretagem.

Toda mudança de status passa por `mudar_status`, que confere a tabela
`TRANSICOES`, roda as validações da etapa e grava o histórico. Views e a
página pública só chamam as funções deste módulo.
"""
import datetime
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from obras.models import Concretagem, HistoricoConcretagem

S = Concretagem.Status
R = Concretagem.RespostaConcreteira
A = HistoricoConcretagem.Acao

TRANSICOES = {
    S.RASCUNHO: {S.SOLICITADA, S.CANCELADA},
    S.SOLICITADA: {S.CONFIRMADA, S.RASCUNHO, S.CANCELADA},
    S.CONFIRMADA: {S.EXECUTADA, S.RASCUNHO, S.CANCELADA},
    # Depois de executada (concreto aplicado) não se cancela mais.
    S.EXECUTADA: {S.AGUARDANDO_LAUDOS, S.CONFIRMADA},
    S.AGUARDANDO_LAUDOS: {S.CONCLUIDA, S.EXECUTADA},
    S.CONCLUIDA: set(),
    S.CANCELADA: set(),
}


class FluxoError(ValueError):
    """Regra de negócio violada; a mensagem é exibida ao usuário."""


def registrar_historico(conc, usuario, acao, observacao="", status_anterior=None):
    return HistoricoConcretagem.objects.create(
        concretagem=conc,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        acao=acao,
        status_anterior=status_anterior if status_anterior is not None else conc.status,
        status_novo=conc.status,
        observacao=observacao or "",
    )


def _proximo_codigo():
    ano = timezone.localdate().year
    prefixo = f"CONC-{ano}-"
    ultimo = (
        Concretagem.objects.filter(codigo__startswith=prefixo)
        .order_by("-codigo").values_list("codigo", flat=True).first()
    )
    seq = int(ultimo.rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefixo}{seq:04d}"


def criar_concretagem(conc, itens, usuario):
    """Persiste uma nova concretagem em RASCUNHO com seus itens planejados.

    O código é sequencial por ano; em corrida entre dois cadastros, a
    constraint unique dispara e tentamos o próximo número.
    """
    conc.status = S.RASCUNHO
    conc.criado_por = usuario
    conc.atualizado_por = usuario
    for _ in range(5):
        conc.codigo = _proximo_codigo()
        try:
            with transaction.atomic():
                conc.save()
                break
        except IntegrityError:
            conc.pk = None
            continue
    else:
        raise FluxoError("Não foi possível gerar o código da concretagem. Tente novamente.")
    salvar_itens(conc, itens)
    registrar_historico(conc, usuario, A.CRIACAO, "Solicitação criada.")
    return conc


def salvar_itens(conc, itens):
    """Substitui os itens planejados (lista de dicts com local, descricao, volume_previsto)."""
    conc.itens_planejados.all().delete()
    conc.itens_planejados.model.objects.bulk_create([
        conc.itens_planejados.model(
            concretagem=conc, local=item.get("local"), descricao=item.get("descricao", ""),
            volume_previsto=item["volume_previsto"], ordem=i,
        )
        for i, item in enumerate(itens)
    ])


def possui_caminhoes(conc):
    """Reagendar só é permitido antes de lançar caminhões (execução em campo)."""
    caminhoes = getattr(conc, "caminhoes", None)
    return bool(caminhoes is not None and caminhoes.filter(ativo=True).exists())


def campos_faltando_envio(conc):
    """{chave: rótulo} do que falta para liberar; a chave identifica o campo na tela."""
    checagens = (
        ("concreteira", "concreteira", conc.concreteira_id),
        ("engenheiro", "engenheiro responsável", conc.engenheiro_id),
        ("data", "data", conc.data_programada),
        ("horario", "horário", conc.horario_programado),
        ("fck", "Fck de projeto", conc.fck_projeto),
        ("volume", "volume solicitado", conc.volume_solicitado),
        ("itens", "ao menos um item planejado", conc.itens_planejados.exists()),
    )
    return {chave: rotulo for chave, rotulo, valor in checagens if not valor}


def pendencias_envio(conc):
    return list(campos_faltando_envio(conc).values())


def _validar(conc, novo):
    if novo == S.SOLICITADA:
        faltando = pendencias_envio(conc)
        if faltando:
            raise FluxoError("Antes de solicitar, preencha: " + ", ".join(faltando) + ".")
    elif novo == S.EXECUTADA:
        from .campo import pendencias_finalizar

        faltas = pendencias_finalizar(conc)
        if faltas:
            raise FluxoError("Para finalizar: " + " ".join(faltas))
    elif novo == S.AGUARDANDO_LAUDOS:
        if conc.com_bomba and not conc.nome_bombista:
            raise FluxoError("Informe o nome do bombista antes de enviar os CPs ao laboratório.")
    elif novo == S.CONCLUIDA:
        from .laudos import pendencias_conclusao

        faltas = pendencias_conclusao(conc)
        if faltas:
            raise FluxoError("Para concluir, falta: " + ", ".join(faltas) + ".")


def mudar_status(conc, novo, usuario, observacao="", acao=A.MUDANCA_STATUS):
    anterior = conc.status
    if novo not in TRANSICOES.get(anterior, set()):
        raise FluxoError(
            f"Não é possível passar de “{S(anterior).label}” para “{S(novo).label}”."
        )
    _validar(conc, novo)
    conc.status = novo
    campos = ["status", "atualizado_em"]
    if novo == S.SOLICITADA:
        conc.solicitada_em = timezone.now()
        campos.append("solicitada_em")
    if usuario is not None and getattr(usuario, "is_authenticated", False):
        conc.atualizado_por = usuario
        campos.append("atualizado_por")
    conc.save(update_fields=campos)
    registrar_historico(
        conc, usuario, acao,
        observacao or f"{S(anterior).label} → {S(novo).label}.",
        status_anterior=anterior,
    )
    return conc


def solicitar(conc, usuario):
    return mudar_status(conc, S.SOLICITADA, usuario, "Solicitação liberada para envio à concreteira.")


def _limpar_resposta(conc):
    conc.confirmacao_cliente = ""
    conc.confirmacao_observacao = ""
    conc.confirmado_em = None
    conc.aceite_manual_por = None
    conc.reagendamento_data_sugerida = None
    conc.reagendamento_horario_sugerido = None
    conc.reagendamento_solicitante = ""
    # Novo token invalida o link enviado anteriormente.
    conc.token_confirmacao = uuid.uuid4()


# ---------------------------------------------------------------------------
# Respostas da concreteira (link público) e aceite manual do gerente
# ---------------------------------------------------------------------------

def _exigir_aguardando(conc):
    if conc.status != S.SOLICITADA:
        raise FluxoError("Esta solicitação não está aguardando resposta.")
    if conc.confirmacao_cliente:
        raise FluxoError("A concreteira já respondeu esta solicitação.")


@transaction.atomic
def aceitar(conc, usuario=None, observacao=""):
    """Aceite pela concreteira (usuario=None) ou manual pelo gerente."""
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    _exigir_aguardando(conc)
    conc.confirmacao_cliente = R.ACEITO
    conc.confirmado_em = timezone.now()
    conc.confirmacao_observacao = observacao or ""
    manual = usuario is not None
    if manual:
        conc.aceite_manual_por = usuario
    conc.save(update_fields=[
        "confirmacao_cliente", "confirmado_em", "confirmacao_observacao", "aceite_manual_por",
    ])
    texto = (
        "Aceite manual pelo gerente (concreteira não aceitou pelo link)."
        if manual else "Concreteira aceitou pelo link público."
    )
    if observacao:
        texto += f" Observação: {observacao}"
    return mudar_status(conc, S.CONFIRMADA, usuario, texto, acao=A.RESPOSTA_CONCRETEIRA)


@transaction.atomic
def rejeitar(conc, observacao=""):
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    _exigir_aguardando(conc)
    conc.confirmacao_cliente = R.REJEITADO
    conc.confirmado_em = timezone.now()
    conc.confirmacao_observacao = observacao or ""
    conc.cancelado_em = timezone.now()
    conc.motivo_cancelamento = "Recusada pela concreteira." + (f" {observacao}" if observacao else "")
    conc.save(update_fields=[
        "confirmacao_cliente", "confirmado_em", "confirmacao_observacao",
        "cancelado_em", "motivo_cancelamento",
    ])
    return mudar_status(
        conc, S.CANCELADA, None, conc.motivo_cancelamento, acao=A.RESPOSTA_CONCRETEIRA,
    )


@transaction.atomic
def pedir_reagendamento(conc, data, horario, solicitante, observacao=""):
    """A concreteira sugere outra data. O status não muda; alguém da obra reabre e reenvia."""
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    _exigir_aguardando(conc)
    if not data:
        raise FluxoError("Informe a data sugerida.")
    conc.confirmacao_cliente = R.REAGENDAMENTO
    conc.confirmado_em = timezone.now()
    conc.reagendamento_data_sugerida = data
    conc.reagendamento_horario_sugerido = horario
    conc.reagendamento_solicitante = (solicitante or "")[:150]
    conc.confirmacao_observacao = observacao or ""
    conc.save(update_fields=[
        "confirmacao_cliente", "confirmado_em", "reagendamento_data_sugerida",
        "reagendamento_horario_sugerido", "reagendamento_solicitante", "confirmacao_observacao",
    ])
    sugestao = data.strftime("%d/%m/%Y") + (f" às {horario:%H:%M}" if horario else "")
    registrar_historico(
        conc, None, A.RESPOSTA_CONCRETEIRA,
        f"Concreteira pediu reagendamento para {sugestao}"
        + (f" ({solicitante})" if solicitante else "") + (f": {observacao}" if observacao else "."),
    )
    return conc


# ---------------------------------------------------------------------------
# Reagendar / reenviar (engenheiro) e cancelar
# ---------------------------------------------------------------------------

def pode_reagendar(conc):
    return conc.status in (S.SOLICITADA, S.CONFIRMADA) and not possui_caminhoes(conc)


@transaction.atomic
def reagendar(conc, usuario, data=None, horario=None, motivo=""):
    """Volta a solicitação para Rascunho, opcionalmente com nova data, para reenviar.

    Bloqueado depois que há caminhões lançados: a concretagem já começou.
    """
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    if conc.status not in (S.SOLICITADA, S.CONFIRMADA):
        raise FluxoError("Só é possível reagendar uma concretagem solicitada ou confirmada.")
    if possui_caminhoes(conc):
        raise FluxoError("Já existem caminhões lançados; não é possível reagendar.")
    antes = conc.data_programada, conc.horario_programado
    if data:
        conc.data_programada = data
    if horario:
        conc.horario_programado = horario
    _limpar_resposta(conc)
    conc.save()
    depois = conc.data_programada, conc.horario_programado

    def fmt(par):
        d, h = par
        return (d.strftime("%d/%m/%Y") if d else "sem data") + (f" {h:%H:%M}" if h else "")

    texto = (
        f"Reagendada de {fmt(antes)} para {fmt(depois)}." if antes != depois
        else "Reaberta para reenvio, mantendo a mesma data."
    )
    if motivo:
        texto += f" Motivo: {motivo}"
    return mudar_status(conc, S.RASCUNHO, usuario, texto, acao=A.REAGENDAMENTO)


def pode_cancelar(conc):
    """Só até Confirmada; depois do concreto aplicado não faz sentido cancelar."""
    return conc.status in (S.RASCUNHO, S.SOLICITADA, S.CONFIRMADA)


@transaction.atomic
def cancelar(conc, usuario, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise FluxoError("Informe o motivo do cancelamento.")
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    if conc.terminal:
        raise FluxoError("Esta concretagem já está encerrada.")
    if not pode_cancelar(conc):
        raise FluxoError("Depois de executada, a concretagem não pode mais ser cancelada.")
    conc.cancelado_em = timezone.now()
    conc.motivo_cancelamento = motivo
    conc.save(update_fields=["cancelado_em", "motivo_cancelamento"])
    return mudar_status(conc, S.CANCELADA, usuario, f"Cancelada: {motivo}", acao=A.CANCELAMENTO)


# ---------------------------------------------------------------------------
# Execução e controle tecnológico
# ---------------------------------------------------------------------------

@transaction.atomic
def finalizar_execucao(conc, usuario, ocorrencias=""):
    """Confirmada → Executada: exige saldo zero e ficha de moldagem completa."""
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    _validar(conc, S.EXECUTADA)
    conc.executada_em = timezone.now()
    conc.ocorrencias = (ocorrencias or "").strip()
    conc.save(update_fields=["executada_em", "ocorrencias"])
    return mudar_status(conc, S.EXECUTADA, usuario, "Execução em campo finalizada.")


# Entre as etapas 3 e 5 dá para voltar uma etapa (corrigir campo ou envio dos CPs).
ETAPA_ANTERIOR = {S.EXECUTADA: S.CONFIRMADA, S.AGUARDANDO_LAUDOS: S.EXECUTADA}


@transaction.atomic
def voltar_etapa(conc, usuario):
    """Executada → Confirmada (reabre o campo) ou Aguardando laudos → Executada (desfaz o envio dos CPs)."""
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    anterior = ETAPA_ANTERIOR.get(conc.status)
    if anterior is None:
        raise FluxoError("Esta etapa não pode voltar.")
    if conc.status == S.EXECUTADA:
        conc.executada_em = None
        conc.save(update_fields=["executada_em"])
    else:
        conc.cps_enviados_em = None
        conc.cps_enviados_por_nome = ""
        conc.save(update_fields=["cps_enviados_em", "cps_enviados_por_nome"])
    return mudar_status(conc, anterior, usuario, f"Voltou para “{S(anterior).label}”.")


@transaction.atomic
def marcar_cps_enviados(conc, usuario, enviado_por_nome):
    """Executada → Aguardando laudos, registrando quem levou os CPs ao laboratório."""
    nome = (enviado_por_nome or "").strip()
    if not nome:
        raise FluxoError("Informe quem enviou os CPs ao laboratório.")
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    conc.cps_enviados_em = timezone.now()
    conc.cps_enviados_por_nome = nome[:200]
    conc.save(update_fields=["cps_enviados_em", "cps_enviados_por_nome"])
    return mudar_status(conc, S.AGUARDANDO_LAUDOS, usuario, f"CPs enviados ao laboratório por {nome}.")


@transaction.atomic
def concluir(conc, usuario, justificativa=""):
    """Aguardando laudos → Concluída (gerente). Com laudo reprovado, exige justificativa."""
    conc = Concretagem.objects.select_for_update().get(pk=conc.pk)
    reprovados = [l for l in conc.laudos.all() if not l.aprovado]
    justificativa = (justificativa or "").strip()
    if reprovados and not justificativa:
        idades = ", ".join(f"{l.idade_dias} dias" for l in reprovados)
        raise FluxoError(f"Há laudo abaixo do mínimo ({idades}). Informe a justificativa para concluir.")
    _validar(conc, S.CONCLUIDA)
    conc.concluida_em = timezone.now()
    conc.concluida_por = usuario
    conc.save(update_fields=["concluida_em", "concluida_por"])
    texto = "Controle tecnológico concluído."
    if justificativa:
        texto += f" Justificativa (laudo abaixo do mínimo): {justificativa}"
    return mudar_status(conc, S.CONCLUIDA, usuario, texto)


def parse_data(valor):
    try:
        return datetime.date.fromisoformat((valor or "").strip()) if valor else None
    except ValueError:
        raise FluxoError("Data inválida.")


def parse_hora(valor):
    try:
        return datetime.time.fromisoformat((valor or "").strip()) if valor else None
    except ValueError:
        raise FluxoError("Horário inválido.")
