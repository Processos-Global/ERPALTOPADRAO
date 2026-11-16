"""Pastas e arquivos da concretagem no Google Drive.

Estrutura: raiz > Obra > CONC-AAAA-NNNN - serviço > subpastas.
Reaproveita o cliente da conta de serviço de `core.services.arquivos_drive`.
Nada aqui bloqueia o fluxo: falhou, o arquivo fica temporário no
armazenamento privado (status PENDENTE) e é reenviado depois.
"""
import datetime
import io
import logging
import mimetypes
import re

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

SUB_SOLICITACAO = "01 Solicitação"
SUB_NOTAS = "02 Notas fiscais"
SUB_MOLDAGEM = "03 Moldagem CPs"
SUB_LAUDOS = "04 Laudos"
SUB_FOTOS = "05 Fotos"
SUBPASTAS = (SUB_SOLICITACAO, SUB_NOTAS, SUB_MOLDAGEM, SUB_LAUDOS, SUB_FOTOS)

# Ficam só no sistema (entram dentro da ficha de moldagem), sem upload próprio.
ETAPAS_SEM_DRIVE = ("ETIQUETA_CP",)

SUBPASTA_POR_ETAPA = {
    "NOTA_FISCAL": SUB_NOTAS,
    "ETIQUETA_CP": SUB_MOLDAGEM,
    "FICHA_MOLDAGEM": SUB_MOLDAGEM,
    "LAUDO": SUB_LAUDOS,
}


def drive_habilitado():
    return bool(
        getattr(settings, "CONCRETAGEM_DRIVE_ENABLED", False)
        and getattr(settings, "CONCRETAGEM_DRIVE_ROOT_FOLDER_ID", "")
    )


def _limpar_nome(nome, limite=120):
    nome = re.sub(r"[\\/:*?\"<>|\r\n]+", " ", nome or "").strip()
    return re.sub(r"\s+", " ", nome)[:limite].strip() or "SEM NOME"


def nome_pasta(conc):
    servico = conc.descricao_servico()
    return _limpar_nome(f"{conc.codigo} - {servico}" if servico else conc.codigo)


def garantir_pasta(conc):
    """Cria (ou reaproveita) a pasta da concretagem e as subpastas. Retorna True se ok."""
    if conc.drive_pasta_id:
        return True
    if not drive_habilitado():
        return False
    try:
        from core.services.arquivos_drive import obter_pasta

        raiz = settings.CONCRETAGEM_DRIVE_ROOT_FOLDER_ID
        pasta_obra = obter_pasta(raiz, _limpar_nome(conc.obra.nome))
        pasta = obter_pasta(pasta_obra, nome_pasta(conc))
        for sub in SUBPASTAS:
            obter_pasta(pasta, sub)
    except Exception:
        logger.exception("Falha ao criar pasta no Drive da concretagem %s", conc.codigo)
        return False
    conc.drive_pasta_id = pasta
    conc.drive_pasta_url = f"https://drive.google.com/drive/folders/{pasta}"
    conc.save(update_fields=["drive_pasta_id", "drive_pasta_url"])
    return True


def _upload(pasta_id, nome, conteudo, mime):
    from googleapiclient.http import MediaIoBaseUpload

    from core.services.arquivos_drive import cliente

    criado = cliente().files().create(
        body={"name": nome, "parents": [pasta_id]},
        media_body=MediaIoBaseUpload(io.BytesIO(conteudo), mimetype=mime or "application/octet-stream", resumable=True),
        fields="id,webViewLink", supportsAllDrives=True,
    ).execute()
    return criado["id"], criado.get("webViewLink") or f"https://drive.google.com/file/d/{criado['id']}/view"


def _nome_no_drive(anexo):
    base = _limpar_nome(anexo.nome_original, 150)
    prefixos = []
    if anexo.caminhao_id:
        prefixos.append(f"CAM{anexo.caminhao.ordem:02d}")
    if anexo.laudo_id:
        prefixos.append(f"{anexo.laudo.idade_dias}D")
    if anexo.etapa not in SUBPASTA_POR_ETAPA:
        prefixos.append(anexo.get_etapa_display().upper())
    return " - ".join(prefixos + [base]) if prefixos else base


ENVIO_TRAVADO_APOS = datetime.timedelta(minutes=10)


def segundo_plano():
    """Envios ao Drive fora da requisição (padrão). Testes usam envio imediato."""
    return getattr(settings, "CONCRETAGEM_DRIVE_SEGUNDO_PLANO", True)


def _reivindicar(anexo_id):
    """Marca o anexo como "enviando" de forma atômica. False se outro envio já está em curso."""
    from django.db.models import F, Q
    from django.utils import timezone

    from obras.models import AnexoConcretagem

    agora = timezone.now()
    return bool(
        AnexoConcretagem.objects.filter(pk=anexo_id, status=AnexoConcretagem.Status.PENDENTE, ativo=True)
        .filter(Q(enviando_em__isnull=True) | Q(enviando_em__lt=agora - ENVIO_TRAVADO_APOS))
        .update(enviando_em=agora, tentativas=F("tentativas") + 1)
    )


def enviar_anexo(anexo):
    """Leva o anexo pendente ao Drive. Sucesso: apaga o temporário. Retorna True/False."""
    from obras.models import AnexoConcretagem

    if anexo.no_drive:
        return True
    if anexo.etapa in ETAPAS_SEM_DRIVE:
        return False
    if not drive_habilitado() or not _reivindicar(anexo.pk):
        return False
    anexo = AnexoConcretagem.objects.select_related("concretagem__obra", "caminhao", "laudo").get(pk=anexo.pk)
    conc = anexo.concretagem
    try:
        if not garantir_pasta(conc):
            raise RuntimeError("pasta da concretagem indisponível no Drive")
        from core.services.arquivos_drive import obter_pasta

        pasta = obter_pasta(conc.drive_pasta_id, SUBPASTA_POR_ETAPA.get(anexo.etapa, SUB_FOTOS))
        with anexo.arquivo.open("rb") as f:
            conteudo = f.read()
        drive_id, url = _upload(pasta, _nome_no_drive(anexo), conteudo, anexo.tipo_conteudo)
    except Exception as exc:
        logger.exception("Falha ao enviar anexo %s da concretagem %s ao Drive", anexo.pk, conc.codigo)
        AnexoConcretagem.objects.filter(pk=anexo.pk).update(ultimo_erro=str(exc)[:300], enviando_em=None)
        return False
    nome_local = anexo.arquivo.name
    AnexoConcretagem.objects.filter(pk=anexo.pk).update(
        drive_id=drive_id, drive_url=url, status=AnexoConcretagem.Status.NO_DRIVE,
        ultimo_erro="", arquivo="", enviando_em=None,
    )
    try:
        anexo._meta.get_field("arquivo").storage.delete(nome_local)
    except Exception:
        logger.warning("Não foi possível apagar o temporário %s", nome_local)
    return True


def _enviar_lote(anexo_ids):
    from obras.models import AnexoConcretagem

    for anexo in AnexoConcretagem.objects.filter(pk__in=anexo_ids, ativo=True):
        try:
            enviar_anexo(anexo)
        except Exception:
            logger.exception("Falha inesperada no envio em segundo plano do anexo %s", anexo.pk)


def em_segundo_plano(funcao, *args):
    """Roda `funcao(*args)` depois do commit, numa thread (ou na hora, se desligado nos testes)."""
    import threading

    from django.db import close_old_connections, transaction

    def rodar():
        try:
            funcao(*args)
        except Exception:
            logger.exception("Falha em tarefa de segundo plano da concretagem (%s)", getattr(funcao, "__name__", funcao))

    def em_thread():
        close_old_connections()
        try:
            rodar()
        finally:
            close_old_connections()

    if not segundo_plano():
        rodar()  # testes: síncrono, sem mexer nas conexões
        return
    transaction.on_commit(lambda: threading.Thread(target=em_thread, name="concretagem-drive", daemon=True).start())


def _garantir_pasta_por_id(conc_id):
    from obras.models import Concretagem

    garantir_pasta(Concretagem.objects.select_related("obra").get(pk=conc_id))


def agendar_pasta(conc):
    if drive_habilitado() and not conc.drive_pasta_id:
        em_segundo_plano(_garantir_pasta_por_id, conc.pk)


def agendar_envio(anexo_ids):
    """Envia ao Drive depois do commit, numa thread: o usuário segue usando o site."""
    ids = [i for i in dict.fromkeys(anexo_ids) if i]
    if ids and drive_habilitado():
        em_segundo_plano(_enviar_lote, ids)


def criar_anexo(conc, etapa, arquivo, usuario, caminhao=None, laudo=None, descricao="", nome=None, conteudo_tipo=None):
    """Grava o temporário (armazenamento privado) e agenda o envio ao Drive em segundo plano.

    `arquivo` pode ser um UploadedFile ou bytes (com `nome` e `conteudo_tipo`).
    """
    from obras.models import AnexoConcretagem

    if isinstance(arquivo, (bytes, bytearray)):
        nome_original = nome or "arquivo"
        tipo = conteudo_tipo or mimetypes.guess_type(nome_original)[0] or "application/octet-stream"
        tamanho = len(arquivo)
        conteudo = ContentFile(bytes(arquivo), name=nome_original)
    else:
        nome_original = nome or arquivo.name
        tipo = getattr(arquivo, "content_type", "") or mimetypes.guess_type(nome_original)[0] or ""
        tamanho = arquivo.size
        conteudo = arquivo
    anexo = AnexoConcretagem(
        concretagem=conc, etapa=etapa, caminhao=caminhao, laudo=laudo,
        nome_original=nome_original[:255], tipo_conteudo=tipo[:100], tamanho=tamanho,
        descricao=(descricao or "")[:300], enviado_por=usuario,
    )
    anexo.arquivo.save(nome_original, conteudo, save=False)
    anexo.save()
    if etapa not in ETAPAS_SEM_DRIVE:
        agendar_envio([anexo.pk])
    return anexo


def pendentes(conc):
    return (
        conc.anexos.filter(ativo=True, status="PENDENTE").exclude(etapa__in=ETAPAS_SEM_DRIVE)
        .select_related("caminhao", "laudo")
    )


def agendar_pendentes(conc):
    """Reagenda em segundo plano todos os anexos ainda temporários. Retorna a quantidade."""
    ids = list(pendentes(conc).values_list("pk", flat=True))
    agendar_envio(ids)
    return len(ids)


def reenviar_pendentes(conc):
    """Envio imediato (síncrono) dos pendentes. Retorna (enviados, restantes)."""
    lista = list(pendentes(conc))
    enviados = sum(1 for a in lista if enviar_anexo(a))
    return enviados, len(lista) - enviados


def ler_bytes(anexo):
    """Conteúdo do anexo: do temporário local ou baixado do Drive (para o PDF da ficha)."""
    if anexo.arquivo:
        with anexo.arquivo.open("rb") as f:
            return f.read()
    if anexo.drive_id:
        from core.services.arquivos_drive import baixar_para

        buf = io.BytesIO()
        baixar_para(anexo.drive_id, buf)
        return buf.getvalue()
    raise FileNotFoundError(f"Anexo {anexo.pk} sem conteúdo disponível")
