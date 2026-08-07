from datetime import timedelta


TOLERANCIA_PERCENTUAL = 0.001


def _calcular_idp(*, duracao_base, duracao_real):
    if duracao_base <= 0 or duracao_real <= 0:
        return None
    return duracao_base / duracao_real


def _calcular_aderencia_fisica(*, executado, previsto):
    if previsto <= 0:
        return None
    return executado / previsto


def _classificar_idp(idp):
    if idp is None:
        return "SEM_DADOS", "Sem dados suficientes"
    if idp > 1.0 + TOLERANCIA_PERCENTUAL:
        return "ADIANTADO", "Duração melhor que a planejada"
    if idp < 1.0 - TOLERANCIA_PERCENTUAL:
        return "ATRASADO", "Duração acima da planejada"
    return "NO_PRAZO", "Duração aderente ao planejado"


def _classificar_situacao_fisica(*, executado, previsto):
    if executado > previsto + TOLERANCIA_PERCENTUAL:
        return "ACIMA_DO_PREVISTO", "Acima do previsto"
    if executado + TOLERANCIA_PERCENTUAL < previsto:
        return "ABAIXO_DO_PREVISTO", "Abaixo do previsto"
    return "IGUAL_AO_PREVISTO", "Igual ao previsto"


def _classificar_situacao_prazo(
    *,
    termino_planejado,
    termino_real,
    data_atualizacao,
):
    if not termino_planejado:
        return "SEM_DADOS", "Término planejado não informado", None, None

    data_comparada = termino_real or data_atualizacao
    if not data_comparada:
        return "SEM_DADOS", "Data de referência não informada", None, None

    diferenca_dias = (data_comparada - termino_planejado).days

    if diferenca_dias <= 0:
        return "NO_PRAZO", "No prazo", diferenca_dias, data_comparada

    return "EM_ATRASO", "Em atraso", diferenca_dias, data_comparada


def calcular_indicadores_prazo(*, resumo, media_avanco_real):
    executado = max(float(resumo.get("executado") or 0.0), 0.0)
    previsto = max(float(resumo.get("previsto") or 0.0), 0.0)
    restante = max(float(resumo.get("restante") or 0.0), 0.0)
    duracao_base = max(float(resumo.get("duracao_base") or 0.0), 0.0)
    duracao_real = max(float(resumo.get("duracao_real") or 0.0), 0.0)

    termino_planejado = resumo.get("termino_base")
    termino_real = resumo.get("termino_real")
    data_atualizacao = resumo.get("data_atualizacao")

    semanas_restantes = None
    previsao_termino = None

    if media_avanco_real > 0:
        semanas_restantes = restante / media_avanco_real
        if data_atualizacao:
            previsao_termino = data_atualizacao + timedelta(
                days=round(semanas_restantes * 7)
            )

    idp = _calcular_idp(
        duracao_base=duracao_base,
        duracao_real=duracao_real,
    )
    idp_situacao, idp_rotulo = _classificar_idp(idp)

    aderencia = _calcular_aderencia_fisica(
        executado=executado,
        previsto=previsto,
    )
    situacao_fisica, situacao_fisica_rotulo = (
        _classificar_situacao_fisica(
            executado=executado,
            previsto=previsto,
        )
    )
    (
        situacao_prazo,
        situacao_prazo_rotulo,
        dias_diferenca_prazo,
        data_comparada_prazo,
    ) = _classificar_situacao_prazo(
        termino_planejado=termino_planejado,
        termino_real=termino_real,
        data_atualizacao=data_atualizacao,
    )

    return {
        "situacao": situacao_prazo,
        "situacao_rotulo": situacao_prazo_rotulo,
        "dias_diferenca_prazo": dias_diferenca_prazo,
        "data_comparada_prazo": data_comparada_prazo,
        "termino_planejado": termino_planejado,
        "termino_real": termino_real,
        "previsao_termino": previsao_termino,
        "semanas_restantes_estimadas": semanas_restantes,
        "media_avanco_semanal": media_avanco_real,
        "idp": idp,
        "idp_situacao": idp_situacao,
        "idp_rotulo": idp_rotulo,
        "duracao_planejada": duracao_base,
        "duracao_real": duracao_real,
        "aderencia_fisica": aderencia,
        "situacao_fisica": situacao_fisica,
        "situacao_fisica_rotulo": situacao_fisica_rotulo,
        "executado": executado,
        "previsto": previsto,
    }
