from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation


CAMPOS_OBRIGATORIOS_CABECALHO = {
    "tipo": "TIPO",
    "codigo": "CODIGO",
    "descricao": "DESC",
}

ALIAS_CABECALHO = {
    "nr": "nr",

    "tipo": "tipo",

    "codigo": "codigo",
    "cod": "codigo",
    "codigo_eap": "codigo",

    "alternativo": "alternativo",
    "codigo_alternativo": "alternativo",

    "codigo_ins": "codigo_ins",
    "codigo_insumo": "codigo_ins",
    "cod_ins": "codigo_ins",

    "svc_in_mega": "svc_in_mega",

    "desc": "descricao",
    "descricao": "descricao",

    "unid": "unid",
    "unidade": "unid",

    "quant": "quant",
    "quantidade": "quant",
    "qtd": "quant",

    "custo": "custo",

    "total": "total",

    "datacusto": "data_custo",
    "data_custo": "data_custo",

    "pro_in_mega": "pro_in_mega",

    "imp": "imp",
    "encbdi": "encbdi",
    "encsociais": "encsociais",

    "descricao_do_grupo": "descricao_grupo",
    "descricao_grupo": "descricao_grupo",

    "natureza": "natureza",

    "classe_financeira": "classe_financeira",
    "classe_gerencial": "classe_gerencial",
    "classe_gerenical": "classe_gerencial",
    "classe_macro": "classe_macro",
}

CAMPOS_TEXTO = {
    "nr",
    "tipo",
    "codigo",
    "alternativo",
    "codigo_ins",
    "svc_in_mega",
    "descricao",
    "unid",
    "pro_in_mega",
    "descricao_grupo",
    "natureza",
    "classe_financeira",
    "classe_gerencial",
    "classe_macro",
}

CAMPOS_DECIMAL = {"quant", "custo", "total", "imp", "encbdi", "encsociais"}

CAMPOS_DATA = {"data_custo"}


def normalizar_cabecalho(nome_coluna: str) -> str:
    if not nome_coluna:
        return ""

    texto = str(nome_coluna).strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"[\s\-\.]+", "_", texto).strip("_")

    return ALIAS_CABECALHO.get(texto, texto)


def cabecalho_parece_valido(linha: list[str]) -> bool:
    campos = {normalizar_cabecalho(valor) for valor in linha}
    return all(campo in campos for campo in CAMPOS_OBRIGATORIOS_CABECALHO)


def campos_obrigatorios_faltantes(linha: list[str]) -> list[str]:
    campos = {normalizar_cabecalho(valor) for valor in linha}
    return [
        nome_exibicao
        for campo, nome_exibicao in CAMPOS_OBRIGATORIOS_CABECALHO.items()
        if campo not in campos
    ]


def parsear_valor(campo: str, valor_bruto) -> object:
    if valor_bruto is None:
        return None

    valor = str(valor_bruto).strip()
    if not valor:
        return None

    if campo in CAMPOS_DECIMAL:
        try:
            valor = valor.replace("R$", "").replace(" ", "")
            if "," in valor:
                valor = valor.replace(".", "").replace(",", ".")
            return Decimal(valor)
        except (InvalidOperation, ValueError):
            return None

    if campo in CAMPOS_DATA:
        for formato in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(valor, formato).date()
            except ValueError:
                continue
        return None

    return valor


def detectar_estrutura_eap(codigo: str) -> int | None:
    """
    Conta os segmentos separados por ponto do primeiro CODIGO encontrado.

    01.01.001.0001       -> 4 níveis
    01.01.001.0001.00001 -> 5 níveis
    """
    codigo = str(codigo or "").strip()
    if not codigo:
        return None

    segmentos = [parte for parte in codigo.split(".") if parte != ""]
    quantidade = len(segmentos)

    if quantidade in (4, 5):
        return quantidade

    return None


NOME_ABA_ORCAMENTO = "00 - ORCAMENTO"


def _normalizar_nome_aba(nome_aba: str) -> str:
    texto = str(nome_aba or "").strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", texto)


def localizar_aba_orcamento(nomes_abas: list[str]) -> str | None:
    """Encontra a aba '00 - Orçamento' entre as abas da planilha da obra."""
    for nome_aba in nomes_abas:
        if _normalizar_nome_aba(nome_aba) == NOME_ABA_ORCAMENTO:
            return nome_aba
    return None


def eh_mao_de_obra(descricao: str) -> bool:
    """
    Por ora, mão de obra é identificada apenas pela descrição começar com "M.O".
    """
    texto = str(descricao or "").strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return texto.startswith("M.O") or texto.startswith("M O") or texto.startswith("MO ")
