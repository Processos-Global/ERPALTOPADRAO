from __future__ import annotations

import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Iterator

from planejamento.models import ImportacaoCronograma, RegistroCronograma


DISCIPLINAS_ESTRUTURAIS = {"RESUMO GERAL", "RESUMO", "MARCOS"}

# A importação ativa é reutilizada apenas dentro do contexto atual.
# ContextVar é seguro para requisições concorrentes e não cria cache global
# permanente entre atualizações da base.
_IMPORTACAO_ATIVA_CONTEXTO: ContextVar[ImportacaoCronograma | None] = (
    ContextVar(
        "planejamento_importacao_cronograma_ativa",
        default=None,
    )
)


class CronogramaBaseError(Exception):
    """Erro controlado da camada de consultas do cronograma."""


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""

    texto = str(valor).replace("\u00a0", " ").strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return " ".join(texto.split()).upper()


def decimal_para_float(
    valor: Decimal | float | int | None,
) -> float:
    if valor is None:
        return 0.0

    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def formatar_data(valor):
    return valor.strftime("%d/%m/%Y") if valor else None


def eh_linha_estrutural(disciplina):
    return (
        normalizar_texto(disciplina)
        in DISCIPLINAS_ESTRUTURAIS
    )


def obter_importacao_ativa() -> ImportacaoCronograma:
    """
    Obtém a importação ativa do cronograma.

    Quando o painel abre um contexto com usar_importacao_ativa(), todas
    as chamadas subsequentes reutilizam o mesmo objeto sem executar
    novamente SELECT em ImportacaoCronograma.

    Fora desse contexto, o comportamento continua exatamente como antes:
    consulta a base e retorna a importação ativa mais recente.
    """
    importacao_contextual = _IMPORTACAO_ATIVA_CONTEXTO.get()

    if importacao_contextual is not None:
        return importacao_contextual

    importacao = (
        ImportacaoCronograma.objects
        .filter(
            ativa=True,
            status=ImportacaoCronograma.Status.CONCLUIDA,
        )
        .order_by("-id")
        .first()
    )

    if importacao is None:
        raise CronogramaBaseError(
            "Ainda não existe uma importação ativa do cronograma."
        )

    return importacao


@contextmanager
def usar_importacao_ativa(
    importacao: ImportacaoCronograma | None = None,
) -> Iterator[ImportacaoCronograma]:
    """
    Reutiliza a mesma importação durante uma operação composta.

    O valor é restaurado ao sair do bloco, inclusive quando ocorre erro.
    Isso evita cache global e impede que uma nova requisição reutilize
    uma importação que deixou de ser ativa.
    """
    if importacao is None:
        importacao = obter_importacao_ativa()

    token = _IMPORTACAO_ATIVA_CONTEXTO.set(importacao)

    try:
        yield importacao
    finally:
        _IMPORTACAO_ATIVA_CONTEXTO.reset(token)


def queryset_ativo(
    *,
    projeto=None,
    semana=None,
    obra=None,
    obra_id=None,
):
    queryset = RegistroCronograma.objects.filter(
        importacao=obter_importacao_ativa()
    )

    if obra is not None:
        queryset = queryset.filter(obra=obra)
    elif obra_id is not None:
        queryset = queryset.filter(obra_id=obra_id)

    if projeto:
        queryset = queryset.filter(projeto=projeto)

    if semana is not None:
        queryset = queryset.filter(semana=semana)

    return queryset


def listar_projetos_ativos():
    return list(
        queryset_ativo()
        .exclude(projeto__isnull=True)
        .exclude(projeto__exact="")
        .order_by("projeto")
        .values_list("projeto", flat=True)
        .distinct()
    )


def listar_semanas_ativas(*, projeto):
    return list(
        queryset_ativo(projeto=projeto)
        .exclude(semana__isnull=True)
        .order_by("semana")
        .values_list("semana", flat=True)
        .distinct()
    )


def listar_semanas_com_resumo_geral(*, projeto):
    return list(
        queryset_ativo(projeto=projeto)
        .filter(disciplina__iexact="RESUMO GERAL")
        .exclude(semana__isnull=True)
        .order_by("semana")
        .values_list("semana", flat=True)
        .distinct()
    )


def obter_ultima_semana_valida(
    *,
    projeto,
    ate_semana=None,
):
    semanas = listar_semanas_com_resumo_geral(
        projeto=projeto
    )

    if ate_semana is not None:
        semanas = [
            semana
            for semana in semanas
            if semana <= ate_semana
        ]

    return semanas[-1] if semanas else None


def listar_responsaveis_ativos(*, projeto=None):
    return list(
        queryset_ativo(projeto=projeto)
        .exclude(responsavel__exact="")
        .order_by("responsavel")
        .values_list("responsavel", flat=True)
        .distinct()
    )
