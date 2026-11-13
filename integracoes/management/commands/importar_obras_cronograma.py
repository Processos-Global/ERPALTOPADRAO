from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from obras.models import Obra
from planejamento.services.cronograma.configuracoes import obter_configuracao_cronograma
from planejamento.services.cronograma.google_drive import (
    GoogleDriveCronogramaError,
    obter_dados_csv_mais_recente,
)
from planejamento.services.cronograma.normalizacao_csv import (
    CronogramaCsvError,
    iterar_blocos_cronograma,
)
from planejamento.services.cronograma.vinculos import normalizar_nome_obra


class Command(BaseCommand):
    help = (
        "Cria as obras oficiais do ERP a partir dos projetos existentes no "
        "CSV mais recente do Cronograma de Obras no Google Drive."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria criado sem gravar nada no banco.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))

        self.stdout.write(self.style.MIGRATE_HEADING("Importação de obras do cronograma"))
        self.stdout.write("Fonte: CSV mais recente do Cronograma de Obras no Google Drive")
        if dry_run:
            self.stdout.write(self.style.WARNING("MODO DRY-RUN: nenhuma obra será criada."))

        try:
            configuracao = obter_configuracao_cronograma()
            dados_arquivo = obter_dados_csv_mais_recente(configuracao["folder_id"])
        except (GoogleDriveCronogramaError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        nome_arquivo = dados_arquivo.get("nome_arquivo", "")
        conteudo = dados_arquivo.get("conteudo", b"")

        self.stdout.write(f"Arquivo localizado: {nome_arquivo or '(sem nome)'}")

        projetos = self._ler_projetos(
            conteudo=conteudo,
            nome_arquivo=nome_arquivo,
        )

        if not projetos:
            self.stdout.write(self.style.WARNING("Nenhum projeto válido foi encontrado no CSV."))
            return

        existentes = self._indice_obras_existentes()
        codigos_reservados = {
            str(codigo).strip().upper()
            for codigo in Obra.objects.values_list("codigo", flat=True)
            if str(codigo or "").strip()
        }

        a_criar = []
        ja_existentes = []

        for chave, dados in projetos.items():
            obra_existente = existentes.get(chave)
            if obra_existente is not None:
                ja_existentes.append((dados["nome"], obra_existente))
                continue

            codigo = self._gerar_codigo_unico(
                dados["nome"],
                codigos_reservados,
            )
            codigos_reservados.add(codigo.upper())

            a_criar.append(
                {
                    "nome": dados["nome"],
                    "codigo": codigo,
                    "nome_curto": dados["nome"][:120],
                    "tipo_obra": self._inferir_tipo_obra(dados["nome"]),
                    "quantidade_unidades": dados["quantidade_unidades"] or 1,
                }
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_LABEL(f"Projetos encontrados no CSV: {len(projetos)}"))
        self.stdout.write(f"Já cadastrados no ERP: {len(ja_existentes)}")
        self.stdout.write(f"Obras novas: {len(a_criar)}")

        if ja_existentes:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_LABEL("Já existentes:"))
            for nome, obra in ja_existentes:
                self.stdout.write(
                    f"  [OK] {nome} -> ID {obra.pk} | código {obra.codigo}"
                )

        if not a_criar:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Todas as obras do cronograma já estão cadastradas."))
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_LABEL("Obras que serão criadas:"))
        for item in a_criar:
            self.stdout.write(
                "  [CRIAR] "
                f"{item['nome']} | código={item['codigo']} | "
                f"tipo={item['tipo_obra']} | unidades={item['quantidade_unidades']}"
            )

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run concluído. Rode novamente sem --dry-run para gravar as obras."
                )
            )
            return

        criadas = []
        try:
            with transaction.atomic():
                for item in a_criar:
                    obra = Obra.objects.create(
                        nome=item["nome"],
                        codigo=item["codigo"],
                        nome_curto=item["nome_curto"],
                        tipo_obra=item["tipo_obra"],
                        status=Obra.Status.PLANEJAMENTO,
                        quantidade_unidades=item["quantidade_unidades"],
                        ativa=True,
                    )
                    criadas.append(obra)
        except Exception as exc:
            raise CommandError(
                "A criação das obras foi cancelada e a transação foi revertida. "
                f"Detalhes: {exc}"
            ) from exc

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído: {len(criadas)} obra(s) criada(s) com sucesso."
            )
        )
        self.stdout.write(
            "Agora você já pode atualizar/importar o Cronograma de Obras normalmente."
        )

    def _ler_projetos(self, *, conteudo: bytes, nome_arquivo: str):
        """
        Lê o mesmo CSV usado pelo importador oficial e consolida um registro
        por projeto. Quantidade de unidades usa o maior valor positivo encontrado
        para aquele projeto no arquivo.
        """
        projetos: OrderedDict[str, dict] = OrderedDict()

        try:
            blocos = iterar_blocos_cronograma(
                conteudo,
                tamanho_bloco=5000,
                nome_arquivo=nome_arquivo,
            )

            for dataframe in blocos:
                for registro in dataframe.to_dict("records"):
                    nome = str(registro.get("projeto") or "").strip()
                    chave = normalizar_nome_obra(nome)
                    if not chave:
                        continue

                    quantidade = registro.get("quantidade_unidades")
                    try:
                        quantidade = int(quantidade) if quantidade else None
                    except (TypeError, ValueError):
                        quantidade = None
                    if quantidade is not None and quantidade <= 0:
                        quantidade = None

                    if chave not in projetos:
                        projetos[chave] = {
                            "nome": nome,
                            "quantidade_unidades": quantidade,
                        }
                    elif quantidade:
                        atual = projetos[chave].get("quantidade_unidades") or 0
                        projetos[chave]["quantidade_unidades"] = max(
                            atual,
                            quantidade,
                        )

        except CronogramaCsvError as exc:
            raise CommandError(f"Erro ao ler o CSV do cronograma: {exc}") from exc

        return projetos

    def _indice_obras_existentes(self):
        """
        Índice conservador por nome normalizado.
        Não considera código/descrição aqui para não concluir que uma obra existe
        apenas porque algum outro campo textual coincidentemente bateu com o projeto.
        """
        indice = {}
        ambiguos = set()

        for obra in Obra.objects.all().iterator(chunk_size=1000):
            chave = normalizar_nome_obra(obra.nome)
            if not chave:
                continue

            anterior = indice.get(chave)
            if anterior is None:
                indice[chave] = obra
            elif anterior.pk != obra.pk:
                ambiguos.add(chave)

        for chave in ambiguos:
            indice.pop(chave, None)

        return indice

    def _gerar_codigo_unico(self, nome: str, codigos_reservados: set[str]) -> str:
        base = self._codigo_base(nome)
        candidato = base
        contador = 2

        while candidato.upper() in codigos_reservados:
            sufixo = f"-{contador}"
            candidato = f"{base[:60 - len(sufixo)]}{sufixo}"
            contador += 1

        return candidato

    @staticmethod
    def _codigo_base(nome: str) -> str:
        texto = unicodedata.normalize("NFKD", str(nome or ""))
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = texto.upper().strip()
        texto = re.sub(r"[^A-Z0-9]+", "-", texto)
        texto = re.sub(r"-+", "-", texto).strip("-")

        if not texto:
            texto = "OBRA"

        return texto[:60]

    @staticmethod
    def _inferir_tipo_obra(nome: str) -> str:
        chave = normalizar_nome_obra(nome)

        if "CASA" in chave:
            return Obra.TipoObra.CASA
        if any(termo in chave for termo in ("PREDIO", "TORRE", "EDIFICIO")):
            return Obra.TipoObra.PREDIO
        if "CONDOMINIO" in chave:
            return Obra.TipoObra.CONDOMINIO
        if any(termo in chave for termo in ("COMERCIAL", "LOJA", "ESCRITORIO")):
            return Obra.TipoObra.COMERCIAL

        return Obra.TipoObra.OUTRO
