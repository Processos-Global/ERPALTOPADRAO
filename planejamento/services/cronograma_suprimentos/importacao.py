from __future__ import annotations

import io
import re
import traceback
from dataclasses import dataclass

import pandas as pd
from django.db import transaction
from django.utils import timezone

from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra,
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)

from .configuracoes import obter_configuracao_cronograma_suprimentos
from .google_drive import obter_dados_planilha
from .normalizacao import (
    converter_data,
    converter_inteiro,
    localizar_obra_por_aba,
    normalizar_texto,
    texto_limpo,
)


CAMPOS_DATAS_REALIZADAS = (
    "data_real_cotacao",
    "data_real_compatibilizacao",
    "data_real_negociacao",
    "data_real_contratacao",
)


def _chave_item_manual(*, obra_id, item, local, linha_origem=None):
    base = (
        int(obra_id),
        normalizar_texto(item),
        normalizar_texto(local),
    )
    if linha_origem is None:
        return base
    return (*base, int(linha_origem or 0))


def _carregar_ajustes_manuais_ativos():
    exatos = {}
    fallback = {}
    qs = (
        ItemCronogramaSuprimento.objects
        .filter(
            cronograma_obra__importacao__ativa=True,
            cronograma_obra__importacao__status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
            datas_editadas_manualmente=True,
        )
        .select_related("cronograma_obra")
        .order_by("cronograma_obra_id", "ordem", "id")
    )

    for item in qs:
        dados = {campo: getattr(item, campo) for campo in CAMPOS_DATAS_REALIZADAS}
        dados.update(
            {
                "datas_editadas_manualmente": True,
                "datas_editadas_por_id": item.datas_editadas_por_id,
                "datas_editadas_em": item.datas_editadas_em,
            }
        )
        chave_exata = _chave_item_manual(
            obra_id=item.cronograma_obra.obra_id,
            item=item.item,
            local=item.local,
            linha_origem=item.linha_origem,
        )
        exatos[chave_exata] = dados

        chave_base = _chave_item_manual(
            obra_id=item.cronograma_obra.obra_id,
            item=item.item,
            local=item.local,
        )
        fallback.setdefault(chave_base, []).append(dados)

    return exatos, fallback


def _aplicar_ajustes_manuais(itens, *, obra_id, exatos, fallback):
    usados_fallback = {}
    for dados_item in itens:
        chave_exata = _chave_item_manual(
            obra_id=obra_id,
            item=dados_item.get("item"),
            local=dados_item.get("local"),
            linha_origem=dados_item.get("linha_origem"),
        )
        ajuste = exatos.get(chave_exata)

        if ajuste is None:
            chave_base = _chave_item_manual(
                obra_id=obra_id,
                item=dados_item.get("item"),
                local=dados_item.get("local"),
            )
            candidatos = fallback.get(chave_base, [])
            indice = usados_fallback.get(chave_base, 0)
            if indice < len(candidatos):
                ajuste = candidatos[indice]
                usados_fallback[chave_base] = indice + 1

        if ajuste:
            dados_item.update(ajuste)



class ImportacaoCronogramaSuprimentosError(Exception):
    pass


@dataclass
class ResultadoImportacaoCronogramaSuprimentos:
    importado: bool
    importacao: ImportacaoCronogramaSuprimentos | None
    mensagem: str


def _deve_ignorar_aba(nome_aba: str, prefixos: tuple[str, ...]) -> bool:
    texto = normalizar_texto(nome_aba)
    return any(texto.startswith(normalizar_texto(prefixo)) for prefixo in prefixos)


def _detectar_inicio_obra(df: pd.DataFrame):
    # Suporta "INÍCIO OBRA", "DATA DE INÍCIO" e versões semelhantes.
    marcadores = ("INICIO OBRA", "DATA DE INICIO DA OBRA", "DATA INICIO OBRA")
    for linha in range(min(len(df), 20)):
        for coluna in range(df.shape[1]):
            valor = normalizar_texto(df.iat[linha, coluna])
            if any(m in valor for m in marcadores):
                # Procura primeiro ao lado e abaixo, porque há abas com células mescladas.
                candidatos = [
                    (linha, coluna + 1),
                    (linha + 1, coluna),
                    (linha + 1, coluna + 1),
                ]
                for l, c in candidatos:
                    if l < len(df) and c < df.shape[1]:
                        data = converter_data(df.iat[l, c])
                        if data:
                            return data

    # Em algumas versões a linha "OBRA:" traz a data de início na terceira célula útil.
    for linha in range(min(len(df), 10)):
        valores = [df.iat[linha, c] for c in range(df.shape[1])]
        normalizados = [normalizar_texto(v) for v in valores]
        if any(v.startswith("OBRA") for v in normalizados):
            for valor in valores:
                data = converter_data(valor)
                if data:
                    return data
    return None


def _linha_util(df: pd.DataFrame, linha: int) -> list[str]:
    return [normalizar_texto(v) for v in df.iloc[linha].tolist()]


def _localizar_linha_cabecalho(df: pd.DataFrame) -> int:
    """Aceita o layout atual e o layout legado das casas antigas."""
    limite = min(len(df), 80)

    for linha in range(limite):
        valores = _linha_util(df, linha)
        validos = [v for v in valores if v and v not in {"NAN", "NONE", "NAT"}]

        tem_item = any(v == "ITEM" or v.startswith("ITEM ") for v in validos)
        tem_local = any(v == "LOCAL" or v.startswith("LOCAL ") for v in validos)
        tem_contratacao = any("CONTRATAC" in v for v in validos)
        tem_cotacao_ou_orcamento = any(
            "COTACAO" in v or "INICIO DE ORCAMENTO" in v or "INICIO DO ORCAMENTO" in v
            for v in validos
        )

        # Layout novo e legado têm ITEM + LOCAL e pelo menos uma data de fluxo.
        if tem_item and tem_local and (tem_contratacao or tem_cotacao_ou_orcamento):
            return linha

    amostra = []
    for linha in range(min(limite, 15)):
        valores = [v for v in _linha_util(df, linha) if v and v not in {"NAN", "NONE", "NAT"}]
        if valores:
            amostra.append(f"linha {linha + 1}: {' | '.join(valores[:10])}")

    detalhe = "; ".join(amostra[:7]) or "nenhuma linha com conteúdo detectada"
    raise ImportacaoCronogramaSuprimentosError(
        "Não foi possível localizar o cabeçalho do cronograma de suprimentos. "
        f"Amostra da aba: {detalhe}"
    )


def _indice_primeiro(cabecalhos: list[str], *termos: str, excluir: tuple[str, ...] = ()):
    for i, cab in enumerate(cabecalhos):
        if not cab:
            continue
        if all(termo in cab for termo in termos) and not any(x in cab for x in excluir):
            return i
    return None


def _montar_mapa_colunas(df: pd.DataFrame, linha_cabecalho: int) -> dict:
    cab = _linha_util(df, linha_cabecalho)

    idx_item = _indice_primeiro(cab, "ITEM")
    idx_local = _indice_primeiro(cab, "LOCAL")
    if idx_item is None or idx_local is None:
        raise ImportacaoCronogramaSuprimentosError(
            "O cabeçalho foi localizado, mas as colunas ITEM/LOCAL não puderam ser mapeadas."
        )

    idx_situacao = _indice_primeiro(cab, "SITUACAO")
    if idx_situacao is None:
        # Layout legado: a primeira coluna é um checkbox (✓/TRUE/FALSE).
        idx_situacao = 0

    idx_cotacao = _indice_primeiro(cab, "COTACAO")
    if idx_cotacao is None:
        idx_cotacao = _indice_primeiro(cab, "INICIO", "ORCAMENTO")

    idx_compat = _indice_primeiro(cab, "COMPATIBIL")
    idx_negociacao = _indice_primeiro(cab, "NEGOCIAC")
    idx_prazo = _indice_primeiro(cab, "LIMITE", "CONTRATAC")
    idx_real = _indice_primeiro(cab, "REAL", "CONTRATAC")
    idx_contratada = _indice_primeiro(cab, "CONTRATADA")
    if idx_contratada is None:
        idx_contratada = _indice_primeiro(cab, "RESPONSAVEL")
    idx_dias = _indice_primeiro(cab, "DIAS", "INICIO")
    idx_mes = _indice_primeiro(cab, "MES")

    def duracao_apos(indice_data):
        if indice_data is None:
            return None
        prox = indice_data + 1
        if prox < len(cab) and "DURACAO" in cab[prox]:
            return prox
        # Também aceita cabeçalho explícito do tipo DURAÇÃO COTAÇÃO.
        fase = cab[indice_data]
        for i, nome in enumerate(cab):
            if "DURACAO" not in nome:
                continue
            if "COTACAO" in fase and "COTACAO" in nome:
                return i
            if "COMPATIBIL" in fase and "COMPATIBIL" in nome:
                return i
            if "NEGOCIAC" in fase and "NEGOCIAC" in nome:
                return i
        return None

    layout = "LEGADO" if idx_real is not None or any("INICIO" in x and "ORCAMENTO" in x for x in cab) else "ATUAL"

    return {
        "layout": layout,
        "situacao": idx_situacao,
        "data_cotacao": idx_cotacao,
        "duracao_cotacao": duracao_apos(idx_cotacao),
        "data_compatibilizacao": idx_compat,
        "duracao_compatibilizacao": duracao_apos(idx_compat),
        "data_negociacao": idx_negociacao,
        "duracao_negociacao": duracao_apos(idx_negociacao),
        "prazo_limite_contratacao": idx_prazo,
        "data_real_contratacao": idx_real,
        "item": idx_item,
        "local": idx_local,
        "contratada_responsavel": idx_contratada,
        "dias_apos_inicio": idx_dias,
        "mes_referencia": idx_mes,
    }


def _valor(row, indice):
    if indice is None or indice < 0 or indice >= len(row):
        return None
    return row.iloc[indice]


def _situacao_item(valor, *, layout: str, data_real=None) -> str:
    texto = texto_limpo(valor)
    normalizado = normalizar_texto(texto)

    if layout == "LEGADO":
        verdadeiros = {"TRUE", "VERDADEIRO", "SIM", "1", "X", "✓", "OK"}
        falsos = {"FALSE", "FALSO", "NAO", "0", ""}
        if normalizado in verdadeiros or data_real:
            return "CONTRATADO"
        if normalizado in falsos:
            return "PENDENTE"

    return texto


def _ler_aba(df: pd.DataFrame, *, nome_aba: str = "") -> tuple[object, list[dict]]:
    inicio_obra = _detectar_inicio_obra(df)
    try:
        cabecalho = _localizar_linha_cabecalho(df)
        colunas = _montar_mapa_colunas(df, cabecalho)
    except ImportacaoCronogramaSuprimentosError as exc:
        prefixo = f"Aba '{nome_aba}': " if nome_aba else ""
        raise ImportacaoCronogramaSuprimentosError(prefixo + str(exc)) from exc

    categoria_atual = ""
    itens: list[dict] = []
    ordem = 0

    for idx in range(cabecalho + 1, len(df)):
        row = df.iloc[idx]
        item = texto_limpo(_valor(row, colunas["item"]))
        situacao_bruta = _valor(row, colunas["situacao"])

        # Linhas de categoria normalmente têm texto apenas na primeira coluna e ITEM vazio.
        if not item:
            primeira = texto_limpo(row.iloc[0] if len(row) else "")
            primeira_norm = normalizar_texto(primeira)
            if primeira and primeira_norm not in {"TRUE", "FALSE", "VERDADEIRO", "FALSO", "✓"}:
                categoria_atual = primeira
            continue

        data_real = converter_data(_valor(row, colunas["data_real_contratacao"]))
        situacao = _situacao_item(
            situacao_bruta,
            layout=colunas["layout"],
            data_real=data_real,
        )

        ordem += 1
        itens.append(
            {
                "categoria": categoria_atual,
                "situacao": situacao,
                "data_cotacao": converter_data(_valor(row, colunas["data_cotacao"])),
                "duracao_cotacao": converter_inteiro(_valor(row, colunas["duracao_cotacao"])),
                "data_compatibilizacao": converter_data(_valor(row, colunas["data_compatibilizacao"])),
                "duracao_compatibilizacao": converter_inteiro(_valor(row, colunas["duracao_compatibilizacao"])),
                "data_negociacao": converter_data(_valor(row, colunas["data_negociacao"])),
                "duracao_negociacao": converter_inteiro(_valor(row, colunas["duracao_negociacao"])),
                "prazo_limite_contratacao": converter_data(_valor(row, colunas["prazo_limite_contratacao"])),
                "data_real_contratacao": data_real,
                "item": item,
                "local": texto_limpo(_valor(row, colunas["local"])),
                "contratada_responsavel": texto_limpo(_valor(row, colunas["contratada_responsavel"])),
                "dias_apos_inicio": converter_inteiro(_valor(row, colunas["dias_apos_inicio"])),
                "mes_referencia": texto_limpo(_valor(row, colunas["mes_referencia"])),
                "linha_origem": idx + 1,
                "ordem": ordem,
            }
        )

    if not itens:
        raise ImportacaoCronogramaSuprimentosError(
            f"A aba '{nome_aba}' não possui itens válidos após o cabeçalho."
        )

    return inicio_obra, itens


def importar_cronograma_suprimentos(*, usuario=None, forcar: bool = False):
    config = obter_configuracao_cronograma_suprimentos()
    ajustes_manuais_exatos, ajustes_manuais_fallback = _carregar_ajustes_manuais_ativos()

    try:
        dados = obter_dados_planilha(
            file_id=config.get("file_id", ""),
            folder_id=config.get("folder_id", ""),
        )
    except Exception as exc:
        raise ImportacaoCronogramaSuprimentosError(str(exc)) from exc

    existente = (
        ImportacaoCronogramaSuprimentos.objects
        .filter(
            hash_arquivo=dados["hash_arquivo"],
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
            ativa=True,
        )
        .first()
    )
    if existente and not forcar:
        return ResultadoImportacaoCronogramaSuprimentos(
            importado=False,
            importacao=existente,
            mensagem="A planilha de suprimentos mais recente já está importada.",
        )

    importacao = ImportacaoCronogramaSuprimentos.objects.create(
        status=ImportacaoCronogramaSuprimentos.Status.PROCESSANDO,
        ativa=False,
        nome_arquivo=dados["nome_arquivo"],
        arquivo_drive_id=dados["arquivo_drive_id"],
        mime_type=dados["mime_type"],
        data_modificacao_drive=dados["data_modificacao_drive"],
        hash_arquivo=dados["hash_arquivo"],
        tamanho_arquivo_bytes=dados["tamanho_arquivo_bytes"],
        executado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        iniciou_em=timezone.now(),
    )

    try:
        workbook = pd.ExcelFile(io.BytesIO(dados["conteudo"]), engine="openpyxl")
        nomes_abas = workbook.sheet_names
        prefixos_ignorados = tuple(config.get("ignorar_prefixos_abas", ()))
        abas_ignoradas_config = {
            normalizar_texto(nome)
            for nome in config.get("ignorar_abas", ())
        }

        abas_preparadas = []
        abas_ignoradas = 0
        obras_usadas = set()
        total_itens = 0

        # Primeiro valida todas as abas; só depois troca a base ativa.
        for ordem_aba, nome_aba in enumerate(nomes_abas, start=1):
            if normalizar_texto(nome_aba) in abas_ignoradas_config:
                abas_ignoradas += 1
                continue

            if _deve_ignorar_aba(nome_aba, prefixos_ignorados):
                abas_ignoradas += 1
                continue

            try:
                obra, codigo_aba = localizar_obra_por_aba(nome_aba)
            except ValueError:
                if len(re.findall(r"\d+", nome_aba)) >= 3:
                    raise
                abas_ignoradas += 1
                continue

            if obra.pk in obras_usadas:
                raise ImportacaoCronogramaSuprimentosError(
                    f"Mais de uma aba está vinculando a mesma obra '{obra}'. "
                    f"Verifique a aba '{nome_aba}'."
                )
            obras_usadas.add(obra.pk)

            df = pd.read_excel(
                workbook,
                sheet_name=nome_aba,
                header=None,
                dtype=object,
            )
            inicio_obra, itens = _ler_aba(df, nome_aba=nome_aba)
            _aplicar_ajustes_manuais(
                itens,
                obra_id=obra.pk,
                exatos=ajustes_manuais_exatos,
                fallback=ajustes_manuais_fallback,
            )
            total_itens += len(itens)
            abas_preparadas.append(
                {
                    "ordem_aba": ordem_aba,
                    "nome_aba": nome_aba,
                    "obra": obra,
                    "codigo_aba": codigo_aba,
                    "data_inicio_obra": inicio_obra,
                    "itens": itens,
                }
            )

        if not abas_preparadas:
            raise ImportacaoCronogramaSuprimentosError(
                "Nenhuma aba de obra válida foi encontrada na planilha."
            )

        with transaction.atomic():
            for aba in abas_preparadas:
                cronograma_obra = CronogramaSuprimentosObra.objects.create(
                    importacao=importacao,
                    obra=aba["obra"],
                    nome_aba=aba["nome_aba"],
                    codigo_aba=aba["codigo_aba"],
                    data_inicio_obra=aba["data_inicio_obra"],
                    quantidade_itens=len(aba["itens"]),
                    ordem_aba=aba["ordem_aba"],
                )
                ItemCronogramaSuprimento.objects.bulk_create(
                    [
                        ItemCronogramaSuprimento(
                            cronograma_obra=cronograma_obra,
                            **item,
                        )
                        for item in aba["itens"]
                    ],
                    batch_size=1000,
                )

            ImportacaoCronogramaSuprimentos.objects.filter(ativa=True).exclude(
                pk=importacao.pk
            ).update(ativa=False)

            importacao.status = ImportacaoCronogramaSuprimentos.Status.CONCLUIDA
            importacao.ativa = True
            importacao.total_abas_arquivo = len(nomes_abas)
            importacao.abas_importadas = len(abas_preparadas)
            importacao.abas_ignoradas = abas_ignoradas
            importacao.total_itens_importados = total_itens
            importacao.finalizou_em = timezone.now()
            importacao.mensagem = (
                f"{len(abas_preparadas)} obra(s) e {total_itens} item(ns) "
                "importados com sucesso."
            )
            importacao.save()

        return ResultadoImportacaoCronogramaSuprimentos(
            importado=True,
            importacao=importacao,
            mensagem=importacao.mensagem,
        )

    except Exception as exc:
        importacao.status = ImportacaoCronogramaSuprimentos.Status.FALHOU
        importacao.ativa = False
        importacao.finalizou_em = timezone.now()
        importacao.mensagem = str(exc)
        importacao.erro_detalhado = traceback.format_exc()
        importacao.save(
            update_fields=[
                "status",
                "ativa",
                "finalizou_em",
                "mensagem",
                "erro_detalhado",
                "atualizado_em",
            ]
        )
        raise ImportacaoCronogramaSuprimentosError(str(exc)) from exc