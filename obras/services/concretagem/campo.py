"""Regras da execução em campo: caminhões, utilização, sobra e saldo de volume.

saldo sem destinação = volume entregue - volume utilizado - volume de sobra
Uso/sobra nunca podem ultrapassar o saldo (tolerância de 0,02 m³ para
arredondamento). Quando o lançamento indica o caminhão, o limite é o saldo
daquele caminhão.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Sum

from obras.models import CaminhaoConcretagem, Concretagem, SerieMoldagem, SobraConcreto, UtilizacaoConcreto

from .fluxo import A, FluxoError, registrar_historico

TOLERANCIA = Decimal("0.02")
ZERO = Decimal("0")
S = Concretagem.Status


def _soma(qs, campo):
    return qs.aggregate(t=Sum(campo))["t"] or ZERO


def resumo_volume(conc, caminhao=None, ignorar_uso=None, ignorar_sobra=None):
    usos = UtilizacaoConcreto.objects.filter(concretagem=conc, ativo=True)
    sobras = SobraConcreto.objects.filter(concretagem=conc, ativo=True)
    if ignorar_uso:
        usos = usos.exclude(pk=ignorar_uso)
    if ignorar_sobra:
        sobras = sobras.exclude(pk=ignorar_sobra)
    if caminhao is not None:
        entregue = caminhao.volume_entregue
        usos, sobras = usos.filter(caminhao=caminhao), sobras.filter(caminhao=caminhao)
        qtd = 1
    else:
        caminhoes = CaminhaoConcretagem.objects.filter(concretagem=conc, ativo=True)
        entregue = _soma(caminhoes, "volume_entregue")
        qtd = caminhoes.count()
    utilizado = _soma(usos, "volume_utilizado")
    sobra = _soma(sobras, "volume_sobra")
    return {
        "volume_solicitado": conc.volume_solicitado or ZERO,
        "volume_entregue": entregue,
        "volume_utilizado": utilizado,
        "volume_sobra": sobra,
        "volume_destinado": utilizado + sobra,
        "saldo": entregue - utilizado - sobra,
        "diferenca_solicitado": entregue - (conc.volume_solicitado or ZERO),
        "qtd_caminhoes": qtd,
    }


def exigir_execucao_aberta(conc):
    """Lançamentos de campo só depois da confirmação e antes de finalizar."""
    if conc.status != S.CONFIRMADA:
        raise FluxoError("Os lançamentos de campo ficam disponíveis com a concretagem confirmada e ainda não finalizada.")


def _validar_volume_destino(conc, volume, caminhao, ignorar_uso=None, ignorar_sobra=None):
    if volume is None or volume <= 0:
        raise FluxoError("Informe um volume maior que zero.")
    geral = resumo_volume(conc, ignorar_uso=ignorar_uso, ignorar_sobra=ignorar_sobra)
    if volume > geral["saldo"] + TOLERANCIA:
        raise FluxoError(f"Volume maior que o saldo sem destinação ({geral['saldo']} m³).")
    if caminhao is not None:
        parcial = resumo_volume(conc, caminhao, ignorar_uso=ignorar_uso, ignorar_sobra=ignorar_sobra)
        if volume > parcial["saldo"] + TOLERANCIA:
            raise FluxoError(f"Volume maior que o saldo do {caminhao.rotulo} ({parcial['saldo']} m³).")


@transaction.atomic
def salvar_caminhao(conc, caminhao, usuario):
    """Cria/edita. Na criação a ordem é recalculada aqui, nunca vinda do formulário."""
    exigir_execucao_aberta(conc)
    novo = caminhao.pk is None
    if caminhao.volume_entregue is None or caminhao.volume_entregue <= 0:
        raise FluxoError("Informe o volume entregue.")
    if not novo:
        destinado = resumo_volume(conc, caminhao)["volume_destinado"]
        if caminhao.volume_entregue + TOLERANCIA < destinado:
            raise FluxoError(f"Este caminhão já tem {destinado} m³ destinados; o volume não pode ser menor.")
    if novo:
        Concretagem.objects.select_for_update().get(pk=conc.pk)
        ultima = CaminhaoConcretagem.objects.filter(concretagem=conc).aggregate(m=Max("ordem"))["m"] or 0
        caminhao.ordem = ultima + 1
        caminhao.concretagem = conc
        caminhao.criado_por = usuario
    caminhao.save()
    SerieMoldagem.objects.get_or_create(caminhao=caminhao)
    registrar_historico(
        conc, usuario, A.OUTRO,
        f"{'Registrado' if novo else 'Atualizado'} {caminhao.rotulo}: {caminhao.volume_entregue} m³.",
    )
    return caminhao


@transaction.atomic
def remover_caminhao(conc, caminhao, usuario):
    exigir_execucao_aberta(conc)
    if resumo_volume(conc, caminhao)["volume_destinado"] > 0:
        raise FluxoError("Remova antes os usos e sobras lançados para este caminhão.")
    caminhao.ativo = False
    caminhao.save(update_fields=["ativo", "atualizado_em"])
    registrar_historico(conc, usuario, A.OUTRO, f"{caminhao.rotulo} removido.")


@transaction.atomic
def salvar_utilizacao(conc, uso, usuario):
    exigir_execucao_aberta(conc)
    if not uso.local_id:
        raise FluxoError("Escolha o local de uso.")
    if uso.local_id and uso.local.obra_id != conc.obra_id:
        raise FluxoError("O local escolhido não pertence a esta obra.")
    if uso.caminhao_id and uso.caminhao.concretagem_id != conc.pk:
        raise FluxoError("Caminhão inválido.")
    _validar_volume_destino(conc, uso.volume_utilizado, uso.caminhao, ignorar_uso=uso.pk)
    novo = uso.pk is None
    uso.concretagem = conc
    if novo:
        uso.responsavel = usuario
    uso.save()
    registrar_historico(conc, usuario, A.OUTRO, f"Uso {'registrado' if novo else 'alterado'}: {uso.volume_utilizado} m³ em {uso.titulo}.")
    return uso


@transaction.atomic
def salvar_sobra(conc, sobra, usuario):
    exigir_execucao_aberta(conc)
    D = SobraConcreto.Destino
    if sobra.caminhao_id and sobra.caminhao.concretagem_id != conc.pk:
        raise FluxoError("Caminhão inválido.")
    if sobra.destino == D.OUTRA_OBRA and not sobra.obra_destino_id:
        raise FluxoError("Escolha a obra que recebeu a sobra.")
    if sobra.destino == D.OUTRA_OBRA and sobra.obra_destino_id == conc.obra_id:
        raise FluxoError("Para usar na mesma obra, escolha “outra estrutura da obra”.")
    if sobra.destino == D.OUTRA_ESTRUTURA and not (sobra.local_destino_id or sobra.descricao_destino):
        raise FluxoError("Escolha o local ou descreva a estrutura que recebeu a sobra.")
    if sobra.local_destino_id and sobra.local_destino.obra_id != conc.obra_id:
        raise FluxoError("O local de destino não pertence a esta obra.")
    if sobra.destino == D.OUTRO and not sobra.descricao_destino:
        raise FluxoError("Descreva o destino da sobra.")
    if sobra.destino != D.OUTRA_OBRA:
        sobra.obra_destino = None
    if sobra.destino != D.OUTRA_ESTRUTURA:
        sobra.local_destino = None
    _validar_volume_destino(conc, sobra.volume_sobra, sobra.caminhao, ignorar_sobra=sobra.pk)
    novo = sobra.pk is None
    sobra.concretagem = conc
    if novo:
        sobra.responsavel = usuario
    sobra.save()
    registrar_historico(conc, usuario, A.OUTRO, f"Sobra {'registrada' if novo else 'alterada'}: {sobra.volume_sobra} m³ — {sobra.destino_texto}.")
    return sobra


def remover_lancamento(conc, objeto, usuario, rotulo):
    exigir_execucao_aberta(conc)
    objeto.ativo = False
    objeto.save(update_fields=["ativo"])
    registrar_historico(conc, usuario, A.OUTRO, f"{rotulo} removido(a).")


def pendencias_ficha(conc):
    """Lista (caminhão, campos faltando) para cada caminhão ativo com ficha incompleta."""
    faltas = []
    for cam in conc.caminhoes.filter(ativo=True).select_related("serie_moldagem"):
        serie = getattr(cam, "serie_moldagem", None)
        if serie is None:
            faltas.append((cam, ["série de moldagem"]))
            continue
        campos = serie.pendencias()
        if campos:
            faltas.append((cam, campos))
    return faltas


def pendencias_finalizar(conc):
    """Mensagens do que impede finalizar a execução (vazio = pode finalizar)."""
    msgs = []
    resumo = resumo_volume(conc)
    if not resumo["qtd_caminhoes"]:
        msgs.append("Registre ao menos um caminhão.")
    elif abs(resumo["saldo"]) > TOLERANCIA:
        msgs.append(f"Ainda há {resumo['saldo']} m³ sem destino: lance o uso e/ou a sobra.")
    for cam, campos in pendencias_ficha(conc):
        msgs.append(f"Ficha de moldagem do {cam.rotulo}: falta {', '.join(campos)}.")
    from obras.models import AnexoConcretagem

    com_nf = AnexoConcretagem.objects.filter(
        concretagem=conc, etapa=AnexoConcretagem.Etapa.NOTA_FISCAL, ativo=True, caminhao__isnull=False,
    ).values("caminhao_id")
    sem_nf = conc.caminhoes.filter(ativo=True).exclude(pk__in=com_nf).order_by("ordem")
    for cam in sem_nf:
        msgs.append(f"Anexe a nota fiscal do {cam.rotulo}.")
    if conc.com_bomba and not conc.nome_bombista:
        msgs.append("Informe o nome do bombista (aba Solicitação).")
    return msgs
