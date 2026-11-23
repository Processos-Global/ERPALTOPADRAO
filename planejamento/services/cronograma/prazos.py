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


def calcular_indicadores_prazo(*, resumo, media_avanco_real, avancos=None):
    executado = max(float(resumo.get("executado") or 0.0), 0.0)
    previsto = max(float(resumo.get("previsto") or 0.0), 0.0)
    restante = max(float(resumo.get("restante") or 0.0), 0.0)
    duracao_base = max(float(resumo.get("duracao_base") or 0.0), 0.0)
    duracao_real = max(float(resumo.get("duracao_real") or 0.0), 0.0)

    termino_planejado = resumo.get("termino_base")
    termino_real_informado = resumo.get("termino_real")
    data_atualizacao = resumo.get("data_atualizacao")
    # A importação pode preencher TERMINO_REAL mesmo com avanço incompleto.
    # Uma data em uma linha RESUMO GERAL não comprova conclusão da obra.
    obra_concluida = executado >= 1.0 - TOLERANCIA_PERCENTUAL
    termino_real = termino_real_informado if obra_concluida else None
    termino_real_inconsistente = bool(termino_real_informado and not obra_concluida)

    semanas_restantes = None
    previsao_termino = None

    amostras = list(avancos or [])[1:][-4:]
    ganhos_positivos = sum(1 for item in amostras if item.get("avanco_real", 0) > 0)
    projecao_confiavel = (
        ganhos_positivos >= 2
        and media_avanco_real > 0 and bool(data_atualizacao)
        and not obra_concluida and restante > TOLERANCIA_PERCENTUAL
    )
    if projecao_confiavel:
        semanas_restantes = restante / media_avanco_real
        try:
            previsao_termino = data_atualizacao + timedelta(days=round(semanas_restantes * 7))
        except OverflowError:
            projecao_confiavel = False
            semanas_restantes = None

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
        "termino_real_informado": termino_real_informado,
        "termino_real_inconsistente": termino_real_inconsistente,
        "obra_concluida": obra_concluida,
        "previsao_termino": previsao_termino,
        "projecao_confiavel": projecao_confiavel,
        "criterio_projecao": "Avanço médio das últimas quatro semanas, com ao menos três medições e dois avanços positivos",
        "data_base_projecao": data_atualizacao,
        "dias_diferenca_projetada": (
            (previsao_termino - termino_planejado).days
            if previsao_termino and termino_planejado else None
        ),
        "dias_diferenca_real": (
            (termino_real - termino_planejado).days
            if termino_real and termino_planejado else None
        ),
        "dias_atraso_aberto": (
            max((data_atualizacao - termino_planejado).days, 0)
            if not termino_real and data_atualizacao and termino_planejado else None
        ),
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
