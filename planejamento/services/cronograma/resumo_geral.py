from datetime import date, timedelta

from .consultas import CronogramaBaseError, decimal_para_float, queryset_ativo


TOLERANCIA_PERCENTUAL = 0.001


def _valor_executado(registro):
    valor = registro.get("percentual_executado")
    if valor is None:
        valor = registro.get("percentual_concluida")
    return decimal_para_float(valor)


def _valor_previsto(registro):
    valor = registro.get("percentual_previsto")
    if valor is None:
        valor = registro.get("percentual_previsto_tarefa")
    return decimal_para_float(valor)


def obter_resumo_geral(*, projeto, semana):
    registros = list(
        queryset_ativo(projeto=projeto, semana=semana)
        .filter(disciplina__iexact="RESUMO GERAL")
        .values(
            "id", "obra_id", "semana", "data_atualizacao", "inicio_real",
            "duracao_real", "termino_real", "inicio_base", "duracao_base",
            "termino_base", "percentual_concluida", "percentual_previsto_tarefa",
            "percentual_executado", "percentual_previsto",
        )
        .order_by("id")
    )
    if not registros:
        return None

    registro = registros[-1]
    executado = _valor_executado(registro)
    previsto = _valor_previsto(registro)
    if executado <= TOLERANCIA_PERCENTUAL and previsto <= TOLERANCIA_PERCENTUAL:
        situacao_fisica = "SEM DADOS"
    elif executado + TOLERANCIA_PERCENTUAL >= previsto:
        situacao_fisica = "NO PRAZO"
    else:
        situacao_fisica = "ATRASADO"

    return {
        "registro_id": registro["id"],
        "obra_id": registro.get("obra_id"),
        "projeto": projeto,
        "semana": semana,
        "data_atualizacao": registro["data_atualizacao"],
        "inicio_real": registro["inicio_real"],
        "duracao_real": decimal_para_float(registro["duracao_real"]),
        "termino_real": registro["termino_real"],
        "inicio_base": registro["inicio_base"],
        "duracao_base": decimal_para_float(registro["duracao_base"]),
        "termino_base": registro["termino_base"],
        "executado": executado,
        "previsto": previsto,
        "desvio": executado - previsto,
        "restante": max(1.0 - executado, 0.0),
        "situacao_fisica": situacao_fisica,
        "quantidade_resumos_gerais": len(registros),
    }


def obter_resumo_geral_unico(*, projeto, semana):
    resumo = obter_resumo_geral(projeto=projeto, semana=semana)
    if resumo is None:
        raise CronogramaBaseError(
            f"Não existe RESUMO GERAL para {projeto}, semana {semana}."
        )
    return resumo


def obter_serie_resumo_geral(*, projeto):
    registros = list(
        queryset_ativo(projeto=projeto)
        .filter(disciplina__iexact="RESUMO GERAL")
        .exclude(semana__isnull=True)
        .values(
            "id", "semana", "data_atualizacao", "inicio_semana", "inicio_real", "duracao_real",
            "termino_real", "inicio_base", "duracao_base", "termino_base",
            "percentual_concluida", "percentual_previsto_tarefa",
            "percentual_executado", "percentual_previsto",
        )
        .order_by("semana", "id")
    )
    por_semana = {registro["semana"]: registro for registro in registros}
    serie = []
    for numero_semana in sorted(por_semana):
        registro = por_semana[numero_semana]
        executado = _valor_executado(registro)
        previsto = _valor_previsto(registro)
        serie.append({
            "semana": numero_semana,
            "data_atualizacao": registro["data_atualizacao"],
            "inicio_semana": registro["inicio_semana"],
            "executado": executado,
            "previsto": previsto,
            "desvio": executado - previsto,
            "inicio_real": registro["inicio_real"],
            "duracao_real": decimal_para_float(registro["duracao_real"]),
            "termino_real": registro["termino_real"],
            "inicio_base": registro["inicio_base"],
            "duracao_base": decimal_para_float(registro["duracao_base"]),
            "termino_base": registro["termino_base"],
        })
    for indice, item in enumerate(serie):
        inicio = item["inicio_semana"]
        seguinte = serie[indice + 1]["inicio_semana"] if indice + 1 < len(serie) else None
        item["fim_semana"] = (
            min(seguinte - timedelta(days=1), inicio + timedelta(days=6))
            if inicio and seguinte and 0 < (seguinte - inicio).days <= 14
            else (inicio + timedelta(days=6) if inicio else None)
        )
        item["data_referencia"] = item["data_atualizacao"] or inicio
    return serie


def calcular_avancos_semanais(serie):
    resultado = []
    anterior_executado = None
    anterior_previsto = None
    for item in sorted(
        serie,
        key=lambda registro: (
            registro.get("data_referencia") or registro.get("data_atualizacao") or registro.get("inicio_semana")
            or date.min,
            registro.get("semana") or 0,
        ),
    ):
        executado = float(item.get("executado") or 0.0)
        previsto = float(item.get("previsto") or 0.0)
        if anterior_executado is None:
            avanco_real = executado
            avanco_previsto = previsto
        else:
            avanco_real = executado - anterior_executado
            avanco_previsto = previsto - anterior_previsto
        resultado.append({
            "semana": item["semana"],
            "inicio_semana": item.get("inicio_semana"),
            "fim_semana": item.get("fim_semana"),
            "data_referencia": item.get("data_referencia"),
            "executado_acumulado": executado,
            "previsto_acumulado": previsto,
            "avanco_real": avanco_real,
            "avanco_previsto": avanco_previsto,
            "desvio_semanal": avanco_real - avanco_previsto,
            "desvio_acumulado": executado - previsto,
        })
        anterior_executado = executado
        anterior_previsto = previsto
    return resultado


def calcular_avancos_mensais(serie):
    """Último snapshot de cada mês; incrementos são diferenças entre acumulados."""
    por_mes = {}
    for item in sorted(
        serie,
        key=lambda registro: (
            registro.get("data_referencia") or registro.get("data_atualizacao") or registro.get("inicio_semana") or date.min,
            registro.get("semana") or 0,
        ),
    ):
        data = item.get("data_referencia") or item.get("data_atualizacao") or item.get("inicio_semana")
        if data:
            por_mes[(data.year, data.month)] = item
    resultado = []
    anterior_real = anterior_previsto = 0.0
    for ano_mes in sorted(por_mes):
        item = por_mes[ano_mes]
        real = float(item.get("executado") or 0.0)
        previsto = float(item.get("previsto") or 0.0)
        resultado.append({
            "ano": ano_mes[0], "mes": ano_mes[1],
            "periodo": f"{ano_mes[1]:02d}/{ano_mes[0]}",
            "data_referencia": item.get("data_referencia") or item.get("data_atualizacao") or item.get("inicio_semana"),
            "executado_acumulado": real, "previsto_acumulado": previsto,
            "avanco_real": real - anterior_real,
            "avanco_previsto": previsto - anterior_previsto,
            "desvio_acumulado": real - previsto,
        })
        anterior_real, anterior_previsto = real, previsto
    return resultado


def calcular_media_avancos(avancos, *, limite_semanas=4):
    # O primeiro retrato é uma base acumulada, não o avanço daquela semana.
    recorte = avancos[1:][-limite_semanas:]
    if not recorte:
        return {"media_real": 0.0, "media_previsto": 0.0, "quantidade_semanas": 0}
    quantidade = len(recorte)
    return {
        "media_real": sum(i["avanco_real"] for i in recorte) / quantidade,
        "media_previsto": sum(i["avanco_previsto"] for i in recorte) / quantidade,
        "quantidade_semanas": quantidade,
    }
