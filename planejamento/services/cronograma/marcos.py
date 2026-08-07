from .consultas import decimal_para_float, formatar_data, queryset_ativo


TOLERANCIA_PERCENTUAL = 0.001
LIMITE_CONCLUSAO = 1.0 - TOLERANCIA_PERCENTUAL


def obter_marcos(*, projeto, semana):
    registros = list(
        queryset_ativo(projeto=projeto, semana=semana)
        .filter(disciplina__iexact="MARCOS")
        .values(
            "id",
            "local_tarefa",
            "nome_tarefa",
            "responsavel",
            "inicio_base",
            "termino_base",
            "inicio_real",
            "termino_real",
            "data_atualizacao",
            "percentual_concluida",
            "percentual_previsto_tarefa",
            "percentual_executado",
            "percentual_previsto",
        )
        .order_by("termino_base", "id")
    )

    marcos = []

    for registro in registros:
        valor_concluido = registro.get("percentual_concluida")
        if valor_concluido is None:
            valor_concluido = registro.get("percentual_executado")
        realizado = decimal_para_float(valor_concluido)

        valor_previsto = registro.get("percentual_previsto_tarefa")
        if valor_previsto is None:
            valor_previsto = registro.get("percentual_previsto")
        previsto = decimal_para_float(valor_previsto)

        termino_base = registro.get("termino_base")
        termino_real = registro.get("termino_real")
        data_atualizacao = registro.get("data_atualizacao")

        concluido = realizado >= LIMITE_CONCLUSAO
        atrasado = bool(
            not concluido
            and termino_base
            and data_atualizacao
            and termino_base < data_atualizacao
        )
        concluido_com_atraso = bool(
            concluido
            and termino_base
            and termino_real
            and termino_real > termino_base
        )

        if concluido:
            situacao = "CONCLUIDO"
            rotulo = (
                "Concluído com atraso"
                if concluido_com_atraso
                else "Concluído"
            )
        elif atrasado:
            situacao = "ATRASADO"
            rotulo = "Atrasado"
        else:
            situacao = "PLANEJADO"
            rotulo = "Planejado"

        variacao_dias = None
        if termino_base and termino_real:
            variacao_dias = (termino_real - termino_base).days

        marcos.append({
            "id": registro["id"],
            "nome": (
                registro.get("nome_tarefa")
                or registro.get("local_tarefa")
                or "Marco sem descrição"
            ).strip(),
            "local": (registro.get("local_tarefa") or "-").strip(),
            "responsavel": (
                registro.get("responsavel") or "-"
            ).strip(),
            "planejado": previsto,
            "realizado": realizado,
            "situacao": situacao,
            "situacao_rotulo": rotulo,
            "concluido": concluido,
            "concluido_com_atraso": concluido_com_atraso,
            "atrasado": atrasado,
            "inicio_base": formatar_data(registro.get("inicio_base")),
            "termino_base": formatar_data(termino_base),
            "inicio_real": formatar_data(registro.get("inicio_real")),
            "termino_real": formatar_data(termino_real),
            "variacao_dias": variacao_dias,
        })

    return marcos
