"""Indicadores da concretagem.

Fonte: tabelas da própria concretagem (sem dados simulados). Período filtrado
pela data programada da concretagem; canceladas ficam fora dos volumes.

Fórmulas (m³ com 2 casas; % com 1 casa):
- Volume solicitado = Σ volume_solicitado das concretagens não canceladas.
- Volume entregue  = Σ volume_entregue dos caminhões ativos das concretagens executadas
  (Executada, Aguardando laudos, Concluída).
- Desvio de entrega (%) = (entregue − solicitado das executadas) ÷ solicitado das executadas × 100.
- Sobra (%) = Σ sobras ativas ÷ entregue × 100.  Perda (%) = Σ sobras descartadas/devolvidas ÷ entregue × 100.
- Laudo aprovado: resistência ≥ fck × (60% aos 7d, 71,7% aos 14d, 95% aos 28d).
- % do fck aos 28d = média de (resistência ÷ fck × 100) dos laudos de 28 dias.
- Uso (tempos): horas entre os marcos registrados no sistema, comparadas à meta de cada etapa.
"""
import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean, median

from django.db.models import Min, Sum
from django.utils import timezone

from obras.models import (
    CaminhaoConcretagem, Concretagem, HistoricoConcretagem, LaudoConcretagem, SobraConcreto, UtilizacaoConcreto,
)

S = Concretagem.Status
EXECUTADAS = (S.EXECUTADA, S.AGUARDANDO_LAUDOS, S.CONCLUIDA)
ZERO = Decimal("0")
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _q2(v):
    return Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pct(parte, total):
    if not total:
        return None
    return (Decimal(parte) / Decimal(total) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def base_queryset(inicio, fim, obra_id=None, concreteira_id=None):
    qs = Concretagem.objects.filter(data_programada__range=(inicio, fim))
    if obra_id:
        qs = qs.filter(obra_id=obra_id)
    if concreteira_id:
        qs = qs.filter(concreteira_id=concreteira_id)
    return qs


def calcular(inicio, fim, obra_id=None, concreteira_id=None):
    todas = base_queryset(inicio, fim, obra_id, concreteira_id)
    validas = todas.exclude(status=S.CANCELADA)
    executadas = validas.filter(status__in=EXECUTADAS)

    sol_total = _q2(validas.aggregate(t=Sum("volume_solicitado"))["t"])
    sol_exec = _q2(executadas.aggregate(t=Sum("volume_solicitado"))["t"])
    entregue = _q2(CaminhaoConcretagem.objects.filter(concretagem__in=executadas, ativo=True).aggregate(t=Sum("volume_entregue"))["t"])
    sobras = SobraConcreto.objects.filter(concretagem__in=executadas, ativo=True)
    sobra_total = _q2(sobras.aggregate(t=Sum("volume_sobra"))["t"])
    perda = _q2(sobras.filter(situacao=SobraConcreto.Situacao.PERDIDA).aggregate(t=Sum("volume_sobra"))["t"])

    laudos = list(LaudoConcretagem.objects.filter(concretagem__in=validas).select_related("concretagem"))
    por_idade = {i: {"aprovados": 0, "reprovados": 0} for i in (7, 14, 28)}
    pcts_28 = []
    reprovadas = {}
    for l in laudos:
        chave = "aprovados" if l.aprovado else "reprovados"
        por_idade[l.idade_dias][chave] += 1
        if not l.aprovado:
            reprovadas.setdefault(l.concretagem_id, {"conc": l.concretagem, "laudos": []})["laudos"].append(l)
        if l.idade_dias == 28 and l.percentual_fck is not None:
            pcts_28.append(l.percentual_fck)

    resumo = {
        "total": validas.count(),
        "canceladas": todas.filter(status=S.CANCELADA).count(),
        "concluidas": validas.filter(status=S.CONCLUIDA).count(),
        "executadas": executadas.count(),
        "volume_solicitado": sol_total,
        "volume_solicitado_exec": sol_exec,
        "volume_entregue": entregue,
        "desvio_pct": _pct(entregue - sol_exec, sol_exec),
        "sobra": sobra_total,
        "sobra_pct": _pct(sobra_total, entregue),
        "perda": perda,
        "perda_pct": _pct(perda, entregue),
        "laudos": len(laudos),
        "laudos_reprovados": sum(v["reprovados"] for v in por_idade.values()),
        "media_fck_28": (sum(pcts_28) / len(pcts_28)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if pcts_28 else None,
    }

    # Série mensal
    meses = []
    cursor = datetime.date(inicio.year, inicio.month, 1)
    while cursor <= fim:
        meses.append(cursor)
        cursor = datetime.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    sol_mes, ent_mes = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for data, vol in validas.values_list("data_programada", "volume_solicitado"):
        sol_mes[(data.year, data.month)] += vol or ZERO
    for data, vol in CaminhaoConcretagem.objects.filter(concretagem__in=executadas, ativo=True).values_list(
        "concretagem__data_programada", "volume_entregue",
    ):
        ent_mes[(data.year, data.month)] += vol or ZERO
    serie_mensal = {
        "rotulos": [f"{MESES[m.month - 1]}/{str(m.year)[2:]}" for m in meses],
        "solicitado": [float(_q2(sol_mes[(m.year, m.month)])) for m in meses],
        "entregue": [float(_q2(ent_mes[(m.year, m.month)])) for m in meses],
    }

    destinos = [
        {"destino": SobraConcreto.Destino(d).label, "volume": float(_q2(v))}
        for d, v in sobras.values("destino").annotate(v=Sum("volume_sobra")).order_by("-v").values_list("destino", "v")
    ]

    # Por concreteira
    conc_rows = defaultdict(lambda: {"qtd": 0, "solicitado": ZERO, "sol_exec": ZERO, "entregue": ZERO, "reprovadas": 0})
    nomes = {}
    for c in validas.select_related("concreteira"):
        k = c.concreteira_id or 0
        nomes[k] = c.concreteira_nome or "Sem concreteira"
        conc_rows[k]["qtd"] += 1
        conc_rows[k]["solicitado"] += c.volume_solicitado or ZERO
        if c.status in EXECUTADAS:
            conc_rows[k]["sol_exec"] += c.volume_solicitado or ZERO
        if c.pk in reprovadas:
            conc_rows[k]["reprovadas"] += 1
    for k, v in CaminhaoConcretagem.objects.filter(concretagem__in=executadas, ativo=True).values(
        "concretagem__concreteira_id",
    ).annotate(t=Sum("volume_entregue")).values_list("concretagem__concreteira_id", "t"):
        conc_rows[k or 0]["entregue"] += v or ZERO
    por_concreteira = sorted(
        (
            {"nome": nomes.get(k, "—"), **v, "desvio_pct": _pct(v["entregue"] - v["sol_exec"], v["sol_exec"])}
            for k, v in conc_rows.items()
        ),
        key=lambda r: -r["solicitado"],
    )

    # Por tipo de local de uso
    from obras.models import LocalUsoObra

    rotulos_tipo = dict(LocalUsoObra.Tipo.choices)
    por_tipo = [
        {"tipo": rotulos_tipo.get(t, "Sem local"), "volume": float(_q2(v))}
        for t, v in UtilizacaoConcreto.objects.filter(concretagem__in=executadas, ativo=True)
        .values("local__tipo").annotate(v=Sum("volume_utilizado")).order_by("-v").values_list("local__tipo", "v")
    ]

    return {
        "resumo": resumo,
        "serie_mensal": serie_mensal,
        "laudos_idade": [
            {"idade": f"{i} dias", "aprovados": d["aprovados"], "reprovados": d["reprovados"]} for i, d in por_idade.items()
        ],
        "reprovadas": list(reprovadas.values()),
        "destinos_sobra": destinos,
        "por_concreteira": por_concreteira,
        "por_tipo": por_tipo,
    }


# ---------------------------------------------------------------------------
# Uso do sistema (somente gerente)
# ---------------------------------------------------------------------------

ETAPAS_USO = (
    ("liberacao", "Solicitação", "Da criação até liberar para a concreteira", "Usuário", 24),
    ("confirmacao", "Confirmação", "Da liberação até a concreteira aceitar", "Concreteira", None),
    ("primeiro_caminhao", "1º caminhão", "Do horário programado até o 1º caminhão lançado", "Usuário", 1),
    ("finalizacao", "Finalização", "Do 1º caminhão até finalizar a execução", "Usuário", 12),
    ("envio_cps", "Envio dos CPs", "Da finalização até registrar o envio ao laboratório", "Usuário", 48),
    ("laudo", "Lançamento de laudo", "Da data prevista do rompimento até lançar o laudo", "Usuário", 72),
)


def _horas(inicio, fim):
    if not inicio or not fim:
        return None
    return round((fim - inicio).total_seconds() / 3600, 1)


def _resumir(horas, meta):
    horas = [h for h in horas if h is not None]
    if not horas:
        return {"n": 0, "media": None, "mediana": None, "na_meta": None}
    dentro = sum(1 for h in horas if meta is None or h <= meta)
    return {
        "n": len(horas), "media": round(mean(horas), 1), "mediana": round(median(horas), 1),
        "na_meta": round(dentro / len(horas) * 100, 1) if meta is not None else None,
    }


def calcular_uso(inicio, fim, obra_id=None, concreteira_id=None):
    concs = list(base_queryset(inicio, fim, obra_id, concreteira_id).exclude(status=S.CANCELADA).select_related("criado_por"))
    ids = [c.pk for c in concs]
    marcos = defaultdict(dict)
    for h in HistoricoConcretagem.objects.filter(concretagem_id__in=ids, acao__in=("MUDANCA_STATUS", "RESPOSTA_CONCRETEIRA")).order_by("criado_em"):
        marcos[h.concretagem_id].setdefault(h.status_novo, h.criado_em)
    primeiro_cam = dict(
        CaminhaoConcretagem.objects.filter(concretagem_id__in=ids).values("concretagem_id")
        .annotate(m=Min("criado_em")).values_list("concretagem_id", "m")
    )
    tz = timezone.get_current_timezone()
    tempos = defaultdict(list)
    por_usuario = defaultdict(lambda: {"criadas": 0, "horas_liberacao": []})
    for c in concs:
        m = marcos[c.pk]
        liberacao = _horas(c.criado_em, m.get("SOLICITADA"))
        tempos["liberacao"].append(liberacao)
        tempos["confirmacao"].append(_horas(m.get("SOLICITADA"), m.get("CONFIRMADA")))
        if c.data_programada and c.horario_programado and c.pk in primeiro_cam:
            programado = timezone.make_aware(datetime.datetime.combine(c.data_programada, c.horario_programado), tz)
            atraso = _horas(programado, primeiro_cam[c.pk])
            tempos["primeiro_caminhao"].append(max(atraso, 0) if atraso is not None else None)
        tempos["finalizacao"].append(_horas(primeiro_cam.get(c.pk), c.executada_em))
        tempos["envio_cps"].append(_horas(c.executada_em, c.cps_enviados_em))
        if c.criado_por_id:
            u = por_usuario[c.criado_por]
            u["criadas"] += 1
            u["horas_liberacao"].append(liberacao)
    for l in LaudoConcretagem.objects.filter(concretagem_id__in=ids).select_related("concretagem"):
        c = l.concretagem
        base = c.executada_em or (
            timezone.make_aware(datetime.datetime.combine(c.data_programada, datetime.time(12)), tz) if c.data_programada else None
        )
        if base:
            atraso = _horas(base + datetime.timedelta(days=l.idade_dias), l.lancado_em)
            tempos["laudo"].append(max(atraso, 0) if atraso is not None else None)

    etapas = [
        {"chave": k, "nome": n, "descricao": d, "responsavel": r, "meta": meta, **_resumir(tempos[k], meta)}
        for k, n, d, r, meta in ETAPAS_USO
    ]
    acoes = defaultdict(int)
    for uid in HistoricoConcretagem.objects.filter(concretagem_id__in=ids, usuario__isnull=False).values_list("usuario_id", flat=True):
        acoes[uid] += 1
    usuarios = sorted(
        (
            {
                "nome": u.get_full_name() or u.username,
                "criadas": d["criadas"],
                "acoes": acoes.get(u.pk, 0),
                "media_liberacao": _resumir(d["horas_liberacao"], 24)["media"],
            }
            for u, d in por_usuario.items()
        ),
        key=lambda r: (-r["acoes"], r["nome"]),
    )
    return {"etapas": etapas, "usuarios": usuarios}
