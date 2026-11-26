import logging
from hashlib import sha256
from random import uniform
from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED
from time import sleep

from django.core.files import File
from django.db import OperationalError, connection, transaction

from financeiro.models import AnexoTituloPagar
from financeiro.models.titulos import SolicitacaoAvulsa
from financeiro.services.notificacoes import notificar_aprovadores
from financeiro.services.titulos import criar_titulos_manuais


logger = logging.getLogger(__name__)


class SolicitacaoAvulsaDivergente(Exception):
    pass


class SolicitacaoAvulsaInvalida(Exception):
    pass


def _anexar_documentos(titulos, documentos, usuario, gravados):
    chaves = set()
    for documento in documentos:
        conteudo = sha256()
        for bloco in documento.chunks():
            conteudo.update(bloco)
        documento.seek(0)
        chave = (documento.name.strip().lower(), conteudo.digest())
        if chave in chaves:
            continue
        chaves.add(chave)
        for titulo in titulos:
            documento.seek(0)
            anexo = AnexoTituloPagar(titulo=titulo, nome_original=documento.name, enviado_por=usuario)
            # O wrapper permite compartilhar a leitura sem mover o upload temporário.
            anexo.arquivo.save(documento.name, File(documento.file, name=documento.name), save=False)
            gravados.append((anexo.arquivo.storage, anexo.arquivo.name))
            anexo.save()


def _registrar(usuario, chave, impressao, validar_dados):
    gravados = []
    try:
        with transaction.atomic():
            tentativa, criada = SolicitacaoAvulsa.objects.select_for_update().get_or_create(
                usuario=usuario, chave=chave, defaults={"impressao_digital": impressao},
            )
            if not criada:
                if tentativa.impressao_digital != impressao:
                    raise SolicitacaoAvulsaDivergente
                return list(tentativa.titulos.order_by("parcela_ordem")), False

            dados = validar_dados()
            documentos = dados.pop("anexos", [])
            titulos = criar_titulos_manuais(usuario=usuario, solicitacao_avulsa=tentativa, **dados)
            _anexar_documentos(titulos, documentos, usuario, gravados)
            for titulo in titulos:
                notificar_aprovadores(titulo)
            return titulos, True
    except Exception:
        # O armazenamento privado não participa do rollback do banco.
        for storage, nome in gravados:
            try:
                storage.delete(nome)
            except OSError:
                logger.exception("Falha ao remover o arquivo de uma solicitação revertida.")
        raise


def _bloqueio_de_concorrencia(erro):
    if connection.vendor == "sqlite":
        codigo = getattr(erro.__cause__, "sqlite_errorcode", 0)
        return codigo & 0xFF in {SQLITE_BUSY, SQLITE_LOCKED}
    return connection.vendor == "mysql" and erro.args[:1] in {(1205,), (1213,)}


def registrar_solicitacao_avulsa(*, usuario, chave, impressao, validar_dados):
    """Materializa título, parcelas, anexos, histórico e notificações numa tentativa."""
    esperas = (0.02, 0.05, 0.10, 0.20, 0.40, 0)
    if connection.vendor == "sqlite":
        # O cache compartilhado do SQLite pode bloquear a promoção de leitura
        # para escrita. Evita que tentativas simultâneas repitam em sincronia.
        esperas = (0.02, 0.05, 0.10, 0.20, 0.40, 0.80, 1.60, 0)
    for espera in esperas:
        try:
            return _registrar(usuario, chave, impressao, validar_dados)
        except OperationalError as erro:
            if not espera or not _bloqueio_de_concorrencia(erro):
                raise
            sleep(uniform(espera / 2, espera) if connection.vendor == "sqlite" else espera)
