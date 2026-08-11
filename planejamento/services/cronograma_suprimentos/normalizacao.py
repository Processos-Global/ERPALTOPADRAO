from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from django.apps import apps


class VinculoAbaObraError(ValueError):
    pass


def normalizar_texto(valor) -> str:
    texto = str(valor or "").strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto).strip()


def extrair_codigo_aba(nome_aba: str) -> tuple[int, int, int] | None:
    texto = normalizar_texto(nome_aba)
    numeros = re.findall(r"\d+", texto)
    if len(numeros) < 3:
        return None

    # Os cronogramas usam os três primeiros blocos como quadra/conjunto/casa.
    return tuple(int(n) for n in numeros[:3])


def formatar_codigo_aba(codigo: tuple[int, int, int]) -> str:
    return "-".join(f"{n:02d}" for n in codigo)


def _codigo_obra_por_texto(valor) -> tuple[int, int, int] | None:
    texto = normalizar_texto(valor)
    if not texto:
        return None

    # Dá preferência ao padrão semântico QI/QL + CJ + CASA.
    padrao = re.search(
        r"\b(?:QI|QL)\s*0*(\d+)\b.*?\bCJ\s*0*(\d+)\b.*?\bCASA\s*0*(\d+)\b",
        texto,
    )
    if padrao:
        return tuple(int(x) for x in padrao.groups())

    numeros = re.findall(r"\d+", texto)
    if len(numeros) >= 3:
        return tuple(int(n) for n in numeros[:3])
    return None


def localizar_obra_por_aba(nome_aba: str):
    codigo = extrair_codigo_aba(nome_aba)
    if not codigo:
        raise VinculoAbaObraError(
            f"Não foi possível extrair o código da aba '{nome_aba}'."
        )

    Obra = apps.get_model("obras", "Obra")
    campos = {campo.name for campo in Obra._meta.fields}
    campos_texto = [
        nome for nome in ("nome", "codigo", "nome_curto")
        if nome in campos
    ]

    candidatas = []
    for obra in Obra.objects.all().iterator():
        codigos = {
            _codigo_obra_por_texto(getattr(obra, campo, ""))
            for campo in campos_texto
        }
        if codigo in codigos:
            candidatas.append(obra)

    if not candidatas:
        raise VinculoAbaObraError(
            f"A aba '{nome_aba}' ({formatar_codigo_aba(codigo)}) não encontrou "
            "uma obra correspondente no cadastro."
        )

    if len(candidatas) > 1:
        nomes = ", ".join(str(obra) for obra in candidatas[:5])
        raise VinculoAbaObraError(
            f"A aba '{nome_aba}' encontrou mais de uma obra para o código "
            f"{formatar_codigo_aba(codigo)}: {nomes}."
        )

    return candidatas[0], formatar_codigo_aba(codigo)


def converter_data(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "nat", "none"}:
        return None

    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    return None


def converter_inteiro(valor):
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def texto_limpo(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() in {"nan", "nat", "none"} else texto
