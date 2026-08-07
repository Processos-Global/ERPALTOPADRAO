from __future__ import annotations

import unicodedata
from typing import Any

from django.apps import apps


class VinculoObraError(Exception):
    """Erro controlado ao relacionar projeto do CSV com obras.Obra."""


CAMPOS_NOME_OBRA_PREFERIDOS = (
    "nome",
    "nome_obra",
    "descricao",
    "titulo",
    "empreendimento",
)


def normalizar_nome_obra(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).replace("\u00a0", " ").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.split())


def _obter_model_obra():
    return apps.get_model("obras", "Obra")


def _campos_textuais_candidatos(modelo) -> list[str]:
    nomes = {campo.name for campo in modelo._meta.get_fields() if hasattr(campo, "attname")}
    preferidos = [campo for campo in CAMPOS_NOME_OBRA_PREFERIDOS if campo in nomes]

    # Além dos nomes preferidos, indexamos os demais campos textuais (por
    # exemplo código/sigla) sem duplicá-los. Isso aumenta a chance de casar o
    # identificador usado no CSV sem assumir a estrutura exata de obras.Obra.
    outros = []
    for campo in modelo._meta.concrete_fields:
        internal_type = campo.get_internal_type()
        if internal_type in {"CharField", "TextField"} and campo.name not in preferidos:
            outros.append(campo.name)
    return preferidos + outros


def listar_obras_por_nome_normalizado() -> dict[str, Any]:
    """
    Monta um índice das obras oficiais por nome normalizado.

    Se duas obras diferentes produzirem exatamente o mesmo nome normalizado,
    esse nome é considerado ambíguo e não é usado automaticamente.
    """
    Obra = _obter_model_obra()
    campos = _campos_textuais_candidatos(Obra)
    if not campos:
        raise VinculoObraError(
            "Não foi encontrado campo textual utilizável em obras.Obra para "
            "relacionar o nome do projeto do cronograma."
        )

    indice: dict[str, Any] = {}
    ambiguos: set[str] = set()

    for obra in Obra.objects.all().iterator(chunk_size=1000):
        for campo in campos:
            valor = getattr(obra, campo, None)
            chave = normalizar_nome_obra(valor)
            if not chave:
                continue

            existente = indice.get(chave)
            if existente is None:
                indice[chave] = obra
            elif existente.pk != obra.pk:
                ambiguos.add(chave)

    for chave in ambiguos:
        indice.pop(chave, None)

    return indice


def resolver_obra_por_projeto(
    projeto: str,
    *,
    indice: dict[str, Any] | None = None,
):
    chave = normalizar_nome_obra(projeto)
    if not chave:
        raise VinculoObraError("O registro do cronograma possui projeto vazio.")

    indice = indice if indice is not None else listar_obras_por_nome_normalizado()
    obra = indice.get(chave)
    if obra is None:
        raise VinculoObraError(
            f'Não foi possível vincular o projeto "{projeto}" a uma obra oficial '
            "do ERP. Confira se o nome do projeto no CSV corresponde ao nome "
            "cadastrado em obras.Obra."
        )
    return obra
