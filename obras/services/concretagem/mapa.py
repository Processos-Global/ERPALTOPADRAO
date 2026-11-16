"""Regras do mapa de concretagem e dos formatos de desenho.

- Quem preenche o mapa cria, edita e aplica formatos direto (sem aprovação) e pinta.
- Uma célula fora do contorno nunca é pintada.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Q

from obras.models import (
    CelulaMapa, FormatoDesenho, MapaLocal, SobraConcreto, UtilizacaoConcreto,
)
from obras.models.concretagem.execucao import proxima_cor
from obras.models.concretagem.mapa import MAX_DIMENSAO

from .fluxo import FluxoError



# ---------------------------------------------------------------------------
# Validação comum
# ---------------------------------------------------------------------------

def validar_dimensoes(linhas, colunas):
    try:
        linhas, colunas = int(linhas), int(colunas)
    except (TypeError, ValueError):
        raise FluxoError("Informe linhas e colunas.")
    if not (1 <= linhas <= MAX_DIMENSAO and 1 <= colunas <= MAX_DIMENSAO):
        raise FluxoError(f"Linhas e colunas devem ficar entre 1 e {MAX_DIMENSAO}.")
    return linhas, colunas


def _validar_formato(nome, linhas, colunas, excluir_formato=None):
    nome = (nome or "").strip()
    if not nome:
        raise FluxoError("Dê um nome ao formato.")
    linhas, colunas = validar_dimensoes(linhas, colunas)
    qs = FormatoDesenho.objects.filter(nome__iexact=nome)
    if excluir_formato:
        qs = qs.exclude(pk=excluir_formato.pk)
    if qs.exists():
        raise FluxoError("Já existe um formato com esse nome.")
    return nome[:120], linhas, colunas


# ---------------------------------------------------------------------------
# Formatos: criação direta (gerente) ou proposta (demais)
# ---------------------------------------------------------------------------

@transaction.atomic
def salvar_formato(usuario, nome, linhas, colunas, celulas_fora, obra=None, formato=None):
    """Cria ou edita um formato direto (sem aprovação). O tamanho de um formato já aplicado não muda."""
    nome, linhas, colunas = _validar_formato(nome, linhas, colunas, excluir_formato=formato)
    if formato is not None and formato.mapas.exclude(linhas=linhas, colunas=colunas).exists():
        raise FluxoError("Este formato está aplicado em mapas; não é possível mudar o tamanho dele.")
    alvo = formato or FormatoDesenho(criado_por=usuario, obra_origem=obra)
    alvo.nome, alvo.linhas, alvo.colunas, alvo.celulas_fora = nome, linhas, colunas, celulas_fora
    alvo.save()
    if formato is not None:
        # Contorno alterado: células que ficaram fora deixam de valer nos mapas que usam o formato.
        for mapa in formato.mapas.all():
            for linha, coluna in alvo.celulas_fora:
                mapa.celulas.filter(linha=linha, coluna=coluna).delete()
    return alvo


# ---------------------------------------------------------------------------
# Mapa do local
# ---------------------------------------------------------------------------

def mapa_do_local(local):
    return MapaLocal.objects.filter(local=local).select_related("formato").first()


@transaction.atomic
def definir_mapa(local, usuario, linhas=None, colunas=None, formato=None):
    """Define o tamanho da grade (ou aplica um formato). Células fora da nova grade são apagadas."""
    if formato is not None:
        linhas, colunas = formato.linhas, formato.colunas
    linhas, colunas = validar_dimensoes(linhas, colunas)
    mapa, _ = MapaLocal.objects.get_or_create(local=local, defaults={"linhas": linhas, "colunas": colunas})
    mapa.linhas, mapa.colunas, mapa.formato = linhas, colunas, formato
    mapa.atualizado_por = usuario
    mapa.save()
    mapa.celulas.filter(Q(linha__gt=linhas) | Q(coluna__gt=colunas)).delete()
    if formato is not None:
        for linha, coluna in formato.celulas_fora:
            mapa.celulas.filter(linha=linha, coluna=coluna).delete()
    return mapa


def _hora(t):
    return t.strftime("%H:%M") if t else ""


def _dados_caminhao(cam):
    """Dados do caminhão para a lista do mapa (mesmas colunas do mapa original).

    Tempo total = término da descarga − início da mistura (série de moldagem),
    somando 24 h quando a descarga termina depois da meia-noite.
    """
    if cam is None:
        return {"caminhao": "", "nf": "", "cps": "", "inicio_mistura": "", "chegada": "",
                "inicio_descarga": "", "termino": "", "tempo_total": ""}
    try:
        mistura = cam.serie_moldagem.inicio_mistura
    except ObjectDoesNotExist:
        mistura = None
    tempo = ""
    if mistura and cam.termino_descarga:
        minutos = (cam.termino_descarga.hour * 60 + cam.termino_descarga.minute) - (mistura.hour * 60 + mistura.minute)
        if minutos < 0:
            minutos += 24 * 60
        tempo = f"{minutos // 60}h{minutos % 60:02d}"
    return {
        "caminhao": cam.rotulo, "nf": cam.numero_nota_fiscal, "cps": cam.cps_moldados,
        "inicio_mistura": _hora(mistura), "chegada": _hora(cam.horario_chegada),
        "inicio_descarga": _hora(cam.inicio_descarga), "termino": _hora(cam.termino_descarga),
        "tempo_total": tempo,
    }


def itens_paleta(local):
    """Usos deste local e sobras reaproveitáveis da obra (inclusive as recebidas de outra obra)."""
    obra_id = local.obra_id
    usos = list(
        UtilizacaoConcreto.objects.filter(ativo=True, local=local, concretagem__obra_id=obra_id)
        .exclude(concretagem__status="CANCELADA")
        .select_related("concretagem", "caminhao__serie_moldagem").order_by("concretagem__data_programada", "id")
    )
    sobras = list(
        SobraConcreto.objects.filter(ativo=True)
        .filter(Q(concretagem__obra_id=obra_id) | Q(obra_destino_id=obra_id))
        .exclude(situacao=SobraConcreto.Situacao.PERDIDA)
        .exclude(Q(destino=SobraConcreto.Destino.OUTRA_OBRA) & ~Q(obra_destino_id=obra_id))
        .exclude(concretagem__status="CANCELADA")
        .select_related("concretagem__obra", "caminhao__serie_moldagem", "local_destino", "obra_destino").order_by("registrado_em")
    )
    for obj in usos + sobras:
        if not obj.cor:
            obj.cor = proxima_cor(obj.concretagem.obra_id)
            type(obj).objects.filter(pk=obj.pk).update(cor=obj.cor)
    itens = []
    for u in usos:
        c = u.concretagem
        itens.append({
            "chave": f"u{u.pk}", "cor": u.cor, "tipo": "Uso",
            "titulo": f"{c.codigo} · {u.volume_utilizado} m³",
            "detalhe": " · ".join(filter(None, [
                c.data_programada.strftime("%d/%m/%Y") if c.data_programada else "",
                u.descricao, u.caminhao.rotulo if u.caminhao_id else "",
            ])),
            "codigo": c.codigo, "data": c.data_programada, "volume": u.volume_utilizado,
            **_dados_caminhao(u.caminhao if u.caminhao_id else None),
        })
    for s in sobras:
        c = s.concretagem
        recebida = c.obra_id != obra_id
        itens.append({
            "chave": f"s{s.pk}", "cor": s.cor, "tipo": "Sobra recebida" if recebida else "Sobra",
            "titulo": f"{c.codigo} · {s.volume_sobra} m³",
            "detalhe": (f"de {c.obra.nome} · " if recebida else "") + s.destino_texto,
            "codigo": c.codigo, "data": c.data_programada, "volume": s.volume_sobra,
            **_dados_caminhao(s.caminhao if s.caminhao_id else None),
        })
    return itens


def resolver_item(chave, local):
    """'u12' / 's5' -> (utilizacao, sobra) válidos para este local; ('', '') apaga."""
    if not chave:
        return None, None
    validos = {i["chave"] for i in itens_paleta(local)}
    if chave not in validos:
        raise FluxoError("Item da legenda inválido para este local.")
    if chave.startswith("u"):
        return UtilizacaoConcreto.objects.get(pk=int(chave[1:])), None
    return None, SobraConcreto.objects.get(pk=int(chave[1:]))


@transaction.atomic
def pintar(mapa, celulas, chave, usuario):
    """Pinta (ou apaga, com chave vazia) um lote de células. Retorna quantas mudaram."""
    utilizacao, sobra = resolver_item(chave, mapa.local)
    fora = {tuple(c) for c in mapa.celulas_fora}
    posicoes = set()
    for item in celulas or []:
        try:
            linha, coluna = int(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if 1 <= linha <= mapa.linhas and 1 <= coluna <= mapa.colunas and (linha, coluna) not in fora:
            posicoes.add((linha, coluna))
    if len(posicoes) > MAX_DIMENSAO * MAX_DIMENSAO:
        raise FluxoError("Lote grande demais.")
    for linha, coluna in posicoes:
        if utilizacao is None and sobra is None:
            mapa.celulas.filter(linha=linha, coluna=coluna).delete()
        else:
            CelulaMapa.objects.update_or_create(
                mapa=mapa, linha=linha, coluna=coluna,
                defaults={"utilizacao": utilizacao, "sobra": sobra, "atualizado_por": usuario},
            )
    return len(posicoes)


def estado_mapa(mapa):
    """Células pintadas como {"l,c": chave} para o front."""
    estado = {}
    for c in mapa.celulas.all().only("linha", "coluna", "utilizacao_id", "sobra_id"):
        chave = f"u{c.utilizacao_id}" if c.utilizacao_id else f"s{c.sobra_id}" if c.sobra_id else ""
        if chave:
            estado[f"{c.linha},{c.coluna}"] = chave
    return estado


def resumo_locais(obra):
    """Locais da obra com indicação de mapa definido e células pintadas."""
    from obras.models import LocalUsoObra

    return (
        LocalUsoObra.objects.filter(obra=obra, ativo=True)
        .annotate(pintadas=Count("mapa__celulas", distinct=True), usos=Count("utilizacoes", filter=Q(utilizacoes__ativo=True), distinct=True))
        .select_related("mapa")
        .order_by("ordem", "nome")
    )
