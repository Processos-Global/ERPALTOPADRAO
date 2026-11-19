"""Leitura gerencial das atividades de vistoria do cronograma ativo."""

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date

from obras.models import VistoriaItem
from planejamento.models import ImportacaoCronograma, RegistroCronograma


DISCIPLINAS_VISTORIA = (
    "CHECKLIST HABITE-SE", "CHECKLIST PRE HABITE-SE",
    "CHECKLIST PRÉ HABITE-SE", "POS HABITE-SE", "PÓS HABITE-SE",
)
DISCIPLINAS_PRE = frozenset(DISCIPLINAS_VISTORIA[:3])
SITUACOES_FILTRO = (
    ("FEITO", "Feito"),
    ("NAO_FEITO", "Não feito (avaliado)"),
    ("SEM_AVALIACAO", "Sem avaliação"),
)


def _data(valor):
    if not valor:
        return None
    try:
        return parse_date(valor)
    except ValueError:
        return None


def montar_resumo_vistorias(parametros):
    """Resumo do estado atual; período restringe snapshots por data_atualizacao."""
    obra_texto = (parametros.get("obra") or "").strip()
    obra_id = int(obra_texto) if obra_texto.isdigit() else None
    tipo = (parametros.get("tipo") or "").strip().upper()
    if tipo not in {"PRE", "POS"}:
        tipo = ""
    situacao = (parametros.get("situacao") or "").strip().upper()
    if situacao not in dict(SITUACOES_FILTRO):
        situacao = ""
    inicio = _data((parametros.get("inicio") or "").strip())
    fim = _data((parametros.get("fim") or "").strip())
    filtros = {
        "obra": obra_id, "tipo": tipo, "situacao": situacao,
        "inicio": inicio, "fim": fim,
    }
    resultado = {
        "filtros": filtros, "obras_filtro": [], "linhas": [], "pendencias": [],
        "situacoes_filtro": SITUACOES_FILTRO,
        "resumo": {"total": 0, "realizadas": 0, "nao_realizadas": 0,
                   "sem_avaliacao": 0, "percentual": 0},
        "ultima_atualizacao": None,
        "importacao": None,
    }
    importacao = (ImportacaoCronograma.objects.filter(
        ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA,
    ).order_by("-id").first())
    if importacao is None:
        return resultado
    resultado["importacao"] = importacao

    base = RegistroCronograma.objects.filter(
        importacao=importacao, obra__ativa=True,
        atividade_planejamento__isnull=False,
        atividade_planejamento__ativa=True,
        disciplina__in=DISCIPLINAS_VISTORIA,
    )
    resultado["obras_filtro"] = list(base.order_by("obra__nome", "obra_id").values(
        "obra_id", "obra__nome",
    ).distinct())
    if obra_id:
        base = base.filter(obra_id=obra_id)
    if inicio:
        base = base.filter(data_atualizacao__gte=inicio)
    if fim:
        base = base.filter(data_atualizacao__lte=fim)
    if tipo:
        base = base.filter(disciplina__in=(
            DISCIPLINAS_PRE if tipo == "PRE"
            else set(DISCIPLINAS_VISTORIA) - DISCIPLINAS_PRE
        ))

    # A identidade permanente evita contar novamente a mesma atividade em
    # cada snapshot semanal. A ordenação escolhe o snapshot mais recente.
    atividades = {}
    registros = base.order_by("-semana", "-id").values(
        "atividade_planejamento_id", "obra_id", "obra__nome",
        "disciplina", "nome_tarefa", "local_tarefa", "data_atualizacao",
        "atividade_planejamento__nome_tarefa",
    )
    for registro in registros.iterator(chunk_size=1000):
        atividades.setdefault(registro["atividade_planejamento_id"], registro)

    estados = {
        estado.atividade_id: estado
        for estado in VistoriaItem.objects.filter(atividade_id__in=atividades)
        .only("atividade_id", "status", "atualizado_em")
    }
    por_obra = {}
    for atividade_id, registro in atividades.items():
        estado = estados.get(atividade_id)
        estado_filtro = estado.status if estado else "SEM_AVALIACAO"
        if situacao and situacao != estado_filtro:
            continue
        obra = por_obra.setdefault(registro["obra_id"], {
            "obra_id": registro["obra_id"], "obra_nome": registro["obra__nome"],
            "total": 0, "realizadas": 0, "nao_realizadas": 0,
            "sem_avaliacao": 0, "percentual": 0, "ultima_atualizacao": None,
        })
        obra["total"] += 1
        resultado["resumo"]["total"] += 1
        if estado_filtro == "FEITO":
            obra["realizadas"] += 1
            resultado["resumo"]["realizadas"] += 1
        else:
            obra["nao_realizadas"] += 1
            resultado["resumo"]["nao_realizadas"] += 1
            if estado is None:
                obra["sem_avaliacao"] += 1
                resultado["resumo"]["sem_avaliacao"] += 1
            resultado["pendencias"].append({
                "obra_nome": registro["obra__nome"],
                "atividade": registro["nome_tarefa"] or registro["atividade_planejamento__nome_tarefa"],
                "local": registro["local_tarefa"] or "Sem local informado",
                "tipo": "Pré Habite-se" if registro["disciplina"] in DISCIPLINAS_PRE else "Pós Habite-se",
                "situacao": "Sem avaliação" if estado is None else "Não feito",
            })
        data_registro = registro["data_atualizacao"]
        atualizacao = estado.atualizado_em if estado else None
        if data_registro:
            data_snapshot = timezone.make_aware(datetime.combine(data_registro, time.min))
            atualizacao = max(atualizacao, data_snapshot) if atualizacao else data_snapshot
        if atualizacao:
            obra["ultima_atualizacao"] = max(
                obra["ultima_atualizacao"], atualizacao,
            ) if obra["ultima_atualizacao"] else atualizacao

    for obra in por_obra.values():
        obra["percentual"] = round(100 * obra["realizadas"] / obra["total"], 1)
    resultado["linhas"] = sorted(por_obra.values(), key=lambda x: x["obra_nome"].casefold())
    resultado["pendencias"].sort(key=lambda x: (x["obra_nome"].casefold(), x["atividade"].casefold()))
    total = resultado["resumo"]["total"]
    if total:
        resultado["resumo"]["percentual"] = round(100 * resultado["resumo"]["realizadas"] / total, 1)
    datas = [linha["ultima_atualizacao"] for linha in resultado["linhas"] if linha["ultima_atualizacao"]]
    resultado["ultima_atualizacao"] = max(datas) if datas else None
    return resultado
