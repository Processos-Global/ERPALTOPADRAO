from __future__ import annotations

import re
import unicodedata

from obras.models import Obra
from planejamento.services.cronograma.vinculos import normalizar_nome_obra


def _gerar_codigo_a_partir_do_nome(nome: str) -> str:
    texto = unicodedata.normalize("NFKD", nome)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-").upper()

    codigo_base = texto[:50] or "OBRA"
    codigo = codigo_base
    sufixo = 1

    while Obra.objects.filter(codigo=codigo).exists():
        sufixo += 1
        codigo = f"{codigo_base}-{sufixo}"

    return codigo


def resolver_ou_criar_obra(
    nome_arquivo: str,
    *,
    programa_padrao: str,
    indice_obras: dict,
) -> tuple[Obra, bool]:
    """
    Localiza a obra pelo nome do arquivo (sem extensão).

    Se não existir nenhuma obra com esse nome, cria uma nova com o
    programa padrão configurado, retornando (obra, criada).
    """
    nome = str(nome_arquivo or "").strip()
    chave = normalizar_nome_obra(nome)

    obra = indice_obras.get(chave)
    if obra is not None:
        return obra, False

    obra = Obra.objects.create(
        nome=nome,
        codigo=_gerar_codigo_a_partir_do_nome(nome),
        programa=programa_padrao,
    )

    indice_obras[chave] = obra
    return obra, True
