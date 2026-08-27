from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
import unicodedata

import pandas as pd
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from compras.models import HistoricoCompraSuprimento, SuprimentoReferencia
from compras.services.historico_suprimentos import normalizar_suprimento
from planejamento.models import (
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)
from planejamento.services.cronograma_suprimentos.normalizacao import (
    VinculoAbaObraError,
    localizar_obra_por_aba,
    normalizar_texto,
    texto_limpo,
)


COLUNAS_OBRIGATORIAS = ("ITEM", "STATUS", "FORNECEDOR", "VALOR")


# ---------------------------------------------------------------------------
# ALIASES CONFIRMADOS
# ---------------------------------------------------------------------------
# Chave = nome histórico vindo da planilha
# Valor = nome CANÔNICO existente atualmente no cronograma de suprimentos.
#
# Importante:
# - O nome original continua salvo em `suprimento`.
# - `suprimento_chave` recebe a chave do nome canônico.
# - Casos ambíguos NÃO entram aqui.
# ---------------------------------------------------------------------------
ALIASES_SUPRIMENTOS = {
    "ACABAMENTOS ELÉTRICA": "INTERRUPTORES E TOMADAS",

    "AQUECIMENTO PISCINA":
        "PLACAS DE AQUECIMENTO DE PISCINA",

    "AR CONDICIONADO - EQUIPAMENTO":
        "INSTALAÇÕES DE AR CONDICIONADO - MÁQUINAS",

    "AR CONDICIONADO INFRA":
        "INSTALAÇÕES DE AR CONDICIONADO - INFRAESTRUTURA",

    "ESQUADRIAS":
        "ESQUADRIAS DE ALUMÍNIO + VIDROS",

    "ILUMINAÇÃO":
        "LUMINÁRIAS",

    "MARCENARIA DA CASA":
        "MARCENARIA E ARMÁRIOS",

    "MARCENARIA DO BANHEIRO":
        "MARCENARIA DECORATIVA E PAINÉIS",

    "MARMORARIA":
        "REVESTIMENTOS (MARMORARIA)",

    "PORCELANATO":
        "REVESTIMENTOS EM PORCELANATO",

    "PEDRAS":
        "REVESTIMENTOS EM PEDRAS NATURAIS",

    "PORTAS":
        "PORTAS INTERNAS",

    "QUADROS":
        "QUADROS ELÉTRICOS",

    "PAISAGISMO":
        "PAISAGISMO (EXECUÇÃO)",

    "PROJETO ESTRUTURAL":
        "PROJETO - ESTRUTURAL",

    "PROJETO ESTRUTURAL / FUNDAÇÕES":
        "PROJETO - ESTRUTURAL",

    "PROJETO ESTRUTURAL E FUNDAÇÕES":
        "PROJETO - ESTRUTURAL",

    "PROJETO PAISAGISMO":
        "PROJETO - PAISAGISMO",

    "PROJETO INSTALAÇÕES":
        "PROJETO - INSTALAÇÕES (COMPLEMENTARES)",

    # Variações antigas observadas na base histórica
    "MARCENARIA  DECORATIVA (BANHOS, SALA E CIRCULAÇÃO )":
        "MARCENARIA DECORATIVA E PAINÉIS",

    "MARCENARIA DECORATIVA (BANHOS, SALA E CIRCULAÇÃO)":
        "MARCENARIA DECORATIVA E PAINÉIS",

    "MARCENARIA   (CLOSTS, HALL, AREA DE SERVIÇO, COZINHA E GOURMET)":
        "MARCENARIA E ARMÁRIOS",

    "MARCENARIA (CLOSTS, HALL, AREA DE SERVIÇO, COZINHA E GOURMET)":
        "MARCENARIA E ARMÁRIOS",
}


def _texto_comparacao(valor: str) -> str:
    valor = str(valor or "").strip()
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(
        c for c in valor
        if not unicodedata.combining(c)
    )
    return " ".join(valor.upper().split())



# Um histórico antigo pode representar mais de um suprimento atual.
# O valor NÃO é dividido: o mesmo registro aparece nos históricos
# relacionados, identificado no modal pelo nome original da compra.
ALIASES_MULTIPLOS_SUPRIMENTOS = {
    "BOX E ESPELHOS": [
        "BOXES",
        "ESPELHOS",
    ],
    "LOUÇAS E METAIS": [
        "LOUÇAS",
        "METAIS",
    ],
    "FORRO DE MADEIRA E PISO": [
        "FORRO EM MADEIRA",
        "PISO DE MADEIRA",
    ],
}

ALIASES_MULTIPLOS_NORMALIZADOS = {
    _texto_comparacao(origem): destinos
    for origem, destinos in ALIASES_MULTIPLOS_SUPRIMENTOS.items()
}

ALIASES_NORMALIZADOS = {
    _texto_comparacao(origem):
        destino
    for origem, destino in ALIASES_SUPRIMENTOS.items()
}


def _localizar_colunas(df):
    mapa = {}

    for coluna in df.columns:
        normalizada = normalizar_texto(coluna)

        if normalizada == "ITEM":
            mapa["ITEM"] = coluna
        elif normalizada == "STATUS":
            mapa["STATUS"] = coluna
        elif normalizada == "FORNECEDOR":
            mapa["FORNECEDOR"] = coluna
        elif "VALOR" in normalizada:
            mapa["VALOR"] = coluna

    faltantes = [
        nome
        for nome in COLUNAS_OBRIGATORIAS
        if nome not in mapa
    ]

    if faltantes:
        raise CommandError(
            "Colunas obrigatórias não encontradas: "
            + ", ".join(faltantes)
        )

    return mapa


def _decimal(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"))

    if isinstance(valor, (int, float)):
        return Decimal(str(valor)).quantize(Decimal("0.01"))

    texto = (
        str(valor)
        .strip()
        .replace("R$", "")
        .replace(" ", "")
    )

    if not texto:
        return None

    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _mapa_fornecedores():
    Fornecedor = apps.get_model("cadastros", "Fornecedor")
    mapa = defaultdict(list)

    for fornecedor in Fornecedor.objects.all().only("id", "nome"):
        chave = normalizar_texto(fornecedor.nome)

        if chave:
            mapa[chave].append(fornecedor)

    return mapa


def _localizar_obra_opcional(aba):
    """
    A obra histórica é opcional.

    Se ainda existir no cadastro atual:
      - salva FK da obra
      - salva nome atual

    Se não existir:
      - obra = NULL
      - obra_nome = nome original da aba
    """
    try:
        obra, codigo_obra = localizar_obra_por_aba(aba)

        return {
            "obra": obra,
            "obra_codigo": codigo_obra or str(aba).strip(),
            "obra_nome": str(obra),
            "vinculada": True,
        }

    except VinculoAbaObraError:
        nome_historico = str(aba).strip()

        return {
            "obra": None,
            "obra_codigo": nome_historico,
            "obra_nome": nome_historico,
            "vinculada": False,
        }


def _carregar_suprimentos_canonicos():
    """
    Catálogo real de suprimentos atualmente existentes
    no cronograma ativo/concluído.
    """
    qs = (
        ItemCronogramaSuprimento.objects
        .filter(
            cronograma_obra__importacao__ativa=True,
            cronograma_obra__importacao__status=
                ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        .exclude(item="")
        .values_list("item", flat=True)
        .distinct()
    )

    nomes = sorted(
        {str(x).strip() for x in qs if str(x).strip()},
        key=_texto_comparacao,
    )

    return nomes


def _montar_indices_canonicos(canonicos):
    exatos = defaultdict(list)
    equivalentes = defaultdict(list)

    for nome in canonicos:
        exatos[nome].append(nome)
        equivalentes[_texto_comparacao(nome)].append(nome)

    return exatos, equivalentes


def _resolver_suprimento_canonico(
    nome_historico,
    canonicos,
    exatos,
    equivalentes,
):
    """
    Resolve o vínculo em ordem:

    1. Exato
    2. Equivalente simples
    3. Alias manual único
    4. Alias manual múltiplo
    5. Sem vínculo automático

    Similaridade serve somente para relatório.
    """
    if nome_historico in exatos and len(exatos[nome_historico]) == 1:
        return {
            "tipo": "EXATO",
            "canonicos": [exatos[nome_historico][0]],
        }

    chave_comp = _texto_comparacao(nome_historico)
    equivalentes_encontrados = equivalentes.get(chave_comp, [])

    if len(equivalentes_encontrados) == 1:
        return {
            "tipo": "EQUIVALENTE",
            "canonicos": [equivalentes_encontrados[0]],
        }

    alias_multiplo = ALIASES_MULTIPLOS_NORMALIZADOS.get(chave_comp)

    if alias_multiplo:
        inexistentes = [
            nome for nome in alias_multiplo
            if nome not in canonicos
        ]

        if not inexistentes:
            return {
                "tipo": "ALIAS_MULTIPLO",
                "canonicos": list(alias_multiplo),
            }

        return {
            "tipo": "ALIAS_MULTIPLO_INVALIDO",
            "canonicos": [],
            "alias_destinos": list(alias_multiplo),
            "inexistentes": inexistentes,
        }

    alias = ALIASES_NORMALIZADOS.get(chave_comp)

    if alias:
        if alias in canonicos:
            return {
                "tipo": "ALIAS",
                "canonicos": [alias],
            }

        return {
            "tipo": "ALIAS_INVALIDO",
            "canonicos": [],
            "alias_destino": alias,
        }

    sugestoes = sorted(
        (
            (
                SequenceMatcher(
                    None,
                    chave_comp,
                    _texto_comparacao(nome),
                ).ratio(),
                nome,
            )
            for nome in canonicos
        ),
        reverse=True,
    )[:3]

    return {
        "tipo": "SEM_VINCULO",
        "canonicos": [],
        "sugestoes": sugestoes,
    }


def _sincronizar_catalogo_referencias(canonicos):
    """
    Garante que todos os suprimentos atuais tenham uma referência canônica.
    Retorna dict {nome_canônico: SuprimentoReferencia}.
    """
    referencias = {}

    for nome in canonicos:
        chave = normalizar_suprimento(nome)
        referencia, _ = SuprimentoReferencia.objects.update_or_create(
            chave=chave,
            defaults={
                "nome": nome,
                "ativo": True,
            },
        )
        referencias[nome] = referencia

    return referencias


class Command(BaseCommand):
    help = (
        "Importa histórico legado de suprimentos a partir "
        "de planilha Excel, preservando obra/fornecedor históricos "
        "e vinculando os suprimentos conhecidos ao catálogo atual."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "arquivo",
            type=str,
            help="Caminho da planilha .xlsx",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida e exibe o resultado sem gravar no banco.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        caminho = Path(options["arquivo"]).resolve()
        dry_run = options["dry_run"]

        if not caminho.exists():
            raise CommandError(
                f"Arquivo não encontrado: {caminho}"
            )

        if caminho.suffix.lower() != ".xlsx":
            raise CommandError(
                "O arquivo precisa ser uma planilha .xlsx."
            )

        try:
            excel = pd.ExcelFile(
                caminho,
                engine="openpyxl",
            )
        except Exception as exc:
            raise CommandError(
                f"Não foi possível abrir a planilha: {exc}"
            ) from exc

        fornecedores = _mapa_fornecedores()

        canonicos = _carregar_suprimentos_canonicos()

        if not canonicos:
            raise CommandError(
                "Nenhum suprimento foi encontrado na importação "
                "ativa/concluída do cronograma de suprimentos."
            )

        exatos, equivalentes = _montar_indices_canonicos(canonicos)
        referencias_canonicas = _sincronizar_catalogo_referencias(canonicos)

        criados = 0
        atualizados = 0
        ignorados_status = 0
        ignorados_invalidos = 0

        fornecedores_vinculados = 0
        fornecedores_nao_vinculados = set()

        obras_historicas_sem_vinculo = []

        vinculos_exatos = 0
        vinculos_equivalentes = 0
        vinculos_alias = 0
        vinculos_alias_multiplos = 0
        sem_vinculo_canonico = defaultdict(int)
        aliases_invalidos = {}

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Planilha: {caminho.name}"
            )
        )

        self.stdout.write(
            f"Suprimentos canônicos encontrados "
            f"no cronograma atual: {len(canonicos)}\n"
        )

        for aba in excel.sheet_names:
            dados_obra = _localizar_obra_opcional(aba)

            obra = dados_obra["obra"]
            codigo_obra = dados_obra["obra_codigo"]
            obra_nome = dados_obra["obra_nome"]
            obra_vinculada = dados_obra["vinculada"]

            if not obra_vinculada:
                obras_historicas_sem_vinculo.append(aba)

                self.stdout.write(
                    self.style.WARNING(
                        f"[ABA {aba}] obra histórica sem vínculo "
                        "com o cadastro atual; os registros serão "
                        f"preservados como '{obra_nome}'."
                    )
                )

            df = pd.read_excel(
                excel,
                sheet_name=aba,
                header=0,
            )

            mapa = _localizar_colunas(df)

            importados_aba = 0

            for indice, linha in df.iterrows():
                numero_linha_excel = int(indice) + 2

                status = normalizar_texto(
                    linha.get(mapa["STATUS"])
                )

                if status != "FECHADO":
                    ignorados_status += 1
                    continue

                item = texto_limpo(
                    linha.get(mapa["ITEM"])
                )

                fornecedor_nome = texto_limpo(
                    linha.get(mapa["FORNECEDOR"])
                )

                valor = _decimal(
                    linha.get(mapa["VALOR"])
                )

                if (
                    not item
                    or not fornecedor_nome
                    or valor is None
                    or valor <= 0
                ):
                    ignorados_invalidos += 1

                    self.stdout.write(
                        self.style.WARNING(
                            f"[ABA {aba} · linha "
                            f"{numero_linha_excel}] ignorada: "
                            "item, fornecedor ou valor "
                            "ausente/inválido."
                        )
                    )

                    continue

                candidatos_fornecedor = fornecedores.get(
                    normalizar_texto(fornecedor_nome),
                    [],
                )

                fornecedor = (
                    candidatos_fornecedor[0]
                    if len(candidatos_fornecedor) == 1
                    else None
                )

                if fornecedor:
                    fornecedores_vinculados += 1
                else:
                    fornecedores_nao_vinculados.add(
                        fornecedor_nome
                    )

                resolucao = _resolver_suprimento_canonico(
                    item,
                    canonicos,
                    exatos,
                    equivalentes,
                )

                tipo_vinculo = resolucao["tipo"]
                nomes_canonicos = resolucao.get("canonicos") or []

                if tipo_vinculo == "EXATO":
                    vinculos_exatos += 1
                elif tipo_vinculo == "EQUIVALENTE":
                    vinculos_equivalentes += 1
                elif tipo_vinculo == "ALIAS":
                    vinculos_alias += 1
                elif tipo_vinculo == "ALIAS_MULTIPLO":
                    vinculos_alias_multiplos += 1
                elif tipo_vinculo == "ALIAS_INVALIDO":
                    aliases_invalidos[item] = (
                        resolucao.get("alias_destino")
                    )
                elif tipo_vinculo == "ALIAS_MULTIPLO_INVALIDO":
                    aliases_invalidos[item] = " / ".join(
                        resolucao.get("alias_destinos") or []
                    )
                else:
                    sem_vinculo_canonico[item] += 1

                if len(nomes_canonicos) == 1:
                    suprimento_chave = normalizar_suprimento(
                        nomes_canonicos[0]
                    )
                else:
                    # Em vínculos múltiplos a relação oficial fica no M2M.
                    # A chave simples permanece como fallback histórico.
                    suprimento_chave = normalizar_suprimento(item)

                chave_importacao = hashlib.sha256(
                    (
                        "HISTORICO_SUPRIMENTOS|"
                        f"{aba}|"
                        f"{numero_linha_excel}"
                    ).encode("utf-8")
                ).hexdigest()

                defaults = {
                    "suprimento": item,
                    "suprimento_chave": suprimento_chave,
                    "obra": obra,
                    "obra_codigo": codigo_obra,
                    "obra_nome": obra_nome,
                    "fornecedor": fornecedor,
                    "fornecedor_nome": fornecedor_nome,
                    "valor": valor,
                    "data_fechamento": None,
                    "origem": (
                        HistoricoCompraSuprimento
                        .Origem
                        .LEGADO
                    ),
                    "processo": None,
                    "pedido": None,
                    "arquivo_origem": caminho.name,
                    "aba_origem": aba,
                    "linha_origem": numero_linha_excel,
                }

                registro, criado = (
                    HistoricoCompraSuprimento
                    .objects
                    .update_or_create(
                        chave_importacao=chave_importacao,
                        defaults=defaults,
                    )
                )

                referencias_do_historico = [
                    referencias_canonicas[nome]
                    for nome in nomes_canonicos
                    if nome in referencias_canonicas
                ]
                registro.suprimentos_referencia.set(
                    referencias_do_historico
                )

                criados += int(criado)
                atualizados += int(not criado)
                importados_aba += 1

            if obra_vinculada:
                descricao_obra = str(obra)
            else:
                descricao_obra = (
                    f"{obra_nome} "
                    "(histórica, sem vínculo atual)"
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"[ABA {aba}] obra "
                    f"{descricao_obra} · "
                    f"{importados_aba} "
                    "registro(s) válido(s)."
                )
            )

        # ------------------------------------------------------------------
        # RELATÓRIO
        # ------------------------------------------------------------------
        if obras_historicas_sem_vinculo:
            self.stdout.write(
                self.style.WARNING(
                    "\nObras históricas sem vínculo "
                    "com o cadastro atual:"
                )
            )

            for aba in obras_historicas_sem_vinculo:
                self.stdout.write(f"  - {aba}")

        if fornecedores_nao_vinculados:
            self.stdout.write(
                self.style.WARNING(
                    "\nFornecedores preservados apenas pelo nome:"
                )
            )

            for nome in sorted(fornecedores_nao_vinculados):
                self.stdout.write(f"  - {nome}")

        if sem_vinculo_canonico:
            self.stdout.write(
                self.style.WARNING(
                    "\nSuprimentos históricos sem vínculo canônico:"
                )
            )

            for nome, qtd in sorted(
                sem_vinculo_canonico.items(),
                key=lambda x: _texto_comparacao(x[0]),
            ):
                resolucao = _resolver_suprimento_canonico(
                    nome,
                    canonicos,
                    exatos,
                    equivalentes,
                )

                self.stdout.write(
                    f"  - {nome} · {qtd} registro(s)"
                )

                sugestoes = resolucao.get("sugestoes") or []

                for score, sugestao in sugestoes[:3]:
                    self.stdout.write(
                        f"      {score * 100:5.1f}%  {sugestao}"
                    )

        if aliases_invalidos:
            self.stdout.write(
                self.style.ERROR(
                    "\nATENÇÃO: aliases configurados cujo destino "
                    "não existe no cronograma atual:"
                )
            )

            for origem, destino in sorted(
                aliases_invalidos.items()
            ):
                self.stdout.write(
                    f"  - {origem} -> {destino}"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Criados: {criados}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Atualizados: {atualizados}")
        )

        self.stdout.write(
            "Fornecedores vinculados ao cadastro: "
            f"{fornecedores_vinculados}"
        )

        self.stdout.write(
            "Ignorados por status diferente de Fechado: "
            f"{ignorados_status}"
        )

        self.stdout.write(
            "Ignorados por dados incompletos/inválidos: "
            f"{ignorados_invalidos}"
        )

        self.stdout.write(
            "Obras históricas sem vínculo atual: "
            f"{len(obras_historicas_sem_vinculo)}"
        )

        self.stdout.write("")
        self.stdout.write("Vínculos de suprimento:")
        self.stdout.write(
            f"  Exatos: {vinculos_exatos}"
        )
        self.stdout.write(
            f"  Equivalentes: {vinculos_equivalentes}"
        )
        self.stdout.write(
            f"  Por alias confirmado: {vinculos_alias}"
        )
        self.stdout.write(
            f"  Por alias múltiplo: {vinculos_alias_multiplos}"
        )
        self.stdout.write(
            "  Sem vínculo canônico: "
            f"{sum(sem_vinculo_canonico.values())}"
        )

        if dry_run:
            transaction.set_rollback(True)

            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: nenhuma alteração "
                    "foi gravada no banco."
                )
            )
