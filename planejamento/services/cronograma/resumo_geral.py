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
            "id", "semana", "data_atualizacao", "inicio_real", "duracao_real",
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
    return serie


def calcular_avancos_semanais(serie):
    resultado = []
    anterior_executado = None
    anterior_previsto = None
    for item in serie:
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


def calcular_media_avancos(avancos, *, limite_semanas=4):
    if not avancos:
        return {"media_real": 0.0, "media_previsto": 0.0, "quantidade_semanas": 0}
    recorte = avancos[-limite_semanas:]
    quantidade = len(recorte)
    return {
        "media_real": sum(i["avanco_real"] for i in recorte) / quantidade,
        "media_previsto": sum(i["avanco_previsto"] for i in recorte) / quantidade,
        "quantidade_semanas": quantidade,
    }
