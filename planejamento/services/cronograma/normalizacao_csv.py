import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import pandas as pd

from .configuracoes import obter_configuracao_cronograma


class CronogramaCsvError(Exception):
    """Erro de leitura, estrutura ou normalização do CSV."""


COLUNAS_MAPEADAS = {
    "NOME_DO_PROJETO": "projeto",
    "PREDIO_OU_CASA": "tipo",
    "QUANTIDADE_DE_UNIDADES": "quantidade_unidades",
    "SEMANA": "semana",
    "DATA_DE_ATUALIZACAO": "data_atualizacao",
    "LOCAL_DA_TAREFA": "local_tarefa",
    "NOME_DA_TAREFA": "nome_tarefa",
    "INICIO_REAL": "inicio_real",
    "DURACAO_REAL": "duracao_real",
    "TERMINO_REAL": "termino_real",
    "INICIO_BASE": "inicio_base",
    "DURACAO_BASE": "duracao_base",
    "TERMINO_BASE": "termino_base",
    "PERCENT_CONCLUIDA": "percentual_concluida",
    "PERCENT_PREV_TAREFA": "percentual_previsto_tarefa",
    "DISCIPLINA": "disciplina",
    "CHECKLIST_HABITE_SE": "checklist_habitese",
    "CHECKLIST_HABITESE": "checklist_habitese",
    "CHECKLIST_CEF": "checklist_cef",
    "RESPONSAVEL": "responsavel",
    "PESOS": "peso",
    "PESO": "peso",
    "PERCENT_EXECUTADO": "percentual_executado",
    "PERCENT_PREVISTO": "percentual_previsto",
    "INICIO_SEMANA": "inicio_semana",
    "SEMANA_ANTERIOR1": "semana_anterior",
    "SEMANA_SEGUINTE1": "semana_seguinte",
    "INICIO_SEMANA_BASE": "inicio_semana_base",
}

COLUNAS_OBRIGATORIAS = {
    "projeto",
    "semana",
    "data_atualizacao",
    "disciplina",
    "percentual_executado",
    "percentual_previsto",
}

COLUNAS_TEXTO = (
    "projeto",
    "tipo",
    "local_tarefa",
    "nome_tarefa",
    "disciplina",
    "checklist_habitese",
    "checklist_cef",
    "responsavel",
    "semana_anterior",
    "semana_seguinte",
)

COLUNAS_DATA = (
    "data_atualizacao",
    "inicio_real",
    "termino_real",
    "inicio_base",
    "termino_base",
    "inicio_semana",
    "inicio_semana_base",
)

COLUNAS_DECIMAIS = (
    "duracao_real",
    "duracao_base",
    "percentual_concluida",
    "percentual_previsto_tarefa",
    "peso",
    "percentual_executado",
    "percentual_previsto",
)


def normalizar_cabecalho(valor) -> str:
    if valor is None:
        return ""

    texto = str(valor).strip().upper()
    texto = texto.replace("%", "PERCENT_")
    texto = texto.replace("\u00a0", " ")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto)
    return texto.strip("_")


def limpar_texto(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def converter_decimal(valor, percentual=False):
    if valor is None or pd.isna(valor):
        return None

    texto = limpar_texto(valor)
    if not texto:
        return None

    texto = texto.replace("%", "").replace("R$", "").replace(" ", "")
    if not texto:
        return None

    try:
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")

        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None

    if percentual and numero > 1:
        numero /= Decimal("100")

    return numero


def converter_inteiro(valor):
    decimal = converter_decimal(valor)
    if decimal is None:
        return None
    try:
        return int(decimal)
    except (ValueError, TypeError):
        return None


PADRAO_UNIDADES_NOME_ARQUIVO = re.compile(
    r"(?<!\d)(\d{1,6}(?:[\.,]\d{3})*)\s*(?:UNIDADES?|UN|UH)\b",
    flags=re.IGNORECASE,
)


def extrair_quantidade_unidades_nome_arquivo(nome_arquivo):
    nome = limpar_texto(nome_arquivo)
    if not nome:
        return None

    correspondencias = PADRAO_UNIDADES_NOME_ARQUIVO.findall(nome)
    if not correspondencias:
        return None

    try:
        quantidade = int(
            correspondencias[-1].replace(".", "").replace(",", "")
        )
    except (TypeError, ValueError):
        return None

    return quantidade if quantidade > 0 else None


def converter_data(serie, dayfirst=True):
    if serie is None:
        return None

    valores = serie.apply(limpar_texto)
    convertido = pd.to_datetime(
        valores,
        errors="coerce",
        dayfirst=dayfirst,
        format="mixed",
    )
    return convertido.apply(
        lambda valor: None if pd.isna(valor) else valor.date()
    )


def _detectar_encoding(conteudo: bytes, separador: str) -> str:
    ultimo_erro = None

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            pd.read_csv(
                io.BytesIO(conteudo),
                sep=separador,
                encoding=encoding,
                nrows=5,
                dtype=str,
                keep_default_na=False,
            )
            return encoding
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            ultimo_erro = exc

    raise CronogramaCsvError(
        "Não foi possível identificar a codificação ou ler o CSV. "
        f"Detalhes: {ultimo_erro}"
    )


def _renomear_colunas(dataframe):
    renomear = {}

    for coluna_original in dataframe.columns:
        coluna_normalizada = normalizar_cabecalho(coluna_original)
        campo_destino = COLUNAS_MAPEADAS.get(coluna_normalizada)
        if campo_destino:
            renomear[coluna_original] = campo_destino

    dataframe = dataframe.rename(columns=renomear)

    repetidas = dataframe.columns[dataframe.columns.duplicated()].tolist()
    if repetidas:
        raise CronogramaCsvError(
            "Colunas duplicadas após a normalização: "
            f"{', '.join(repetidas)}."
        )

    return dataframe


def validar_colunas_dataframe(dataframe):
    ausentes = COLUNAS_OBRIGATORIAS - set(dataframe.columns)
    if ausentes:
        raise CronogramaCsvError(
            "O CSV não possui as colunas obrigatórias: "
            f"{', '.join(sorted(ausentes))}."
        )


def normalizar_bloco_cronograma(dataframe, nome_arquivo=""):
    configuracao = obter_configuracao_cronograma()
    dataframe = _renomear_colunas(dataframe)
    validar_colunas_dataframe(dataframe)

    for coluna in COLUNAS_TEXTO:
        if coluna not in dataframe.columns:
            dataframe[coluna] = ""
        else:
            dataframe[coluna] = dataframe[coluna].apply(limpar_texto)

    for coluna in COLUNAS_DATA:
        if coluna not in dataframe.columns:
            dataframe[coluna] = None
        else:
            dataframe[coluna] = converter_data(
                dataframe[coluna],
                dayfirst=configuracao["dayfirst"],
            )

    for coluna in COLUNAS_DECIMAIS:
        if coluna not in dataframe.columns:
            dataframe[coluna] = None
            continue

        percentual = coluna in {
            "percentual_concluida",
            "percentual_previsto_tarefa",
            "percentual_executado",
            "percentual_previsto",
        }
        dataframe[coluna] = dataframe[coluna].apply(
            lambda valor: converter_decimal(valor, percentual=percentual)
        )

    for coluna in ("quantidade_unidades", "semana"):
        if coluna not in dataframe.columns:
            dataframe[coluna] = None
        else:
            dataframe[coluna] = dataframe[coluna].apply(converter_inteiro)

    quantidade_nome = extrair_quantidade_unidades_nome_arquivo(nome_arquivo)
    if quantidade_nome:
        dataframe["quantidade_unidades"] = dataframe[
            "quantidade_unidades"
        ].apply(lambda valor: valor or quantidade_nome)

    colunas_destino = [
        "projeto",
        "tipo",
        "quantidade_unidades",
        "semana",
        "data_atualizacao",
        "local_tarefa",
        "nome_tarefa",
        "inicio_real",
        "duracao_real",
        "termino_real",
        "inicio_base",
        "duracao_base",
        "termino_base",
        "percentual_concluida",
        "percentual_previsto_tarefa",
        "disciplina",
        "checklist_habitese",
        "checklist_cef",
        "responsavel",
        "peso",
        "percentual_executado",
        "percentual_previsto",
        "inicio_semana",
        "semana_anterior",
        "semana_seguinte",
        "inicio_semana_base",
    ]

    for coluna in colunas_destino:
        if coluna not in dataframe.columns:
            dataframe[coluna] = None

    return dataframe[colunas_destino].copy()


def iterar_blocos_cronograma(
    conteudo: bytes,
    tamanho_bloco=5000,
    nome_arquivo="",
):
    if not conteudo:
        raise CronogramaCsvError("O arquivo CSV foi baixado vazio.")

    configuracao = obter_configuracao_cronograma()
    separador = configuracao["separador"]
    encoding = _detectar_encoding(conteudo, separador)

    try:
        leitor = pd.read_csv(
            io.BytesIO(conteudo),
            sep=separador,
            encoding=encoding,
            dtype=str,
            keep_default_na=False,
            chunksize=tamanho_bloco,
            low_memory=False,
        )

        encontrou_linhas = False

        for numero_bloco, dataframe in enumerate(leitor, start=1):
            encontrou_linhas = True
            try:
                yield normalizar_bloco_cronograma(
                    dataframe=dataframe,
                    nome_arquivo=nome_arquivo,
                )
            except CronogramaCsvError as exc:
                raise CronogramaCsvError(
                    f"Erro no bloco {numero_bloco}: {exc}"
                ) from exc

        if not encontrou_linhas:
            raise CronogramaCsvError("O arquivo não possui linhas de dados.")

    except pd.errors.ParserError as exc:
        raise CronogramaCsvError(
            "Não foi possível interpretar o CSV. "
            "Verifique o separador e as colunas. "
            f"Detalhes: {exc}"
        ) from exc
