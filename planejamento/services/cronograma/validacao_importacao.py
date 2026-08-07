from __future__ import annotations

from collections import defaultdict

from planejamento.models import ImportacaoCronograma, RegistroCronograma


class ValidacaoImportacaoError(Exception):
    """Erro impeditivo encontrado durante a validação da importação."""


def obter_inconsistencias_resumo_geral(
    importacao: ImportacaoCronograma,
) -> dict[str, list[int]]:
    """
    Identifica projeto/semana que possuem registros de cronograma,
    mas não possuem uma linha RESUMO GERAL.

    A ausência de RESUMO GERAL é tratada como inconsistência da base,
    e não como erro fatal de importação. Isso permite preservar os
    demais dados válidos e deixar o painel utilizar somente semanas
    que possuam resumo global.
    """

    pares_existentes = set(
        RegistroCronograma.objects
        .filter(importacao=importacao)
        .exclude(projeto="")
        .exclude(semana__isnull=True)
        .values_list("projeto", "semana")
        .distinct()
    )

    pares_com_resumo = set(
        RegistroCronograma.objects
        .filter(
            importacao=importacao,
            disciplina__iexact="RESUMO GERAL",
        )
        .exclude(projeto="")
        .exclude(semana__isnull=True)
        .values_list("projeto", "semana")
        .distinct()
    )

    faltantes = pares_existentes - pares_com_resumo

    resultado: dict[str, list[int]] = defaultdict(list)

    for projeto, semana in faltantes:
        if projeto and semana is not None:
            resultado[str(projeto)].append(int(semana))

    return {
        projeto: sorted(set(semanas))
        for projeto, semanas in sorted(resultado.items())
    }


def validar_resumo_geral_por_projeto_semana(
    importacao: ImportacaoCronograma,
) -> dict[str, list[int]]:
    """
    Valida a presença do RESUMO GERAL.

    IMPORTANTE:
    A ausência de RESUMO GERAL em uma determinada semana não invalida
    toda a importação. O método retorna as inconsistências encontradas
    para que sejam registradas como alerta.

    Erros realmente estruturais continuam sendo tratados pelo
    importador principal.
    """

    return obter_inconsistencias_resumo_geral(importacao)


def formatar_alertas_resumo_geral(
    inconsistencias: dict[str, list[int]],
) -> str:
    if not inconsistencias:
        return ""

    detalhes = []

    for projeto, semanas in inconsistencias.items():
        texto_semanas = ", ".join(str(semana) for semana in semanas)

        detalhes.append(
            f"{projeto}: semanas {texto_semanas}"
        )

    return (
        "Atenção: existem projeto/semana sem linha RESUMO GERAL. "
        + " | ".join(detalhes)
    )