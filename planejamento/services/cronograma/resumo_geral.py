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



def _calcular_equivalente_dias(*, data_referencia, previsto, realizado, pontos):
    """Diferença temporal estimada relativa à curva planejada acumulada.

    Convenção: positivo = atraso; negativo = adiantamento.
    Busca a data em que o planejado alcançou o percentual realizado,
    interpolando entre medições. Quando o realizado supera todos os pontos
    disponíveis, extrapola pelo ritmo planejado recente e marca estimado.
    Não converte diretamente percentual em dias nem considera semana=7 dias.
    """
    if data_referencia is None:
        return None, False
    if abs(realizado - previsto) <= TOLERANCIA_PERCENTUAL:
        return 0, False

    por_data = {}
    for item in pontos:
        data = item.get("data_referencia") or item.get("data_atualizacao") or item.get("inicio_semana")
        if data is not None:
            por_data[data] = float(item.get("previsto") or 0.0)
    curva = sorted(por_data.items())
    if len(curva) < 2:
        return None, False

    # Última passagem pelo percentual, sem assumir que revisões da linha-base
    # tornem a série necessariamente crescente em todos os momentos.
    cruzamentos = []
    for (dia_inicio, valor_inicio), (dia_fim, valor_fim) in zip(curva, curva[1:]):
        if valor_fim <= valor_inicio or not (valor_inicio <= realizado <= valor_fim):
            continue
        proporcao = (realizado - valor_inicio) / (valor_fim - valor_inicio)
        # Date + timedelta fracionário descarta subdias. Preserve a fração
        # até o arredondamento final para não transformar 1 dia em "No prazo".
        dias_alvo_menos_referencia = (
            (dia_inicio - data_referencia).days
            + (dia_fim - dia_inicio).days * proporcao
        )
        cruzamentos.append(dias_alvo_menos_referencia)
    if cruzamentos:
        # Para atraso, escolhe o último cruzamento anterior à medição.
        # Para adiantamento, escolhe o primeiro cruzamento posterior.
        possiveis = ([dias for dias in cruzamentos if dias <= 0]
                     if realizado < previsto else
                     [dias for dias in cruzamentos if dias >= 0])
        if possiveis:
            deslocamento = max(possiveis) if realizado < previsto else min(possiveis)
            return round(-deslocamento), False

    if realizado <= previsto:
        # A curva não possui histórico suficiente para situar o avanço físico.
        return None, False

    # Avanço superior ao último ponto projetado: extrapolação local pela taxa
    # planejada das medições mais recentes, usando dias efetivamente decorridos.
    anteriores = [(data, valor) for data, valor in curva if data <= data_referencia]
    if len(anteriores) < 2:
        return None, False
    ultimos = anteriores[-5:]
    dias = (ultimos[-1][0] - ultimos[0][0]).days
    ganho = ultimos[-1][1] - ultimos[0][1]
    if dias <= 0 or ganho <= TOLERANCIA_PERCENTUAL:
        return None, False
    ritmo_por_dia = ganho / dias
    dias_adiantados = (realizado - previsto) / ritmo_por_dia
    if dias_adiantados > 3650:  # evita projeções absurdas por base quase parada
        return None, False
    return -max(1, round(dias_adiantados)), True


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
        referencia = item.get("data_referencia") or item.get("data_atualizacao") or item.get("inicio_semana")
        desvio_dias, desvio_estimado = _calcular_equivalente_dias(
            data_referencia=referencia,
            previsto=previsto,
            realizado=real,
            pontos=serie,
        )
        resultado.append({
            "ano": ano_mes[0], "mes": ano_mes[1],
            "periodo": f"{ano_mes[1]:02d}/{ano_mes[0]}",
            "data_referencia": item.get("data_referencia") or item.get("data_atualizacao") or item.get("inicio_semana"),
            "executado_acumulado": real, "previsto_acumulado": previsto,
            "avanco_real": real - anterior_real,
            "avanco_previsto": previsto - anterior_previsto,
            "desvio_acumulado": real - previsto,
            "desvio_dias": desvio_dias,
            "desvio_dias_estimado": desvio_estimado,
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
