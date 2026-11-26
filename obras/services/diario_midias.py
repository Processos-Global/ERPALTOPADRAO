import logging
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from django.core.cache import cache
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.utils import timezone
from PIL import Image, ImageOps

from core.storage import private_media_storage
from obras.services.fotos import validar_fotos


VARIANTES_FOTO_DIARIO = {
    "miniatura": (480, 78),
    "visualizar": (1600, 84),
}
FORMATOS_FOTO_DIARIO = ("JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF")
MAX_PIXELS_FOTO_DIARIO = 50_000_000
TEMPO_CACHE_FOTO_DIARIO = 900
MAX_BYTES_CACHE_FOTO_DIARIO = 512 * 1024


PREFIXO_FOTO_PRIVADA = "obras/diarios_privados/"
logger = logging.getLogger(__name__)


class ErroUploadFotoDiario(Exception):
    pass


def validar_fotos_diario(arquivos):
    fotos = validar_fotos(arquivos)
    for arquivo in fotos:
        try:
            with Image.open(arquivo, formats=FORMATOS_FOTO_DIARIO) as imagem:
                if imagem.width * imagem.height > MAX_PIXELS_FOTO_DIARIO:
                    raise ValidationError(f"A foto {arquivo.name} excede 50 milhões de pixels.")
                imagem.verify()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise ValidationError(f"A foto {arquivo.name} está inválida ou possui formato não suportado.") from exc
        finally:
            arquivo.seek(0)
    return fotos


def storage_foto_diario(foto):
    # O prefixo distingue os novos arquivos sem migrar ou mover mídias legadas.
    # Nunca procurar um arquivo privado ausente no armazenamento público.
    if foto.arquivo.name.startswith(PREFIXO_FOTO_PRIVADA):
        return private_media_storage
    return foto.arquivo.storage


@contextmanager
def uploads_privados_diario():
    """Compensa arquivos gravados se a transação do diário não concluir."""
    gravados = []

    def salvar(foto, arquivo):
        storage = private_media_storage
        campo = foto._meta.get_field("arquivo")
        nome = None
        try:
            agora = timezone.localdate()
            candidato = f"{PREFIXO_FOTO_PRIVADA}{agora:%Y/%m}/{uuid4().hex}/{storage.get_valid_name(arquivo.name)}"
            nome = storage.get_available_name(candidato, max_length=campo.max_length)
            arquivo.seek(0)
            nome_salvo = storage.save(nome, arquivo, max_length=campo.max_length)
        except (OSError, ValueError, SuspiciousFileOperation) as exc:
            # O diretório é exclusivo deste envio: também tenta limpar uma
            # gravação interrompida antes de storage.save retornar.
            try:
                if nome is not None:
                    storage.delete(nome)
            except Exception:
                logger.exception("Falha ao limpar foto parcial do diário.")
            raise ErroUploadFotoDiario from exc
        gravados.append((storage, nome_salvo))
        foto.arquivo = nome_salvo
        foto.save(force_insert=True)

    try:
        yield salvar
    except BaseException:
        for storage, nome in reversed(gravados):
            try:
                storage.delete(nome)
            except Exception:
                logger.exception("Falha ao limpar foto do diário após rollback.")
        raise


def gerar_variante_foto_diario(foto, variante):
    """Gera apenas a variante solicitada, a partir do mesmo storage da evidência."""
    limite, qualidade = VARIANTES_FOTO_DIARIO[variante]
    arquivo = foto.arquivo
    nome_chave = sha256(f"{arquivo.name}:{foto.enviado_em.isoformat()}".encode()).hexdigest()
    chave = f"diario-foto:v1:{foto.pk}:{variante}:{nome_chave}"
    jpeg = cache.get(chave)
    if jpeg is not None:
        return jpeg

    with storage_foto_diario(foto).open(arquivo.name, "rb") as original:
        with Image.open(original, formats=FORMATOS_FOTO_DIARIO) as imagem:
            if imagem.width * imagem.height > MAX_PIXELS_FOTO_DIARIO:
                raise ValueError("Foto excede o tamanho de visualização.")
            if imagem.format == "JPEG":
                imagem.draft("RGB", (limite, limite))
            ImageOps.exif_transpose(imagem, in_place=True)
            imagem.thumbnail((limite, limite), Image.Resampling.LANCZOS)
            with imagem.convert("RGB") as rgb, BytesIO() as destino:
                rgb.save(destino, "JPEG", quality=qualidade, optimize=True)
                jpeg = destino.getvalue()

    if len(jpeg) <= MAX_BYTES_CACHE_FOTO_DIARIO:
        cache.set(chave, jpeg, TEMPO_CACHE_FOTO_DIARIO)
    return jpeg
