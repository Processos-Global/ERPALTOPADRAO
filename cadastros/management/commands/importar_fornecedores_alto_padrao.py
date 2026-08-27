from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError


ABA_BASE = "BASE DE DADOS"
COLUNAS = [
    "DISCIPLINA",
    "NOME",
    "REPRESENTANTE",
    "CONTATO",
    "FORNECIMENTO E INSTALAÇÃO",
    "AVALIAÇÃO",
]


def normalizar(valor) -> str:
    texto = str(valor or "").strip().upper()
    texto = "".join(
        c
        for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto).strip()


def limpar(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return re.sub(r"\s+", " ", str(valor).strip())


def avaliacao_para_decimal(valor):
    """
    A planilha enviada usa estrelas vazias (☆☆☆☆☆) como ausência de nota.
    Se no futuro houver ★ preenchidas, convertemos para 1..5.
    """
    texto = limpar(valor)
    if not texto:
        return None

    preenchidas = texto.count("★")
    if preenchidas:
        return Decimal(preenchidas)

    # Somente estrelas vazias = ainda não avaliado.
    if set(texto) <= {"☆"}:
        return None

    try:
        numero = Decimal(texto.replace(",", "."))
        if Decimal("0") <= numero <= Decimal("5"):
            return numero
    except Exception:
        pass

    return None


def campos_modelo(model):
    return {f.name: f for f in model._meta.fields}


def atribuir_se_existe(destino, campos, nomes, valor):
    for nome in nomes:
        if nome in campos:
            destino[nome] = valor
            return nome
    return None


def carregar_grupos_visuais(caminho: Path, nomes_validos: set[str]):
    """
    Identifica se o fornecedor aparece nas abas visuais:
    - LISTA DE GRANDES FORNECEDORES
    - FORNECEDORES

    Isso é apenas informação descritiva e vai para observação.
    """
    grupos = defaultdict(set)

    mapa_abas = {
        "LISTA DE GRANDES FORNECEDORES": "Grandes fornecedores",
        "FORNECEDORES": "Fornecedores",
    }

    for aba, rotulo in mapa_abas.items():
        try:
            raw = pd.read_excel(caminho, sheet_name=aba, header=None)
        except Exception:
            continue

        if raw.shape[1] < 2:
            continue

        for valor in raw.iloc[:, 1].dropna():
            nome = limpar(valor)
            chave = normalizar(nome)
            if chave in nomes_validos:
                grupos[chave].add(rotulo)

    return grupos


def consolidar_planilha(caminho: Path):
    try:
        df = pd.read_excel(caminho, sheet_name=ABA_BASE)
    except ValueError as exc:
        raise CommandError(
            f"A planilha precisa conter a aba '{ABA_BASE}'."
        ) from exc

    faltantes = [c for c in COLUNAS if c not in df.columns]
    if faltantes:
        raise CommandError(
            "Colunas ausentes na BASE DE DADOS: " + ", ".join(faltantes)
        )

    grupos = {}

    for indice, linha in df.iterrows():
        nome = limpar(linha["NOME"])

        # Há uma linha de cabeçalho repetida dentro da BASE DE DADOS.
        if not nome or normalizar(nome) == "NOME":
            continue

        chave = normalizar(nome)

        if chave not in grupos:
            grupos[chave] = {
                "nome": nome,
                "linhas": [],
                "disciplinas": set(),
                "representantes": [],
                "contatos": [],
                "fornecimentos": set(),
                "avaliacoes": [],
            }

        g = grupos[chave]
        g["linhas"].append(int(indice) + 2)

        disciplina = limpar(linha["DISCIPLINA"])
        representante = limpar(linha["REPRESENTANTE"])
        contato = limpar(linha["CONTATO"])
        fornecimento = limpar(linha["FORNECIMENTO E INSTALAÇÃO"])
        avaliacao = avaliacao_para_decimal(linha["AVALIAÇÃO"])

        if disciplina:
            g["disciplinas"].add(disciplina)

        if representante and normalizar(representante) != "REPRESENTANTE":
            if representante not in g["representantes"]:
                g["representantes"].append(representante)

        if contato and normalizar(contato) != "CONTATO":
            if contato not in g["contatos"]:
                g["contatos"].append(contato)

        if (
            fornecimento
            and normalizar(fornecimento) != "FORNECIMENTO E INSTALACAO"
            and fornecimento != "-"
        ):
            g["fornecimentos"].add(fornecimento)

        if avaliacao is not None:
            g["avaliacoes"].append(avaliacao)

    nomes_validos = set(grupos.keys())
    grupos_visuais = carregar_grupos_visuais(caminho, nomes_validos)

    for chave, g in grupos.items():
        g["grupos_planilha"] = grupos_visuais.get(chave, set())

    return grupos


def montar_observacao(g):
    partes = [
        "Importado da planilha LISTA DE FORNECEDORES - ALTO PADRÃO.",
    ]

    if g["grupos_planilha"]:
        partes.append(
            "Origem na planilha: "
            + ", ".join(sorted(g["grupos_planilha"]))
            + "."
        )

    if g["disciplinas"]:
        partes.append(
            "Disciplinas: "
            + "; ".join(sorted(g["disciplinas"]))
            + "."
        )

    if g["fornecimentos"]:
        partes.append(
            "Fornecimento / instalação: "
            + "; ".join(sorted(g["fornecimentos"]))
            + "."
        )

    pares = []
    maximo = max(len(g["representantes"]), len(g["contatos"]))

    for i in range(maximo):
        representante = (
            g["representantes"][i]
            if i < len(g["representantes"])
            else ""
        )
        contato = (
            g["contatos"][i]
            if i < len(g["contatos"])
            else ""
        )

        if representante or contato:
            texto = representante or "Contato"
            if contato:
                texto += f" ({contato})"
            pares.append(texto)

    if len(pares) > 1:
        partes.append(
            "Contatos registrados: " + "; ".join(pares) + "."
        )

    return "\n".join(partes)


def gerar_codigo(Fornecedor, usados: set[str]) -> str:
    """
    Gera FOR-000001, FOR-000002...
    Só é usado se o model possuir campo `codigo`.
    """
    maior = 0

    for codigo in usados:
        m = re.fullmatch(r"FOR-(\d+)", codigo or "")
        if m:
            maior = max(maior, int(m.group(1)))

    numero = maior + 1

    while True:
        codigo = f"FOR-{numero:06d}"
        if codigo not in usados:
            usados.add(codigo)
            return codigo
        numero += 1


def descrever_protecao(exc: ProtectedError):
    objetos = list(exc.protected_objects)
    agrupados = defaultdict(list)

    for obj in objetos[:100]:
        agrupados[obj._meta.label].append(str(obj))

    linhas = []
    for modelo, valores in sorted(agrupados.items()):
        linhas.append(f"  - {modelo}: {len(valores)} vínculo(s)")
        for valor in valores[:5]:
            linhas.append(f"      • {valor}")
        if len(valores) > 5:
            linhas.append("      • ...")

    return "\n".join(linhas)


class Command(BaseCommand):
    help = (
        "Importa fornecedores da planilha LISTA DE FORNECEDORES - ALTO PADRÃO, "
        "consolidando duplicidades por nome normalizado."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=str)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Executa toda a validação e desfaz a transação ao final.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Exclui todos os fornecedores atuais antes da importação. "
                "Se houver vínculos protegidos, o comando aborta sem apagar nada."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        caminho = Path(options["arquivo"]).resolve()
        dry_run = options["dry_run"]
        reset = options["reset"]

        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        Fornecedor = apps.get_model("cadastros", "Fornecedor")
        campos = campos_modelo(Fornecedor)

        if "nome" not in campos:
            raise CommandError(
                "cadastros.Fornecedor não possui o campo obrigatório 'nome'."
            )

        grupos = consolidar_planilha(caminho)

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Planilha: {caminho.name}")
        )
        self.stdout.write(
            f"Linhas consolidadas em fornecedores únicos: {len(grupos)}"
        )

        atuais = Fornecedor.objects.all().order_by("id")
        qtd_atuais = atuais.count()
        self.stdout.write(f"Fornecedores atuais no banco: {qtd_atuais}")

        if reset and qtd_atuais:
            self.stdout.write(
                self.style.WARNING(
                    "\nRESET solicitado: tentando excluir fornecedores atuais..."
                )
            )
            try:
                apagados, detalhes = atuais.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Fornecedores atuais removidos com segurança: {apagados}"
                    )
                )
            except ProtectedError as exc:
                transaction.set_rollback(True)
                raise CommandError(
                    "Não foi possível excluir os fornecedores atuais porque "
                    "existem registros de Compras vinculados com PROTECT.\n"
                    "Nenhuma alteração foi gravada.\n\n"
                    + descrever_protecao(exc)
                ) from exc

        existentes = defaultdict(list)
        for fornecedor in Fornecedor.objects.all().order_by("id"):
            existentes[normalizar(fornecedor.nome)].append(fornecedor)

        codigos_usados = set()
        if "codigo" in campos:
            codigos_usados = set(
                Fornecedor.objects.exclude(codigo="")
                .values_list("codigo", flat=True)
            )

        criados = 0
        atualizados = 0
        avaliados = 0
        sem_avaliacao = 0
        multiplas_disciplinas = 0

        for chave, g in sorted(grupos.items(), key=lambda x: x[0]):
            candidatos = existentes.get(chave, [])

            if len(candidatos) > 1:
                raise CommandError(
                    f"Já existem {len(candidatos)} fornecedores no banco "
                    f"com o mesmo nome normalizado '{g['nome']}'. "
                    "Resolva a duplicidade ou use --reset."
                )

            representante_principal = (
                g["representantes"][0] if g["representantes"] else ""
            )
            contato_principal = (
                g["contatos"][0] if g["contatos"] else ""
            )

            avaliacao = None
            if g["avaliacoes"]:
                avaliacao = (
                    sum(g["avaliacoes"]) / Decimal(len(g["avaliacoes"]))
                ).quantize(Decimal("0.01"))
                avaliados += 1
            else:
                sem_avaliacao += 1

            if len(g["disciplinas"]) > 1:
                multiplas_disciplinas += 1

            dados = {}

            # Campos presentes no ERP Alto Padrão.
            atribuir_se_existe(dados, campos, ["nome_fantasia"], "")
            atribuir_se_existe(dados, campos, ["documento"], "")
            atribuir_se_existe(dados, campos, ["email"], "")
            atribuir_se_existe(
                dados, campos, ["contato", "contato_nome"], representante_principal
            )
            atribuir_se_existe(
                dados, campos, ["telefone"], contato_principal
            )
            atribuir_se_existe(
                dados, campos, ["whatsapp"], contato_principal
            )
            atribuir_se_existe(dados, campos, ["cidade"], "")
            atribuir_se_existe(dados, campos, ["estado"], "")
            atribuir_se_existe(dados, campos, ["endereco"], "")
            atribuir_se_existe(dados, campos, ["cep"], "")
            atribuir_se_existe(dados, campos, ["inscricao_estadual"], "")
            atribuir_se_existe(
                dados, campos, ["observacao", "observacoes"], montar_observacao(g)
            )
            atribuir_se_existe(dados, campos, ["ativo"], True)

            if "avaliacao" in campos:
                dados["avaliacao"] = avaliacao

            if candidatos:
                fornecedor = candidatos[0]
                fornecedor.nome = g["nome"]

                for campo, valor in dados.items():
                    setattr(fornecedor, campo, valor)

                fornecedor.save()
                atualizados += 1

            else:
                kwargs = {"nome": g["nome"], **dados}

                if "codigo" in campos:
                    kwargs["codigo"] = gerar_codigo(
                        Fornecedor,
                        codigos_usados,
                    )

                fornecedor = Fornecedor.objects.create(**kwargs)
                existentes[chave] = [fornecedor]
                criados += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Criados: {criados}"))
        self.stdout.write(self.style.SUCCESS(f"Atualizados: {atualizados}"))
        self.stdout.write(
            f"Fornecedores com múltiplas disciplinas: {multiplas_disciplinas}"
        )
        self.stdout.write(f"Com avaliação válida: {avaliados}")
        self.stdout.write(f"Sem avaliação: {sem_avaliacao}")
        self.stdout.write(
            f"Total final previsto: {Fornecedor.objects.count()}"
        )

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY-RUN: nenhuma alteração foi gravada no banco."
                )
            )
