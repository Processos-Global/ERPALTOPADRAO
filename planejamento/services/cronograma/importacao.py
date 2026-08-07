from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import transaction
from django.utils import timezone

from planejamento.models import (
    AtividadePlanejamento,
    ImportacaoCronograma,
    RegistroCronograma,
)

from .configuracoes import obter_configuracao_cronograma
from .consultas import eh_linha_estrutural
from .google_drive import (
    GoogleDriveCronogramaError,
    obter_dados_csv_mais_recente,
)
from .normalizacao_csv import (
    CronogramaCsvError,
    iterar_blocos_cronograma,
)
from .validacao_importacao import (
    formatar_alertas_resumo_geral,
    validar_resumo_geral_por_projeto_semana,
)
from .vinculos import (
    VinculoObraError,
    listar_obras_por_nome_normalizado,
    resolver_obra_por_projeto,
)


class ImportacaoCronogramaError(Exception):
    """Erro controlado da importação do cronograma."""


@dataclass
class ResultadoImportacao:
    importacao: ImportacaoCronograma | None
    importado: bool
    mensagem: str


TAMANHO_BLOCO_LEITURA = 5_000
TAMANHO_LOTE_BANCO = 2_000


def _normalizar_parte_chave(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    texto = texto.replace("\u00a0", " ").strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"\s+", " ", texto)


def _gerar_chave_base_atividade(
    *,
    obra_id: Any,
    disciplina: Any,
    local_tarefa: Any,
    nome_tarefa: Any,
) -> str:
    """
    Chave do grupo lógico da atividade.

    Ela NÃO é necessariamente única porque o CSV pode conter várias
    ocorrências com o mesmo projeto/obra, disciplina, local e nome.
    """
    partes = (
        _normalizar_parte_chave(obra_id),
        _normalizar_parte_chave(disciplina),
        _normalizar_parte_chave(local_tarefa),
        _normalizar_parte_chave(nome_tarefa),
    )
    texto = "||".join(partes)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gerar_chave_atividade(
    *,
    obra_id: Any,
    disciplina: Any,
    local_tarefa: Any,
    nome_tarefa: Any,
    ocorrencia: int = 1,
) -> str:
    """
    Gera a identidade permanente da ocorrência da atividade.

    O CSV não possui um ID nativo para diferenciar linhas repetidas.
    Por isso, além de obra + disciplina + local + nome, usamos a posição
    ordinal da ocorrência dentro do mesmo grupo e da mesma semana.

    A semana NÃO entra no hash final. Ela serve apenas para calcular a
    ordem da ocorrência em cada snapshot semanal. Assim, a ocorrência 1
    da semana 10 continua sendo a mesma identidade da ocorrência 1 da
    semana 11, desde que a ordem das linhas do cronograma seja preservada.

    Datas, percentuais, responsável e peso não entram na chave porque
    podem mudar ao longo do tempo.
    """
    partes = (
        _normalizar_parte_chave(obra_id),
        _normalizar_parte_chave(disciplina),
        _normalizar_parte_chave(local_tarefa),
        _normalizar_parte_chave(nome_tarefa),
        _normalizar_parte_chave(ocorrencia),
    )
    texto = "||".join(partes)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _obter_importacao_ativa_anterior():
    return (
        ImportacaoCronograma.objects
        .filter(
            ativa=True,
            status=ImportacaoCronograma.Status.CONCLUIDA,
        )
        .order_by("-id")
        .first()
    )


def _resolver_obra_cache(
    projeto: str,
    *,
    indice_obras,
    cache_obras,
):
    chave = _normalizar_parte_chave(projeto)

    if chave in cache_obras:
        return cache_obras[chave]

    obra = resolver_obra_por_projeto(
        projeto,
        indice=indice_obras,
    )

    cache_obras[chave] = obra
    return obra


def _montar_mapa_datas_anteriores(
    importacao_anterior: ImportacaoCronograma | None,
    *,
    indice_obras,
    cache_obras,
) -> dict[
    tuple[str, int | None],
    tuple[date | None, date | None],
]:
    """
    Reconstrói as identidades da base anterior a partir da ordem original
    dos registros, sem confiar na chave antiga salva no banco.

    Isso é necessário porque versões anteriores da aplicação usavam uma
    chave que não diferenciava ocorrências duplicadas.

    A comparação de reprogramação é feita por:
        (identidade permanente da ocorrência, semana)
    """
    if importacao_anterior is None:
        return {}

    mapa: dict[
        tuple[str, int | None],
        tuple[date | None, date | None],
    ] = {}

    contadores: dict[
        tuple[str, int | None],
        int,
    ] = defaultdict(int)

    queryset = (
        RegistroCronograma.objects
        .filter(importacao=importacao_anterior)
        .values(
            "obra_id",
            "projeto",
            "semana",
            "disciplina",
            "local_tarefa",
            "nome_tarefa",
            "inicio_base",
            "termino_base",
        )
        .order_by("id")
        .iterator(chunk_size=5_000)
    )

    for registro in queryset:
        disciplina = registro.get("disciplina") or ""
        nome_tarefa = registro.get("nome_tarefa") or ""

        if eh_linha_estrutural(disciplina) or not str(nome_tarefa).strip():
            continue

        obra_id = registro.get("obra_id")

        if not obra_id:
            try:
                obra = _resolver_obra_cache(
                    registro.get("projeto") or "",
                    indice_obras=indice_obras,
                    cache_obras=cache_obras,
                )
            except VinculoObraError:
                # Base histórica antiga sem vínculo não deve impedir
                # uma nova importação válida.
                continue

            obra_id = obra.pk

        chave_base = _gerar_chave_base_atividade(
            obra_id=obra_id,
            disciplina=disciplina,
            local_tarefa=registro.get("local_tarefa"),
            nome_tarefa=nome_tarefa,
        )

        semana = registro.get("semana")
        chave_contador = (chave_base, semana)
        contadores[chave_contador] += 1
        ocorrencia = contadores[chave_contador]

        chave_atividade = gerar_chave_atividade(
            obra_id=obra_id,
            disciplina=disciplina,
            local_tarefa=registro.get("local_tarefa"),
            nome_tarefa=nome_tarefa,
            ocorrencia=ocorrencia,
        )

        chave_snapshot = (
            chave_atividade,
            semana,
        )

        mapa[chave_snapshot] = (
            registro.get("inicio_base"),
            registro.get("termino_base"),
        )

    return mapa


def _criar_importacao(
    dados_arquivo: dict,
    executado_por=None,
):
    return ImportacaoCronograma.objects.create(
        status=ImportacaoCronograma.Status.PROCESSANDO,
        ativa=False,
        nome_arquivo=dados_arquivo.get("nome_arquivo", ""),
        arquivo_drive_id=dados_arquivo.get("arquivo_drive_id", ""),
        data_modificacao_drive=dados_arquivo.get(
            "data_modificacao_drive"
        ),
        hash_arquivo=dados_arquivo.get("hash_arquivo", ""),
        tamanho_arquivo_bytes=dados_arquivo.get(
            "tamanho_arquivo_bytes",
            0,
        ),
        iniciou_em=timezone.now(),
        executado_por=executado_por,
        mensagem="Arquivo localizado no Drive. Iniciando leitura.",
    )


def _arquivo_ja_ativo(hash_arquivo: str) -> bool:
    if not hash_arquivo:
        return False

    return ImportacaoCronograma.objects.filter(
        ativa=True,
        status=ImportacaoCronograma.Status.CONCLUIDA,
        hash_arquivo=hash_arquivo,
    ).exists()


def _datas_foram_reprogramadas(
    *,
    datas_anteriores: tuple[date | None, date | None] | None,
    inicio_base_novo: date | None,
    termino_base_novo: date | None,
) -> bool:
    if datas_anteriores is None:
        return False

    inicio_anterior, termino_anterior = datas_anteriores

    return (
        inicio_anterior != inicio_base_novo
        or termino_anterior != termino_base_novo
    )


def _preparar_atividades_planejamento(
    linhas: list[dict[str, Any]],
    *,
    indice_obras,
    cache_obras,
    contadores_ocorrencia,
):
    """
    Resolve as obras, calcula a ocorrência ordinal de cada linha e garante
    as identidades permanentes necessárias ao bloco atual.

    contadores_ocorrencia é compartilhado entre todos os blocos da mesma
    importação para preservar a ordem mesmo quando um grupo cruza a fronteira
    entre chunks.
    """
    metadados_por_chave: dict[str, dict[str, Any]] = {}

    for linha in linhas:
        projeto = (linha.get("projeto") or "").strip()

        obra = _resolver_obra_cache(
            projeto,
            indice_obras=indice_obras,
            cache_obras=cache_obras,
        )

        # Dados internos usados apenas durante esta importação.
        linha["__obra"] = obra
        linha["__chave_atividade"] = ""
        linha["__ocorrencia"] = None

        disciplina = linha.get("disciplina") or ""
        nome_tarefa = linha.get("nome_tarefa") or ""

        if (
            eh_linha_estrutural(disciplina)
            or not str(nome_tarefa).strip()
        ):
            continue

        chave_base = _gerar_chave_base_atividade(
            obra_id=obra.pk,
            disciplina=disciplina,
            local_tarefa=linha.get("local_tarefa"),
            nome_tarefa=nome_tarefa,
        )

        semana = linha.get("semana")
        chave_contador = (chave_base, semana)
        contadores_ocorrencia[chave_contador] += 1
        ocorrencia = contadores_ocorrencia[chave_contador]

        chave = gerar_chave_atividade(
            obra_id=obra.pk,
            disciplina=disciplina,
            local_tarefa=linha.get("local_tarefa"),
            nome_tarefa=nome_tarefa,
            ocorrencia=ocorrencia,
        )

        linha["__chave_atividade"] = chave
        linha["__ocorrencia"] = ocorrencia

        metadados_por_chave.setdefault(
            chave,
            {
                "chave": chave,
                "obra": obra,
                "projeto_origem": projeto,
                "disciplina": disciplina,
                "local_tarefa": linha.get("local_tarefa") or "",
                "nome_tarefa": nome_tarefa,
            },
        )

    chaves = list(metadados_por_chave)

    if not chaves:
        return {}

    existentes = {
        atividade.chave: atividade
        for atividade in AtividadePlanejamento.objects.filter(
            chave__in=chaves
        )
    }

    novos = [
        AtividadePlanejamento(**dados)
        for chave, dados in metadados_por_chave.items()
        if chave not in existentes
    ]

    if novos:
        AtividadePlanejamento.objects.bulk_create(
            novos,
            batch_size=TAMANHO_LOTE_BANCO,
            ignore_conflicts=True,
        )

    return {
        atividade.chave: atividade
        for atividade in AtividadePlanejamento.objects.filter(
            chave__in=chaves
        )
    }


def _criar_registros_modelo(
    dataframe,
    importacao: ImportacaoCronograma,
    mapa_datas_anteriores: dict[
        tuple[str, int | None],
        tuple[date | None, date | None],
    ],
    momento_reprogramacao,
    *,
    indice_obras,
    cache_obras,
    contadores_ocorrencia,
):
    linhas = dataframe.to_dict(orient="records")

    atividades_por_chave = _preparar_atividades_planejamento(
        linhas,
        indice_obras=indice_obras,
        cache_obras=cache_obras,
        contadores_ocorrencia=contadores_ocorrencia,
    )

    objetos = []

    for linha in linhas:
        projeto = (linha.get("projeto") or "").strip()
        obra = linha["__obra"]
        disciplina = linha.get("disciplina") or ""
        nome_tarefa = linha.get("nome_tarefa") or ""

        chave = linha.get("__chave_atividade") or ""
        atividade_planejamento = None

        if chave:
            atividade_planejamento = atividades_por_chave.get(
                chave
            )

            if atividade_planejamento is None:
                raise ImportacaoCronogramaError(
                    "Não foi possível criar a identidade permanente "
                    f"da atividade: {nome_tarefa}."
                )

        chave_snapshot = (
            chave,
            linha.get("semana"),
        )

        datas_anteriores = (
            mapa_datas_anteriores.get(chave_snapshot)
            if chave
            else None
        )

        inicio_anterior = (
            datas_anteriores[0]
            if datas_anteriores
            else None
        )

        termino_anterior = (
            datas_anteriores[1]
            if datas_anteriores
            else None
        )

        reprogramada = bool(chave) and _datas_foram_reprogramadas(
            datas_anteriores=datas_anteriores,
            inicio_base_novo=linha.get("inicio_base"),
            termino_base_novo=linha.get("termino_base"),
        )

        objetos.append(
            RegistroCronograma(
                importacao=importacao,
                obra=obra,
                atividade_planejamento=atividade_planejamento,
                projeto=projeto,
                tipo=linha.get("tipo", ""),
                quantidade_unidades=linha.get(
                    "quantidade_unidades"
                ),
                semana=linha.get("semana"),
                data_atualizacao=linha.get(
                    "data_atualizacao"
                ),
                local_tarefa=linha.get(
                    "local_tarefa",
                    "",
                ),
                nome_tarefa=nome_tarefa,
                inicio_real=linha.get("inicio_real"),
                duracao_real=linha.get("duracao_real"),
                termino_real=linha.get("termino_real"),
                inicio_base=linha.get("inicio_base"),
                duracao_base=linha.get("duracao_base"),
                termino_base=linha.get("termino_base"),
                percentual_concluida=linha.get(
                    "percentual_concluida"
                ),
                percentual_previsto_tarefa=linha.get(
                    "percentual_previsto_tarefa"
                ),
                disciplina=disciplina,
                checklist_habitese=linha.get(
                    "checklist_habitese",
                    "",
                ),
                checklist_cef=linha.get(
                    "checklist_cef",
                    "",
                ),
                responsavel=linha.get(
                    "responsavel",
                    "",
                ),
                peso=linha.get("peso"),
                percentual_executado=linha.get(
                    "percentual_executado"
                ),
                percentual_previsto=linha.get(
                    "percentual_previsto"
                ),
                inicio_semana=linha.get(
                    "inicio_semana"
                ),
                semana_anterior=linha.get(
                    "semana_anterior",
                    "",
                ),
                semana_seguinte=linha.get(
                    "semana_seguinte",
                    "",
                ),
                inicio_semana_base=linha.get(
                    "inicio_semana_base"
                ),
                chave_atividade=chave,
                inicio_base_anterior=(
                    inicio_anterior
                    if reprogramada
                    else None
                ),
                termino_base_anterior=(
                    termino_anterior
                    if reprogramada
                    else None
                ),
                reprogramada=reprogramada,
                reprogramada_em=(
                    momento_reprogramacao
                    if reprogramada
                    else None
                ),
            )
        )

    return objetos


def _obter_resumo_importacao(
    importacao: ImportacaoCronograma,
) -> dict[str, Any]:
    registros = RegistroCronograma.objects.filter(
        importacao=importacao
    )

    return {
        "linhas_importadas": registros.count(),
        "projetos_identificados": (
            registros
            .exclude(projeto="")
            .values("projeto")
            .distinct()
            .count()
        ),
        "semanas_identificadas": (
            registros
            .exclude(semana__isnull=True)
            .values("semana")
            .distinct()
            .count()
        ),
        "possui_resumo_geral": registros.filter(
            disciplina__iexact="RESUMO GERAL"
        ).exists(),
        "registros_sem_obra": registros.filter(
            obra__isnull=True
        ).count(),
    }


def _validar_importacao_final(
    importacao: ImportacaoCronograma,
) -> tuple[
    dict[str, Any],
    dict[str, list[int]],
]:
    """
    Executa as validações finais.

    Falhas estruturais continuam bloqueando a importação.

    Ausência de RESUMO GERAL em uma semana específica é registrada
    como inconsistência/alerta e não cancela toda a nova base.
    """
    resumo = _obter_resumo_importacao(importacao)

    if resumo["linhas_importadas"] <= 0:
        raise ImportacaoCronogramaError(
            "Nenhuma linha foi importada."
        )

    if resumo["projetos_identificados"] <= 0:
        raise ImportacaoCronogramaError(
            "Nenhuma obra válida foi identificada."
        )

    if resumo["semanas_identificadas"] <= 0:
        raise ImportacaoCronogramaError(
            "Nenhuma semana válida foi identificada."
        )

    if not resumo["possui_resumo_geral"]:
        raise ImportacaoCronogramaError(
            "O CSV não possui nenhuma linha com DISCIPLINA "
            "igual a RESUMO GERAL."
        )

    if resumo["registros_sem_obra"]:
        raise ImportacaoCronogramaError(
            f"Existem {resumo['registros_sem_obra']} registro(s) "
            "sem vínculo com obras.Obra."
        )

    inconsistencias_resumo = (
        validar_resumo_geral_por_projeto_semana(
            importacao
        )
    )

    return resumo, inconsistencias_resumo


def _atualizar_dados_resumo(
    importacao: ImportacaoCronograma,
):
    resumo = _obter_resumo_importacao(importacao)

    importacao.total_linhas_arquivo = resumo[
        "linhas_importadas"
    ]
    importacao.linhas_importadas = resumo[
        "linhas_importadas"
    ]
    importacao.projetos_identificados = resumo[
        "projetos_identificados"
    ]
    importacao.semanas_identificadas = resumo[
        "semanas_identificadas"
    ]


def _ativar_importacao(
    importacao: ImportacaoCronograma,
    *,
    mensagem_final: str,
):
    """
    Ativa a nova importação somente depois que toda a leitura,
    criação de vínculos e validação estrutural terminaram.
    """
    with transaction.atomic():
        antigas = (
            ImportacaoCronograma.objects
            .select_for_update()
            .filter(ativa=True)
            .exclude(pk=importacao.pk)
        )

        antigas.update(
            ativa=False,
            mensagem=(
                "Importação substituída por uma versão mais recente. "
                "Os registros foram preservados para histórico."
            ),
        )

        importacao.ativa = True
        importacao.status = ImportacaoCronograma.Status.CONCLUIDA
        importacao.finalizou_em = timezone.now()
        importacao.mensagem = mensagem_final

        importacao.save(
            update_fields=[
                "ativa",
                "status",
                "finalizou_em",
                "mensagem",
                "total_linhas_arquivo",
                "linhas_importadas",
                "projetos_identificados",
                "semanas_identificadas",
                "atualizado_em",
            ]
        )


def _marcar_importacao_como_falha(
    importacao: ImportacaoCronograma,
    mensagem: str,
):
    RegistroCronograma.objects.filter(
        importacao=importacao
    ).delete()

    # Identidades permanentes eventualmente criadas durante uma tentativa
    # que falhou são mantidas. As chaves são idempotentes e poderão ser
    # reutilizadas em uma próxima importação.
    importacao.status = ImportacaoCronograma.Status.FALHOU
    importacao.ativa = False
    importacao.finalizou_em = timezone.now()
    importacao.mensagem = "A importação falhou."
    importacao.erro_detalhado = mensagem

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


def importar_cronograma(
    *,
    executado_por=None,
    forcar=False,
    tamanho_bloco=TAMANHO_BLOCO_LEITURA,
    tamanho_lote_banco=TAMANHO_LOTE_BANCO,
):
    configuracao = obter_configuracao_cronograma()

    try:
        dados_arquivo = obter_dados_csv_mais_recente(
            configuracao["folder_id"]
        )
    except GoogleDriveCronogramaError as exc:
        raise ImportacaoCronogramaError(
            str(exc)
        ) from exc

    if (
        not forcar
        and _arquivo_ja_ativo(
            dados_arquivo.get("hash_arquivo", "")
        )
    ):
        ativa = (
            ImportacaoCronograma.objects
            .filter(
                ativa=True,
                status=ImportacaoCronograma.Status.CONCLUIDA,
            )
            .order_by("-criado_em")
            .first()
        )

        return ResultadoImportacao(
            importacao=ativa,
            importado=False,
            mensagem=(
                "O CSV mais recente já corresponde à base ativa. "
                "Nenhuma atualização foi necessária."
            ),
        )

    try:
        indice_obras = listar_obras_por_nome_normalizado()
    except VinculoObraError as exc:
        raise ImportacaoCronogramaError(
            str(exc)
        ) from exc

    cache_obras: dict[str, Any] = {}

    importacao_anterior = _obter_importacao_ativa_anterior()

    mapa_datas_anteriores = _montar_mapa_datas_anteriores(
        importacao_anterior,
        indice_obras=indice_obras,
        cache_obras=cache_obras,
    )

    # Contadores compartilhados entre todos os chunks da nova importação.
    contadores_ocorrencia: dict[
        tuple[str, int | None],
        int,
    ] = defaultdict(int)

    momento_reprogramacao = timezone.now()

    importacao = _criar_importacao(
        dados_arquivo,
        executado_por=executado_por,
    )

    try:
        total = 0

        for dataframe in iterar_blocos_cronograma(
            conteudo=dados_arquivo["conteudo"],
            tamanho_bloco=tamanho_bloco,
            nome_arquivo=dados_arquivo.get(
                "nome_arquivo",
                "",
            ),
        ):
            objetos = _criar_registros_modelo(
                dataframe=dataframe,
                importacao=importacao,
                mapa_datas_anteriores=mapa_datas_anteriores,
                momento_reprogramacao=momento_reprogramacao,
                indice_obras=indice_obras,
                cache_obras=cache_obras,
                contadores_ocorrencia=contadores_ocorrencia,
            )

            RegistroCronograma.objects.bulk_create(
                objetos,
                batch_size=tamanho_lote_banco,
            )

            total += len(objetos)

            importacao.total_linhas_arquivo = total
            importacao.linhas_importadas = total
            importacao.mensagem = (
                "Importando e comparando registros: "
                f"{total:,} linhas processadas."
            )

            importacao.save(
                update_fields=[
                    "total_linhas_arquivo",
                    "linhas_importadas",
                    "mensagem",
                    "atualizado_em",
                ]
            )

        importacao.status = (
            ImportacaoCronograma.Status.VALIDANDO
        )
        importacao.mensagem = (
            "Validando os dados importados."
        )

        importacao.save(
            update_fields=[
                "status",
                "mensagem",
                "atualizado_em",
            ]
        )

        _, inconsistencias_resumo = (
            _validar_importacao_final(importacao)
        )

        _atualizar_dados_resumo(importacao)

        quantidade_reprogramadas = (
            RegistroCronograma.objects
            .filter(
                importacao=importacao,
                reprogramada=True,
            )
            .count()
        )

        quantidade_atividades = (
            AtividadePlanejamento.objects
            .filter(
                snapshots__importacao=importacao,
            )
            .distinct()
            .count()
        )

        alerta_resumo = formatar_alertas_resumo_geral(
            inconsistencias_resumo
        )

        mensagem_final = (
            "Importação concluída e ativada com sucesso. "
            f"{quantidade_atividades} atividade(s) permanente(s) "
            "vinculada(s) e "
            f"{quantidade_reprogramadas} registro(s) "
            "reprogramado(s)."
        )

        if alerta_resumo:
            mensagem_final += f" {alerta_resumo}"

        _ativar_importacao(
            importacao,
            mensagem_final=mensagem_final,
        )

        return ResultadoImportacao(
            importacao=importacao,
            importado=True,
            mensagem=mensagem_final,
        )

    except (
        CronogramaCsvError,
        ImportacaoCronogramaError,
        VinculoObraError,
    ) as exc:
        _marcar_importacao_como_falha(
            importacao,
            str(exc),
        )

        raise ImportacaoCronogramaError(
            str(exc)
        ) from exc

    except Exception as exc:
        mensagem = (
            "Erro inesperado durante a importação: "
            f"{exc}"
        )

        _marcar_importacao_como_falha(
            importacao,
            mensagem,
        )

        raise ImportacaoCronogramaError(
            mensagem
        ) from exc
