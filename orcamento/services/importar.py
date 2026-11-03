from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd
from django.db import transaction
from django.utils import timezone

from orcamento.models import ArquivoOrcamentoObra, ImportacaoOrcamento, InsumoOrcamento
from orcamento.services.configuracoes import obter_configuracao_orcamento
from orcamento.services.google_drive import (
    GoogleDriveOrcamentoError,
    baixar_planilha_como_xlsx,
    calcular_hash_arquivo,
    listar_planilhas_pasta,
)
from orcamento.services.normalizacao import (
    cabecalho_parece_valido,
    campos_obrigatorios_faltantes,
    detectar_estrutura_eap,
    eh_mao_de_obra,
    localizar_aba_orcamento,
    normalizar_cabecalho,
    parsear_valor,
)
from orcamento.services.obras import resolver_ou_criar_obra
from planejamento.services.cronograma.vinculos import listar_obras_por_nome_normalizado


class ImportacaoOrcamentoError(Exception):
    """Erro controlado ao atualizar o orçamento a partir do Google Drive."""


@dataclass
class ResultadoImportacaoOrcamento:
    importacao: ImportacaoOrcamento
    erros_por_arquivo: list[str] = field(default_factory=list)


def _nome_obra_do_arquivo(nome_arquivo: str) -> str:
    nome = str(nome_arquivo or "").strip()
    if nome.lower().endswith(".xlsx"):
        nome = nome[: -len(".xlsx")]
    return nome.strip()


def _linha_util(valores: list) -> list[str]:
    return ["" if pd.isna(valor) else str(valor).strip() for valor in valores]


def _localizar_linha_cabecalho(linhas: list[list[str]]) -> int:
    """Retorna o índice (0 ou 1) da linha de cabeçalho real da aba."""
    if linhas and cabecalho_parece_valido(linhas[0]):
        return 0
    if len(linhas) > 1 and cabecalho_parece_valido(linhas[1]):
        return 1
    return -1


def _processar_conteudo_planilha(conteudo: bytes) -> tuple[list[dict], int | None, int]:
    """
    Faz o parse da aba "00 - Orçamento" da planilha de uma obra e devolve
    os payloads das linhas, a estrutura EAP detectada e a quantidade de
    linhas ignoradas.
    """
    workbook = pd.ExcelFile(io.BytesIO(conteudo), engine="openpyxl")

    nome_aba = localizar_aba_orcamento(workbook.sheet_names)
    if nome_aba is None:
        raise ImportacaoOrcamentoError(
            "A planilha não possui a aba \"00 - Orçamento\"."
        )

    df = pd.read_excel(workbook, sheet_name=nome_aba, header=None, dtype=object)
    linhas = [_linha_util(linha) for linha in df.itertuples(index=False, name=None)]

    indice_cabecalho = _localizar_linha_cabecalho(linhas)
    if indice_cabecalho == -1:
        cabecalho_candidato = linhas[0] if linhas else []
        faltantes = campos_obrigatorios_faltantes(cabecalho_candidato)
        raise ImportacaoOrcamentoError(
            "Aba \"00 - Orçamento\" fora do padrão. Títulos obrigatórios ausentes: "
            + ", ".join(faltantes or ["TIPO", "CODIGO", "DESC"])
        )

    cabecalho = linhas[indice_cabecalho]
    campos_por_coluna = [normalizar_cabecalho(nome) for nome in cabecalho]

    linhas_dados = linhas[indice_cabecalho + 1:]

    payloads = []
    estrutura_detectada = None
    linhas_ignoradas = 0

    for linha in linhas_dados:
        if not any(str(valor).strip() for valor in linha):
            linhas_ignoradas += 1
            continue

        payload = {}
        for valor_bruto, campo in zip(linha, campos_por_coluna):
            if not campo:
                continue
            payload[campo] = parsear_valor(campo, valor_bruto)

        codigo = str(payload.get("codigo") or "").strip()
        tipo = str(payload.get("tipo") or "").strip().upper()

        if not codigo or not tipo:
            linhas_ignoradas += 1
            continue

        if estrutura_detectada is None:
            estrutura_detectada = detectar_estrutura_eap(codigo)

        descricao = str(payload.get("descricao") or "").strip()

        payloads.append(
            {
                "nr": str(payload.get("nr") or "").strip(),
                "tipo": tipo[:1],
                "codigo": codigo,
                "alternativo": str(payload.get("alternativo") or "").strip(),
                "codigo_ins": str(payload.get("codigo_ins") or "").strip(),
                "svc_in_mega": str(payload.get("svc_in_mega") or "").strip(),
                "descricao": descricao,
                "unid": str(payload.get("unid") or "").strip(),
                "quant": payload.get("quant"),
                "custo": payload.get("custo"),
                "total": payload.get("total"),
                "data_custo": payload.get("data_custo"),
                "pro_in_mega": str(payload.get("pro_in_mega") or "").strip(),
                "imp": payload.get("imp"),
                "encbdi": payload.get("encbdi"),
                "encsociais": payload.get("encsociais"),
                "descricao_grupo": str(payload.get("descricao_grupo") or "").strip(),
                "natureza": str(payload.get("natureza") or "").strip(),
                "classe_financeira": str(payload.get("classe_financeira") or "").strip(),
                "classe_gerencial": str(payload.get("classe_gerencial") or "").strip(),
                "classe_macro": str(payload.get("classe_macro") or "").strip(),
                "mao_de_obra": eh_mao_de_obra(descricao),
            }
        )

    if not payloads:
        raise ImportacaoOrcamentoError(
            "Nenhuma linha válida (com TIPO e CODIGO) foi encontrada na aba "
            "\"00 - Orçamento\"."
        )

    return payloads, estrutura_detectada, linhas_ignoradas


@transaction.atomic
def _importar_arquivo_da_obra(obra, conteudo: bytes, *, nome_arquivo: str, arquivo_drive_id: str, hash_arquivo: str):
    payloads, estrutura_detectada, _linhas_ignoradas = _processar_conteudo_planilha(conteudo)

    InsumoOrcamento.objects.filter(obra=obra).delete()

    InsumoOrcamento.objects.bulk_create(
        [InsumoOrcamento(obra=obra, **payload) for payload in payloads],
        batch_size=1000,
    )

    if estrutura_detectada and obra.estrutura_eap != estrutura_detectada:
        obra.estrutura_eap = estrutura_detectada
        obra.save(update_fields=["estrutura_eap"])

    ArquivoOrcamentoObra.objects.update_or_create(
        obra=obra,
        defaults={
            "nome_arquivo": nome_arquivo,
            "arquivo_drive_id": arquivo_drive_id,
            "hash_arquivo": hash_arquivo,
            "estrutura_eap_detectada": estrutura_detectada,
            "quantidade_itens": len(payloads),
        },
    )

    return len(payloads)


def atualizar_orcamento(*, executado_por=None, forcar: bool = False) -> ResultadoImportacaoOrcamento:
    configuracao = obter_configuracao_orcamento()

    try:
        arquivos = listar_planilhas_pasta(configuracao["folder_id"])
    except GoogleDriveOrcamentoError as exc:
        raise ImportacaoOrcamentoError(str(exc)) from exc

    if not arquivos:
        raise ImportacaoOrcamentoError(
            "Nenhuma planilha foi encontrada na pasta de orçamento configurada."
        )

    importacao = ImportacaoOrcamento.objects.create(
        status=ImportacaoOrcamento.Status.PROCESSANDO,
        executado_por=executado_por if getattr(executado_por, "is_authenticated", False) else None,
        iniciou_em=timezone.now(),
    )

    indice_obras = listar_obras_por_nome_normalizado()
    hashes_existentes = {
        arquivo.obra_id: arquivo.hash_arquivo
        for arquivo in ArquivoOrcamentoObra.objects.all()
    }

    obras_criadas = 0
    obras_atualizadas = 0
    obras_ignoradas = 0
    total_itens = 0
    erros_por_arquivo: list[str] = []

    for arquivo in arquivos:
        nome_arquivo = arquivo.get("name", "")
        nome_obra = _nome_obra_do_arquivo(nome_arquivo)

        if not nome_obra:
            erros_por_arquivo.append(f"Arquivo sem nome válido ignorado: {nome_arquivo!r}")
            continue

        try:
            obra, criada = resolver_ou_criar_obra(
                nome_obra,
                programa_padrao=configuracao["programa_padrao"],
                indice_obras=indice_obras,
            )

            conteudo = baixar_planilha_como_xlsx(arquivo["id"], arquivo.get("mimeType", ""))
            hash_arquivo = calcular_hash_arquivo(conteudo)

            if not forcar and not criada and hashes_existentes.get(obra.pk) == hash_arquivo:
                obras_ignoradas += 1
                continue

            quantidade_itens = _importar_arquivo_da_obra(
                obra,
                conteudo,
                nome_arquivo=nome_arquivo,
                arquivo_drive_id=arquivo.get("id", ""),
                hash_arquivo=hash_arquivo,
            )

            total_itens += quantidade_itens
            if criada:
                obras_criadas += 1
            else:
                obras_atualizadas += 1

        except (GoogleDriveOrcamentoError, ImportacaoOrcamentoError) as exc:
            erros_por_arquivo.append(f"{nome_arquivo}: {exc}")
        except Exception as exc:  # noqa: BLE001 - erro de um arquivo não pode travar os demais
            erros_por_arquivo.append(f"{nome_arquivo}: erro inesperado - {exc}")

    mensagem = (
        f"{obras_criadas} obra(s) criada(s), {obras_atualizadas} atualizada(s), "
        f"{obras_ignoradas} sem alteração e {total_itens} item(ns) importados no total."
    )

    if erros_por_arquivo:
        mensagem += f" {len(erros_por_arquivo)} arquivo(s) com erro."

    importacao.status = (
        ImportacaoOrcamento.Status.CONCLUIDA
        if (obras_criadas or obras_atualizadas or obras_ignoradas)
        else ImportacaoOrcamento.Status.FALHOU
    )
    importacao.obras_criadas = obras_criadas
    importacao.obras_atualizadas = obras_atualizadas
    importacao.obras_ignoradas = obras_ignoradas
    importacao.total_itens_importados = total_itens
    importacao.mensagem = mensagem
    importacao.erro_detalhado = "\n".join(erros_por_arquivo)
    importacao.finalizou_em = timezone.now()
    importacao.save(
        update_fields=[
            "status",
            "obras_criadas",
            "obras_atualizadas",
            "obras_ignoradas",
            "total_itens_importados",
            "mensagem",
            "erro_detalhado",
            "finalizou_em",
        ]
    )

    return ResultadoImportacaoOrcamento(
        importacao=importacao,
        erros_por_arquivo=erros_por_arquivo,
    )
